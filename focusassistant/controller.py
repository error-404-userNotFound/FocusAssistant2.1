"""Session state machine. UI-thread mutations; bounded background observation/inference."""
from bisect import bisect_right
from dataclasses import replace
import hashlib
import time
from threading import Event as Authorization
from urllib.parse import urlsplit

from .classification import LMStudioClient, cache_key, readability_issue, rule_decision
from .models import BROWSERS, Control, Decision, Event, LABELS, Session, identifier
from .reports import build_report
from .workers import Worker


class SlidingWindowQueue:
    """Array-backed FIFO with moving head and occasional prefix compaction."""
    def __init__(self):
        self.dates = []
        self.head = 0

    def append(self, date, interval=600):
        if self.dates and date < self.dates[-1]:
            self.dates.insert(bisect_right(self.dates, date), date)
        else:
            self.dates.append(date)
        return self.count(date, interval)

    def count(self, now, interval=600):
        while self.head < len(self.dates) and self.dates[self.head] < now - interval:
            self.head += 1
        if self.head >= 64 and self.head * 2 >= len(self.dates):
            self.dates = self.dates[self.head:]
            self.head = 0
        return len(self.dates) - self.head


class Controller:
    def __init__(self, store, observer=None, client=None, actions=None):
        self.store, self.state = store, store.state
        self.observer, self.client = observer, client or LMStudioClient()
        self.observation_pool = Worker("browser")
        self.model_pool = Worker("local-model")
        self.connection_pool = Worker("connection-check")
        self.action_pool = Worker("browser-actions")
        self.review_pool = Worker("correction-review")
        self.actions = actions
        self.action_future = self.restore_future = self.review_future = None
        self.action_lease = self.restore_lease = None
        self.action_event_id = None
        self.action_attempted = set()
        self.warning_ready = set()
        self.close_receipt = None
        self.page_contexts = {}
        self.review_message = "Corrections require a written explanation and local-model approval."
        self.action_message = "Automatic tab closing is disabled."
        self.observation_future = self.model_future = None
        self.model_job = self.queued_job = None
        self.next_observation = 0
        self.snapshot = None
        self.last_identity = None
        self.current_event_id = None
        self.frontmost_bundle = ""
        self.monitoring_message = "Start a session to monitor Safari, Chrome and foreground application names."
        self.error = ""
        self.connection_message = "Connection not checked"
        self.model_choices = []
        self.connection_future = None
        self.connection_base = None
        self.recent = SlidingWindowQueue()
        self.report_cache = {}
        self.closed = False
        self.last_wall, self.last_monotonic = time.time(), time.monotonic()
        # Close interrupted sessions at their recorded heartbeat, not at relaunch.
        current = self.state.current
        if current:
            end = min(time.time(), max(current.started_at, self.state.last_heartbeat or current.started_at))
            current.ended_at, current.paused = end, False
            self.state.controls.append(Control(current.id, end, "ended"))
            self.state.current_session_id = None
            self.error = "The previous session was interrupted and closed at its last recorded heartbeat."
        repaired = False
        for event in self.state.pages:
            if event.source == "pending":
                event.source, event.reason = "unavailable", "Classification was interrupted; this visit remains uncertain."
                repaired = True
        if current or repaired:
            self.save()

    def save(self):
        try:
            self.store.save()
            return True
        except (OSError, ValueError) as exc:
            self.error = f"Could not save changes: {exc}"
            return False

    def start(self, task, now=None):
        task = task.strip()
        if not task:
            raise ValueError("Enter the task you want to focus on before starting.")
        if self.state.current:
            raise ValueError("A session is already running.")
        now = time.time() if now is None else now
        session = Session(identifier(), task, now)
        self.state.sessions.append(session)
        self.state.current_session_id = session.id
        self.state.controls.append(Control(session.id, now, "started"))
        self.state.last_heartbeat = now
        self.recent = SlidingWindowQueue()
        self.invalidate_observation()
        self.save()

    def invalidate_observation(self):
        self.cancel_actions(include_restore=True)
        self.last_identity = None
        self.current_event_id = None
        self.next_observation = 0
        if self.queued_job:
            self.skip(self.queued_job[0])
            self.queued_job = None

    def pause(self, now=None):
        session = self.state.current
        if not session:
            return
        now = time.time() if now is None else now
        session.paused = not session.paused
        self.state.controls.append(Control(session.id, max(session.started_at, now), "paused" if session.paused else "resumed"))
        self.invalidate_observation()
        self.state.last_heartbeat = now
        self.save()

    def cancel_actions(self, include_restore=False):
        if self.action_lease:
            self.action_lease.clear()
        if include_restore and self.restore_lease:
            self.restore_lease.clear()

    def end(self, now=None):
        session = self.state.current
        if not session:
            return
        now = time.time() if now is None else now
        session.ended_at, session.paused = max(session.started_at, now), False
        self.state.controls.append(Control(session.id, session.ended_at, "ended"))
        self.state.current_session_id = None
        self.invalidate_observation()
        self.save()

    @property
    def latest_page(self):
        session = self.state.current
        return next((e for e in reversed(self.state.pages) if session and e.session_id == session.id), None)

    def elapsed(self, now=None):
        session = self.state.current
        if not session:
            return 0
        now = time.time() if now is None else now
        elapsed, start = 0, session.started_at
        for control in self.state.controls:
            if control.session_id != session.id:
                continue
            if control.kind in ("started", "resumed"):
                start = control.occurred_at
            elif control.kind in ("paused", "ended") and start is not None:
                elapsed += max(0, control.occurred_at - start)
                start = None
        return elapsed + (max(0, now - start) if start is not None else 0)

    def report(self, session, now=None):
        if session.ended_at is None:
            return build_report(session, self.state, now)
        key = (session.id, self.state.revision)
        if key not in self.report_cache:
            self.report_cache = {key: build_report(session, self.state, now)}
        return self.report_cache[key]

    def apply_settings(self, settings):
        from .classification import endpoint
        endpoint(settings.base_url, "models")
        self.state.settings = replace(settings)
        self.invalidate_observation()
        self.save()

    def check_connection(self, base):
        from .classification import endpoint
        endpoint(base, "models")
        if self.connection_future is None:
            self.connection_base = base
            self.connection_message = "Checking local server…"
            # Separate from inference so a 35-second model request cannot delay setup.
            self.connection_future = self.connection_pool.submit(self.client.models, base)

    def skip(self, event_id):
        event = self.event(event_id)
        if event and event.source == "pending":
            event.source = "unavailable"
            event.reason = "A newer page replaced this queued request; this visit remains uncertain."

    def event(self, event_id):
        return next((e for e in reversed(self.state.pages) if e.id == event_id), None)

    def warning_text(self, event):
        count = self.recent.append(event.occurred_at)
        return ("Repeated distraction: at least three distracting visits in ten minutes. Consider returning to your task or taking a short break."
                if count >= 3 else "This page may distract from your task. Return to your work or dismiss this reminder.")

    def _apply_override(self, event_id, label, now=None, note=""):
        if label not in LABELS:
            raise ValueError("Choose a valid classification.")
        event, session = self.event(event_id), self.state.current
        if event is None or session is None or event.session_id != session.id:
            raise ValueError("That page is no longer available in the current session.")
        event.label, event.reason, event.source = label, f"Marked {label} by you.", "override"
        event.is_override, event.intervention = True, None
        event.override_note = note
        self.cancel_actions()
        self.state.cache[event.cache_key] = {"label": label, "reason": event.reason, "source": "override"}
        self.recent = SlidingWindowQueue()
        now = time.time() if now is None else now
        for item in self.state.pages:
            if item.session_id == session.id and item.label == "distracting" and item.occurred_at >= now - 600:
                self.recent.append(item.occurred_at)
        self.save()

    def request_override(self, event_id, label, explanation):
        session, event = self.state.current, self.event(event_id)
        if not session or session.paused or not event or event.session_id != session.id:
            raise ValueError("A correction requires the same active, unpaused session.")
        if label not in LABELS or label == event.label:
            raise ValueError("Choose a different valid label.")
        if len(explanation.strip()) < 20:
            raise ValueError("Give a concrete explanation of at least 20 characters.")
        if event.source == "pending":
            raise ValueError("Wait for the local classification/retries to finish first.")
        page = self.page_contexts.get(event.id)
        if page is None:
            raise ValueError("That page's captured review context is no longer available.")
        if self.review_future:
            raise ValueError("A correction application is already being reviewed.")
        self.cancel_actions()
        self.review_job = (event.id, label, explanation.strip(), self.context(), self.classification_signature(event))
        self.review_message = "The local model is reviewing your correction application…"
        self.review_future = self.review_pool.submit(self.client.review_override, session.task, page,
            replace(self.state.settings), event.label, label, explanation.strip(), event.reason)

    @staticmethod
    def classification_signature(event):
        return (event.label, event.source, event.is_override, event.cache_key, event.reason)

    def finish_review(self, verdict):
        event_id, label, explanation, context, event_signature = self.review_job
        event = self.event(event_id)
        if context != self.context() or not event or self.classification_signature(event) != event_signature:
            self.review_message = "Correction discarded: session, settings or classification changed during review."
            return
        if verdict.approved is not True:
            self.action_attempted.discard(event_id)
            self.review_message = "Correction rejected: " + verdict.reason
            return
        self._apply_override(event_id, label, note=explanation + "\nModel approval: " + verdict.reason)
        self.review_message = "Correction approved: " + verdict.reason
        self.restore_if_approved()

    def restore_if_approved(self):
        receipt, session = self.close_receipt, self.state.current
        event = self.event(receipt.event_id) if receipt else None
        if (receipt and receipt.valid and event and event.is_override and event.label != "distracting"
                and session and not session.paused and session.id == event.session_id and self.actions and not self.restore_future):
            self.restore_lease = Authorization()
            self.restore_lease.set()
            self.restore_future = self.action_pool.submit(self.actions.restore, receipt, self.restore_lease)

    def observe(self, page):
        """Commit activity immediately; slow inference never blocks observations."""
        session = self.state.current
        if not session or session.paused or page.observed_at < session.started_at:
            return
        now = page.observed_at
        self.snapshot = page
        application_changed = self.frontmost_bundle != page.bundle or self.last_identity is None
        self.frontmost_bundle = page.bundle
        if application_changed:
            name = BROWSERS.get(page.bundle, page.app_name)
            self.state.applications.append(Event(identifier(), session.id, now, "application", "app://" + page.bundle,
                name, name + " · unclassified" if page.bundle in BROWSERS else "App · " + name, "application|" + page.bundle,
                reason="Waiting for browser page access." if page.bundle in BROWSERS else "Only the app name is recorded; window contents are not inspected.",
                source="unavailable", bundle=page.bundle))
        if page.bundle not in BROWSERS:
            self.cancel_actions()
            self.last_identity = (page.bundle,)
            self.current_event_id = None
            self.monitoring_message = f"Recording foreground application: {page.app_name}"
            if application_changed:
                self.save()
            return
        fingerprint = hashlib.sha256(page.text[:24000].encode()).hexdigest()
        identity = (page.bundle, page.window_id, page.tab_id, page.document_id, page.url, page.title, fingerprint, page.error)
        self.monitoring_message = page.error or f"Monitoring {page.app_name}: {page.title or page.url} ({page.text_source})"
        if self.last_identity == identity:
            return
        self.cancel_actions()
        self.last_identity = identity
        if self.queued_job:
            self.skip(self.queued_job[0])
            self.queued_job = None
        settings = replace(self.state.settings)
        key = cache_key(session.task, page, settings)
        cached = self.state.cache.get(key)
        issue = readability_issue(page)
        supported = urlsplit(page.url).scheme.lower() in ("http", "https")
        if not supported:
            decision = Decision("uncertain", page.error or "Only HTTP/HTTPS pages can be classified.", "unavailable")
        elif issue:
            decision = Decision("uncertain", issue, "unavailable")
        elif cached and not (cached["label"] == "uncertain" and cached["source"] != "override"):
            decision = Decision(cached["label"], cached["reason"], "override" if cached["source"] == "override" else "cache")
        else:
            decision = rule_decision(page, settings, domains_only=not bool(page.text.strip()))
            if decision is None:
                decision = (Decision("uncertain", page.error or "No readable page text was available.", "unavailable")
                            if not page.text.strip() else Decision("uncertain", "Classifying locally; uncertain results are retried up to three times with more context…", "pending"))
        event = Event(identifier(), session.id, now, "webpage", page.url or "browser://unavailable",
                      page.title or "Browser page unavailable", urlsplit(page.url).hostname or page.app_name + " · unavailable",
                      key, decision.label, decision.reason, decision.source, is_override=decision.source == "override",
                      page_key=repr(identity), bundle=page.bundle)
        if event.label == "distracting":
            event.intervention = self.warning_text(event)
        # Binary insertion preserves chronological order for delayed observations.
        position = bisect_right([e.occurred_at for e in self.state.pages], now)
        self.state.pages.insert(position, event)
        self.page_contexts[event.id] = page
        if len(self.page_contexts) > 32:
            # Keep the most recent automatic-close context available for review.
            protected = self.close_receipt.event_id if self.close_receipt else None
            oldest = next((eid for eid in self.page_contexts if eid != protected), None)
            if oldest:
                del self.page_contexts[oldest]
        self.current_event_id = event.id
        if decision.source == "rule":
            self.state.cache[key] = {"label": event.label, "reason": event.reason, "source": "rule"}
        if decision.source == "pending":
            self.queued_job = (event.id, session.task, page, settings)
        self.save()

    def complete_classification(self, job, decision):
        event = self.event(job[0])
        if not event or event.is_override:
            return
        if job[3] != self.state.settings:
            event.source, event.reason = "unavailable", "Classifier settings changed during processing; this visit remains uncertain."
            self.save()
            return
        event.label, event.reason, event.source = decision.label, decision.reason, decision.source
        event.attempts = decision.attempts
        # A correction on another visit to the same key must also win over inference.
        corrected = self.state.cache.get(event.cache_key, {})
        if corrected.get("source") == "override":
            event.label, event.reason, event.source, event.is_override = corrected["label"], corrected["reason"], "override", True
        elif decision.source == "model" and decision.label != "uncertain":
            self.state.cache[event.cache_key] = {"label": decision.label, "reason": decision.reason, "source": "model"}
        session = self.state.current
        if (event.label == "distracting" and session and session.id == event.session_id
                and not session.paused and self.current_event_id == event.id and self.frontmost_bundle == event.bundle):
            event.intervention = self.warning_text(event)
        self.save()

    def warning_event(self, now=None):
        now = time.time() if now is None else now
        session, event = self.state.current, self.event(self.current_event_id)
        if (session and not session.paused and event and event.label == "distracting" and event.intervention
                and not event.closed_at and (not self.actions or event.id in self.warning_ready)
                and self.snapshot and now - self.snapshot.observed_at < 4
                and self.frontmost_bundle == event.bundle):
            return event
        return None

    def tick_actions(self):
        if self.review_future and self.review_future.done():
            try:
                self.finish_review(self.review_future.result())
            except Exception as exc:
                self.review_message = f"Correction rejected: review unavailable ({exc})."
            self.review_future = None
        if self.restore_future and self.restore_future.done():
            try:
                self.action_message = self.restore_future.result().message
            except Exception as exc:
                self.action_message = f"Restore refused: {exc}"
            self.restore_future = None
            self.next_observation = 0
        if self.action_future and self.action_future.done():
            try:
                result = self.action_future.result()
                self.action_message = result.message
                if result.warning_ready:
                    self.warning_ready.add(self.action_event_id)
                if result.receipt:
                    event = self.event(self.action_event_id)
                    if event:
                        event.closed_at = time.time()
                    self.save()
                if result.receipt:
                    if self.close_receipt:
                        self.close_receipt.valid = False
                    self.close_receipt = result.receipt
                    self.restore_if_approved()
                    self.current_event_id = None
                    self.last_identity = None
                    self.next_observation = 0
            except Exception as exc:
                self.action_message = f"Browser action refused: {exc}"
                self.warning_ready.add(self.action_event_id)
            self.action_future = None
        session, event = self.state.current, self.event(self.current_event_id)
        if (self.actions and session and not session.paused and event and event.label == "distracting"
                and not event.closed_at and event.id not in self.action_attempted and not self.action_future
                and not self.restore_future and not self.review_future and self.snapshot
                and time.time() - self.snapshot.observed_at < 4 and self.frontmost_bundle == event.bundle):
            self.action_attempted.add(event.id)
            if self.state.settings.auto_close and self.close_receipt:
                self.close_receipt.valid = False
            self.action_event_id = event.id
            self.action_lease = Authorization()
            self.action_lease.set()
            self.action_message = "Checking the exact active page and keyboard focus…"
            self.action_future = self.action_pool.submit(self.actions.prepare, event.id,
                self.page_contexts[event.id], self.state.settings.auto_close, self.action_lease)

    def tick(self):
        if self.closed:
            return
        now, monotonic = time.time(), time.monotonic()
        gap = now - self.last_wall
        slept = gap - (monotonic - self.last_monotonic) > 2 or gap > 30
        self.last_wall, self.last_monotonic = now, monotonic
        session = self.state.current
        if slept and session and not session.paused:
            self.pause(self.state.last_heartbeat or session.started_at)
            self.error = "Session paused after sleep or a monitoring interruption. Resume when ready."
        if self.observation_future and self.observation_future.done():
            try:
                snapshot = self.observation_future.result()
                # Discard results started before a start/resume/settings boundary.
                if self.observation_context == self.context():
                    self.observe(snapshot)
            except Exception as exc:
                self.monitoring_message = f"Observation unavailable: {exc}"
                # An unknown foreground app is an uncertain boundary, not time on the previous page.
                from .models import Snapshot
                if self.observation_context == self.context():
                    self.observe(Snapshot("unknown", "Observation unavailable", error=str(exc)))
                    self.monitoring_message = f"Observation unavailable: {exc}"
            self.observation_future = None
        if self.connection_future and self.connection_future.done():
            try:
                self.model_choices = self.connection_future.result()
                self.connection_message = f"Connected: {len(self.model_choices)} available model(s) at {self.connection_base}"
            except Exception as exc:
                self.connection_message = str(exc)
            self.connection_future = None
        if self.model_future and self.model_future.done():
            try:
                decision = self.model_future.result()
            except Exception as exc:
                decision = Decision("uncertain", f"Local classification unavailable: {exc}", "unavailable")
            self.complete_classification(self.model_job, decision)
            self.model_future = self.model_job = None
        if self.queued_job and self.model_future is None:
            self.model_job, self.queued_job = self.queued_job, None
            _, task, page, settings = self.model_job
            self.model_future = self.model_pool.submit(self.client.classify, task, page, settings)
        session = self.state.current
        if self.observer and session and not session.paused and self.observation_future is None and monotonic >= self.next_observation:
            self.observation_context = self.context()
            self.observation_future = self.observation_pool.submit(self.observer.observe)
            self.next_observation = monotonic + 1.5
        if session and now - (self.state.last_heartbeat or 0) >= 10:
            self.state.last_heartbeat = now
            self.save()
        self.tick_actions()

    def context(self):
        session = self.state.current
        return (session.id if session else None, len(self.state.controls), repr(self.state.settings))

    def close(self):
        if self.closed:
            return
        self.end()
        if self.model_job:
            self.skip(self.model_job[0])
            self.save()
        self.closed = True
        self.cancel_actions(include_restore=True)
        self.observation_pool.shutdown()
        self.model_pool.shutdown()
        self.connection_pool.shutdown()
        self.action_pool.shutdown()
        self.review_pool.shutdown()
        self.store.close()
