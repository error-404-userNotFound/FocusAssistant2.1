from dataclasses import replace
import json
import tempfile
import time
from threading import Event
import unittest

from focusassistant.classification import LMStudioClient, cache_key
from focusassistant.controller import Controller
from focusassistant.models import Decision, OverrideVerdict, Settings, Snapshot
from focusassistant.storage import Store
from focusassistant.actions import ActionResult, CloseReceipt


def response(label):
    return {"choices":[{"finish_reason":"stop", "message":{"content":json.dumps({"label":label,"reason":"Fixture decision"})}}]}


class Transport(LMStudioClient):
    def __init__(self, *responses):
        self.responses = list(responses)
        self.payloads = []
    def request(self, base, path, payload=None, **_):
        self.payloads.append(payload)
        return self.responses.pop(0)


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.page = Snapshot("com.apple.Safari","Safari",url="https://example.org",title="Article",text="x"*24000)
        self.settings = Settings(model="fixture")

    def test_uncertain_then_decisive_uses_expanded_context(self):
        client=Transport(response("uncertain"),response("relevant"),response("distracting"))
        decision=client.classify("task",self.page,self.settings)
        self.assertEqual((decision.label,decision.attempts),("relevant",2))
        self.assertEqual(len(client.payloads),2)
        prompts=[p["messages"][1]["content"] for p in client.payloads]
        self.assertIn("x"*6000,prompts[0])
        self.assertNotIn("x"*6001,prompts[0])
        self.assertIn("x"*12000,prompts[1])

    def test_three_uncertain_responses_stop_and_explain(self):
        client=Transport(*[response("uncertain") for _ in range(4)])
        decision=client.classify("task",self.page,self.settings)
        self.assertEqual(decision.attempts,3)
        self.assertEqual(len(client.payloads),3)
        self.assertIn("three attempts",decision.reason)
        self.assertIn("x"*24000,client.payloads[2]["messages"][1]["content"])

    def test_decisive_first_response_no_retry(self):
        client=Transport(response("distracting"))
        self.assertEqual(client.classify("task",self.page,self.settings).attempts,1)
        self.assertEqual(len(client.payloads),1)

    def test_transport_or_parser_error_is_not_retried_as_uncertain(self):
        client=Transport({"choices":[]})
        result=client.classify("task",self.page,self.settings)
        self.assertEqual(result.source,"unavailable")
        self.assertEqual(len(client.payloads),1)

    def test_behavior_flags_do_not_invalidate_semantic_cache(self):
        self.assertEqual(cache_key("task",self.page,self.settings),
            cache_key("task",self.page,replace(self.settings,auto_close=True)))

    def test_override_review_accepts_only_explicit_boolean_approval(self):
        for approved, expected in ((True,True),(False,False),("true",False),(1,False)):
            result={"choices":[{"finish_reason":"stop","message":{"content":json.dumps({"approved":approved,"reason":"review"})}}]}
            client=Transport(result)
            verdict=client.review_override("task",self.page,self.settings,"distracting","relevant","Concrete explanation")
            self.assertEqual(verdict.approved,expected)

    def test_unavailable_or_truncated_review_denied(self):
        client=Transport({"choices":[{"finish_reason":"length","message":{"content":""}}]})
        self.assertFalse(client.review_override("task",self.page,self.settings,"distracting","relevant","reason").approved)

    def test_review_prompt_contains_task_page_request_and_original_reason(self):
        approved={"choices":[{"finish_reason":"stop","message":{"content":'{"approved":true,"reason":"supported"}'}}]}
        client=Transport(approved)
        client.review_override("study plants",self.page,self.settings,"distracting","relevant","This is plant research","Original rationale")
        system,user=client.payloads[0]["messages"]
        self.assertIn("untrusted data",system["content"])
        data=json.loads(user["content"])
        self.assertEqual(data["task"],"study plants")
        self.assertEqual(data["classification_reason"],"Original rationale")
        self.assertEqual(data["requested_label"],"relevant")
        self.assertEqual(data["explanation"],"This is plant research")
        self.assertEqual(len(data["page_text"]),24000)


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Controller(Store(self.temp.name))
        self.app.start("Research photosynthesis",now=100)
        self.app.apply_settings(Settings(distracting_domains="example.org"))
        self.page=Snapshot("com.apple.Safari","Safari",url="https://example.org",title="Article",text="Photosynthesis evidence",observed_at=101)
        self.app.observe(self.page)
        self.event=self.app.latest_page
        self.reason="This page explains photosynthesis, which directly supports the task."
    def tearDown(self):
        self.app.close()
        self.temp.cleanup()
    def enable(self):
        pass  # Reviews are ordinary UI; there is no hidden developer switch.
    def apply(self, approved=True):
        class Client:
            def review_override(self,*_):
                return OverrideVerdict(approved,"Fixture model review")
        self.app.client=Client()
        self.app.request_override(self.event.id,"relevant",self.reason)
        self.app.review_future.result(timeout=2)
        self.app.tick_actions()

    def test_review_available_without_developer_setting(self):
        self.assertFalse(hasattr(self.app.state.settings,"debug_corrections"))
        self.apply(False)
        self.assertIn("rejected",self.app.review_message)
    def test_short_explanation_rejected_before_model(self):
        self.enable()
        with self.assertRaisesRegex(ValueError,"20 characters"):
            self.app.request_override(self.event.id,"relevant","because")
    def test_model_rejection_does_not_change_label_cache_or_warning_count(self):
        self.enable()
        old_cache=self.app.state.cache.copy()
        self.apply(False)
        self.assertEqual(self.event.label,"distracting")
        self.assertFalse(self.event.is_override)
        self.assertEqual(self.app.state.cache,old_cache)
        self.assertIn("rejected",self.app.review_message)
    def test_approval_applies_correction_and_records_explanation(self):
        self.enable()
        self.apply()
        self.assertTrue(self.event.is_override)
        self.assertEqual(self.event.label,"relevant")
        self.assertIn(self.reason,self.event.override_note)
        self.assertEqual(self.app.state.cache[self.event.cache_key]["source"],"override")
        self.assertEqual(self.app.recent.count(102),0)
    def test_late_model_cannot_replace_approved_correction(self):
        self.enable()
        self.apply()
        self.app.complete_classification((self.event.id,"task",self.page,self.app.state.settings),Decision("distracting","late","model"))
        self.assertEqual(self.event.label,"relevant")
    def test_paused_session_cannot_submit_application(self):
        self.enable()
        self.app.pause(now=102)
        with self.assertRaisesRegex(ValueError,"unpaused"):
            self.app.request_override(self.event.id,"relevant",self.reason)
    def test_state_change_during_review_rejects_approval(self):
        self.enable()
        self.app.review_job=(self.event.id,"relevant",self.reason,self.app.context(),self.app.classification_signature(self.event))
        self.app.pause(now=102)
        self.app.finish_review(OverrideVerdict(True,"yes"))
        self.assertEqual(self.event.label,"distracting")
        self.assertIn("discarded",self.app.review_message)
    def test_close_metadata_change_does_not_discard_model_approval(self):
        self.app.review_job=(self.event.id,"relevant",self.reason,self.app.context(),self.app.classification_signature(self.event))
        self.event.closed_at=102
        self.app.finish_review(OverrideVerdict(True,"evidence supports it"))
        self.assertEqual(self.event.label,"relevant")
    def test_uncertain_model_cache_does_not_suppress_new_retries(self):
        self.app.state.settings.distracting_domains=""
        from focusassistant.classification import cache_key
        key=cache_key(self.app.state.current.task,self.page,self.app.state.settings)
        self.app.state.cache[key]={"label":"uncertain","reason":"old","source":"model"}
        self.app.invalidate_observation()
        self.app.observe(replace(self.page,observed_at=103))
        self.assertEqual(self.app.latest_page.source,"pending")

    def test_delayed_distracting_result_cannot_schedule_action_for_old_tab(self):
        calls=[]
        class ActionSpy:
            def prepare(self,*args):
                calls.append(args)
                return ActionResult("unexpected")
        self.app.actions=ActionSpy()
        self.app.state.settings.distracting_domains=""
        self.app.invalidate_observation()
        now=time.time()
        self.app.observe(replace(self.page,observed_at=now))
        old=self.app.queued_job
        self.app.observe(replace(self.page,url="https://example.org/new-tab",observed_at=now+0.01))
        self.app.complete_classification(old,Decision("distracting","late result","model"))
        self.app.tick_actions()
        self.assertEqual(calls,[])

    def test_pause_revokes_pending_keyboard_action_lease(self):
        entered,release=Event(),Event()
        dispatches=[]
        class ActionSpy:
            def prepare(self,event_id,target,auto_close,lease):
                entered.set()
                release.wait(2)
                if lease.is_set():
                    dispatches.append(event_id)
                return ActionResult("cancelled")
        self.app.actions=ActionSpy()
        self.app.invalidate_observation()
        self.app.observe(replace(self.page,observed_at=time.time()))
        self.app.tick_actions()
        self.assertTrue(entered.wait(1))
        self.app.pause()
        release.set()
        self.app.action_future.result(timeout=2)
        self.assertEqual(dispatches,[])

    def test_approved_closed_page_schedules_guarded_restore(self):
        calls=[]
        class ActionSpy:
            def restore(self,receipt,lease):
                calls.append((receipt.event_id,lease.is_set()))
                return ActionResult("restored",restored=True)
        self.app.actions=ActionSpy()
        self.app.close_receipt=CloseReceipt(self.event.id,self.page,[],self.page,time.monotonic())
        self.event.closed_at=time.time()
        self.app.review_job=(self.event.id,"relevant",self.reason,self.app.context(),self.app.classification_signature(self.event))
        self.app.finish_review(OverrideVerdict(True,"Task evidence supports correction"))
        self.app.restore_future.result(timeout=2)
        self.assertEqual(calls,[(self.event.id,True)])


if __name__=="__main__":
    unittest.main()
