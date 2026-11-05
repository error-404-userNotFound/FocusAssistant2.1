from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import random
import tempfile
import threading
import time
import unittest

from focusassistant.classification import LMStudioClient, cache_key, endpoint, readability_issue, rule_decision
from focusassistant.controller import Controller, SlidingWindowQueue
from focusassistant.models import Control, Decision, Event, Session, Settings, Snapshot, State
from focusassistant.reports import PrefixSums, Span, build_report, merge_chronological, quicksort_ranking
from focusassistant.storage import StorageError, Store


def snapshot(at=101, url="https://example.org/Article", text="A useful article about photosynthesis.", **kwargs):
    return Snapshot("com.apple.Safari", "Safari", url=url, title="Photosynthesis", text=text,
                    observed_at=at, **kwargs)


def event(at, label="relevant", host="example.org", kind="webpage"):
    return Event(str(at), "s", at, kind, "https://" + host, host, host, "key", label, "reason", "rule")


class RulesTests(unittest.TestCase):
    def test_domain_boundary(self):
        settings = Settings(distracting_domains="example.org")
        self.assertEqual(rule_decision(snapshot(), settings).label, "distracting")
        self.assertEqual(rule_decision(snapshot(url="https://sub.example.org"), settings).label, "distracting")
        self.assertIsNone(rule_decision(snapshot(url="https://notexample.org"), settings))

    def test_conflicting_domains(self):
        settings = Settings(relevant_domains="example.org", distracting_domains="example.org")
        self.assertEqual(rule_decision(snapshot(), settings).label, "uncertain")

    def test_keyword_normalization_and_conflicts(self):
        settings = Settings(relevant_keywords="PHOTOSYNTHÉSIS", distracting_keywords="games")
        self.assertEqual(rule_decision(snapshot(), settings).label, "relevant")
        self.assertEqual(rule_decision(snapshot(text="photosynthesis and games"), settings).label, "uncertain")

    def test_missing_text_does_not_use_keywords(self):
        self.assertIsNone(rule_decision(snapshot(text=""), Settings(relevant_keywords="photosynthesis"), domains_only=True))

    def test_cache_isolates_task_content_case_and_settings(self):
        page, settings = snapshot(), Settings()
        key = cache_key("Task", page, settings)
        for task, changed, config in (("Other", page, settings), ("Task", replace(page, text="changed"), settings),
                                      ("Task", replace(page, url="https://example.org/article"), settings),
                                      ("Task", page, replace(settings, model="other"))):
            self.assertNotEqual(key, cache_key(task, changed, config))
        self.assertEqual(key, cache_key(" task ", page, settings))

    def test_readability(self):
        self.assertIsNotNone(readability_issue(replace(snapshot(), title="Access denied")))

    def test_remote_and_malformed_endpoints(self):
        for base in ("https://example.com/v1", "file:///tmp/server", "http://127.0.0.1.evil/v1",
                     "http://user@localhost/v1", "http://localhost/v1?x=1", "http://localhost:bad/v1"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                endpoint(base, "models")
        self.assertEqual(endpoint("http://[::1]:1234/v1/", "models"), "http://[::1]:1234/v1/models")


class ReportsTests(unittest.TestCase):
    def test_pause_and_app_switch_totals(self):
        state = State()
        session = Session("s", "task", 0, 100)
        state.controls = [Control("s", 0, "started"), Control("s", 30, "paused"), Control("s", 50, "resumed"), Control("s", 100, "ended")]
        state.pages = [event(10), event(60, "distracting")]
        state.applications = [event(80, "uncertain", "App · Notes", "application")]
        report = build_report(session, state)
        self.assertEqual(report.total, {"relevant": 20, "uncertain": 40, "distracting": 20})
        self.assertEqual(report.distraction_ranking, [("example.org", 20)])
        self.assertEqual(report.prefix.totals(20, 70), {"relevant": 10, "uncertain": 10, "distracting": 10})

    def test_same_time_page_supersedes_app_placeholder(self):
        state = State(pages=[event(0)], applications=[event(0, "uncertain", kind="application")])
        self.assertEqual(build_report(Session("s", "task", 0, 10), state).total["relevant"], 10)

    def test_prefix_gaps_and_partial_spans(self):
        prefix = PrefixSums([Span(10, 20, "relevant", "a", "a"), Span(40, 50, "distracting", "b", "b")])
        self.assertEqual(prefix.totals(15, 45), {"relevant": 5, "uncertain": 0, "distracting": 5})
        self.assertEqual(sum(prefix.totals(20, 40).values()), 0)
        self.assertEqual(sum(prefix.totals(50, 10).values()), 0)

    def test_unsorted_and_duplicate_records(self):
        state = State(pages=[event(20, "distracting"), event(10), event(10)])
        report = build_report(Session("s", "task", 0, 30), state)
        self.assertEqual(report.total, {"relevant": 10, "uncertain": 10, "distracting": 10})
        self.assertGreaterEqual(len(report.warnings), 2)

    def test_quicksort_many_equal_values(self):
        rng = random.Random(42)
        values = [(f"site-{i}", rng.randrange(8)) for i in range(500)]
        self.assertEqual(quicksort_ranking(values), sorted(values, key=lambda v: (-v[1], v[0].casefold(), v[0])))

    def test_merge_stream_order(self):
        rows = list(merge_chronological([event(2), event(5)], [event(3)], [Control("s", 0, "started")]))
        self.assertEqual([r.occurred_at for r in rows], [0, 2, 3, 5])


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.app = Controller(self.store)
        self.app.start("Study photosynthesis", now=100)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_empty_task_and_duplicate_start(self):
        self.app.end(now=101)
        with self.assertRaises(ValueError):
            self.app.start(" \n ")
        self.app.start("task", now=102)
        with self.assertRaises(ValueError):
            self.app.start("another", now=103)

    def test_immediate_pending_boundary(self):
        self.app.observe(snapshot())
        self.assertEqual(self.app.latest_page.source, "pending")
        self.assertIsNotNone(self.app.queued_job)
        self.assertEqual(self.app.elapsed(now=111), 11)

    def test_worker_inference_keeps_observations_flowing(self):
        entered, release = threading.Event(), threading.Event()
        class SlowClient:
            def classify(self, *_):
                entered.set()
                release.wait(2)
                return Decision("relevant", "done", "model")
        self.app.client = SlowClient()
        try:
            self.app.observe(snapshot())
            self.app.tick()
            self.assertTrue(entered.wait(1))
            self.app.observe(snapshot(at=103, url="https://example.org/next"))
            self.assertEqual(len(self.app.state.pages), 2)
            self.assertEqual(self.app.latest_page.source, "pending")
            release.set()
            deadline = time.monotonic() + 1
            while not self.app.model_future.done() and time.monotonic() < deadline:
                time.sleep(0.005)
            self.app.tick()
            self.assertEqual(self.app.state.pages[0].label, "relevant")
        finally:
            release.set()

    def test_sleep_or_monitoring_gap_pauses_at_heartbeat(self):
        self.app.last_wall = time.time() - 40
        self.app.state.last_heartbeat = 105
        self.app.tick()
        self.assertTrue(self.app.state.current.paused)
        self.assertEqual(self.app.state.controls[-1].occurred_at, 105)

    def test_observation_dedup_and_app_revisit(self):
        self.app.observe(snapshot())
        self.app.observe(snapshot(at=102))
        self.assertEqual(len(self.app.state.pages), 1)
        self.app.observe(Snapshot("notes", "Notes", observed_at=103))
        self.app.observe(snapshot(at=104))
        self.assertEqual(len(self.app.state.pages), 2)
        self.assertEqual(len(self.app.state.applications), 3)

    def test_slow_inference_does_not_lose_navigation(self):
        self.app.observe(snapshot())
        old = self.app.queued_job
        self.app.observe(snapshot(at=103, url="https://example.org/Other"))
        self.assertEqual(len(self.app.state.pages), 2)
        self.assertEqual(self.app.event(old[0]).source, "unavailable")
        self.app.complete_classification(old, Decision("distracting", "old", "model"))
        self.assertIsNone(self.app.warning_event(now=104))
        self.assertIsNone(self.app.event(old[0]).intervention)

    def test_override_wins_over_late_model_and_revisit(self):
        self.app.observe(snapshot())
        job = self.app.queued_job
        self.app._apply_override(job[0], "relevant", now=102)
        self.app.complete_classification(job, Decision("distracting", "late", "model"))
        self.assertEqual(self.app.latest_page.label, "relevant")
        self.app.observe(Snapshot("notes", "Notes", observed_at=103))
        self.app.observe(snapshot(at=104))
        self.assertEqual(self.app.latest_page.source, "override")

    def test_settings_change_discards_pending_result(self):
        self.app.observe(snapshot())
        job = self.app.queued_job
        self.app.apply_settings(Settings(model="different"))
        self.app.complete_classification(job, Decision("distracting", "late", "model"))
        self.assertEqual(self.app.latest_page.label, "uncertain")
        self.assertEqual(self.app.latest_page.source, "unavailable")

    def test_page_changes_at_same_url(self):
        self.app.observe(snapshot())
        self.app.observe(snapshot(at=102, text="Different page content"))
        self.assertEqual(len(self.app.state.pages), 2)
        self.assertNotEqual(self.app.state.pages[0].cache_key, self.app.state.pages[1].cache_key)

    def test_missing_text_domain_rule_and_uncertain_fallback(self):
        self.app.observe(snapshot(text="", error="Text access denied"))
        self.assertEqual(self.app.latest_page.source, "unavailable")
        self.app.apply_settings(Settings(distracting_domains="example.org"))
        self.app.observe(snapshot(at=102, text="", error="Text access denied"))
        self.assertEqual(self.app.latest_page.label, "distracting")

    def test_unsupported_page_uncertain_even_with_rule(self):
        self.app.apply_settings(Settings(distracting_domains="settings"))
        self.app.observe(snapshot(url="chrome://settings"))
        self.assertEqual(self.app.latest_page.source, "unavailable")

    def test_pause_ignores_observations_and_resumes_boundary(self):
        self.app.observe(snapshot())
        self.app.pause(now=105)
        self.app.observe(snapshot(at=107, url="https://example.org/Paused"))
        self.assertEqual(len(self.app.state.pages), 1)
        self.app.pause(now=110)
        self.app.observe(snapshot(at=111))
        self.app.end(now=120)
        self.assertEqual(sum(self.app.report(self.app.state.sessions[0]).total.values()), 15)

    def test_warning_escalation_and_correction(self):
        self.app.apply_settings(Settings(distracting_domains="example.org"))
        for at in (101, 110, 120):
            self.app.observe(snapshot(at=at, url=f"https://example.org/{at}"))
        self.assertIn("Repeated", self.app.latest_page.intervention)
        self.app._apply_override(self.app.latest_page.id, "relevant", now=121)
        self.assertEqual(self.app.recent.count(121), 2)
        self.assertIsNone(self.app.warning_event(now=121))
        self.app.observe(snapshot(at=800, url="https://example.org/new"))
        self.assertNotIn("Repeated", self.app.latest_page.intervention)

    def test_warning_hides_after_app_switch_or_stale_snapshot(self):
        self.app.apply_settings(Settings(distracting_domains="example.org"))
        self.app.observe(snapshot(at=101))
        self.assertIsNotNone(self.app.warning_event(now=102))
        self.assertIsNone(self.app.warning_event(now=106))
        self.app.observe(Snapshot("notes", "Notes", observed_at=103))
        self.assertIsNone(self.app.warning_event(now=103))

    def test_report_correct_when_model_finishes_after_session_end(self):
        self.app.observe(snapshot())
        job = self.app.queued_job
        self.app.end(now=111)
        self.app.complete_classification(job, Decision("relevant", "done", "model"))
        report = self.app.report(self.app.state.sessions[0])
        self.assertEqual(report.total["relevant"], 10)
        self.assertEqual(report.total["uncertain"], 1)


class StorageTests(unittest.TestCase):
    def test_lock_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            with self.assertRaises(StorageError):
                Store(directory)
            store.state.settings.model = "model"
            store.state.sessions.append(Session("s", "task", 100.1234, 200.5678))
            store.save()
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            store.close()
            reopened = Store(directory)
            self.assertEqual(reopened.state.sessions[0].started_at, 100.1234)
            self.assertEqual(reopened.state.settings.model, "model")
            reopened.close()

    def test_corrupt_file_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{broken")
            with self.assertRaises(StorageError):
                Store(directory)
            self.assertEqual(path.read_text(), "{broken")

    def test_malformed_record_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            data = State().to_dict()
            data["sessions"] = [{"bad": "record"}, {"id": "s", "task": "task", "started_at": 1}]
            (Path(directory) / "state.json").write_text(json.dumps(data))
            store = Store(directory)
            self.assertEqual(len(store.state.sessions), 1)
            self.assertTrue(store.state.storage_warnings)
            store.close()

    def test_recovery_ends_at_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.state.sessions = [Session("s", "task", 100)]
            store.state.current_session_id, store.state.last_heartbeat = "s", 110
            store.save()
            store.close()
            app = Controller(Store(directory))
            self.assertEqual(app.state.sessions[0].ended_at, 110)
            self.assertIsNone(app.state.current)
            self.assertIn("interrupted", app.error)
            app.close()

    def test_large_log_not_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.state.pages = [event(i) for i in range(12050)]
            store.save()
            store.close()
            store = Store(directory)
            self.assertEqual(len(store.state.pages), 12050)
            store.close()


class QueueTests(unittest.TestCase):
    def test_expiry_and_compaction(self):
        queue = SlidingWindowQueue()
        for i in range(1000):
            queue.append(i, interval=10)
        self.assertEqual(queue.count(999, 10), 11)
        self.assertLess(len(queue.dates), 100)
        self.assertEqual(queue.count(2000, 10), 0)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = []
        cls.mode = "normal"
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if cls.mode == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "https://example.com/never-send-page-data")
                    self.end_headers()
                    return
                self.reply({"data": [{"id": "fixture-model"}]})

            def do_POST(self):
                cls.payloads.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                if cls.mode == "http_error":
                    self.send_response(503)
                    self.end_headers()
                    return
                message = {"content": '```json\n{"label":"relevant","reason":"Matches the task."}\n```', "reasoning_content": "not final"}
                if cls.mode == "invalid":
                    message["content"] = '{"label":"wrong","reason":"bad"}'
                if cls.mode == "empty":
                    message["content"] = None
                self.reply({"choices": [{"finish_reason": "length" if cls.mode == "truncated" else "stop", "message": message}]})

            def reply(self, body):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def log_message(self, *_):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        type(self).mode = "normal"
        self.client = LMStudioClient()
        self.settings = Settings(base_url=self.base, model="fixture-model")

    def test_models(self):
        self.assertEqual(self.client.models(self.base + "/"), ["fixture-model"])

    def test_classification_and_reasoning_budget(self):
        decision = self.client.classify("task", snapshot(text="x" * 10000), self.settings)
        self.assertEqual(decision.label, "relevant")
        payload = self.payloads[-1]
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertEqual(payload["messages"][1]["content"].count("x"), 6001)  # URL example.org also contains x.

    def test_invalid_truncated_empty_and_http_failure(self):
        for mode in ("invalid", "truncated", "empty", "http_error"):
            type(self).mode = mode
            with self.subTest(mode=mode):
                self.assertEqual(self.client.classify("task", snapshot(), self.settings).source, "unavailable")

    def test_redirect_blocked(self):
        type(self).mode = "redirect"
        with self.assertRaisesRegex(ValueError, "redirected"):
            self.client.models(self.base)

    def test_missing_model_no_network_needed(self):
        decision = self.client.classify("task", snapshot(), Settings())
        self.assertEqual(decision.source, "unavailable")


if __name__ == "__main__":
    unittest.main()
