"""No real key events: adversarial focus/identity tests with injected interfaces."""
from dataclasses import replace
from threading import Event
import unittest

from focusassistant.actions import Actions, CloseReceipt, after_removing, same_target
from focusassistant.models import Snapshot
from focusassistant.native import Focus


def page(**changes):
    target = Snapshot("com.google.Chrome", "Chrome", url="https://example.org/task", title="Task page", text="captured text",
                      window_id="window", tab_id="tab", document_id="document-uuid", process_id=42)
    return replace(target, **changes)


def topology(two=True):
    tabs = [{"key":"tab", "url":page().url, "title":page().title}]
    if two:
        tabs.append({"key":"next", "url":"https://example.org/next", "title":"Next page"})
    return [{"id":"window", "tabs":tabs}]


class Clock:
    def __init__(self):
        self.now = 0
    def __call__(self):
        return self.now
    def sleep(self, amount):
        self.now += amount


class Observer:
    def __init__(self, *pages):
        self.pages = list(pages)
    def observe(self, **_):
        if len(self.pages) > 1:
            return self.pages.pop(0)
        return self.pages[0]


class Desktop:
    def __init__(self, fullscreen=False, fail=False):
        self.fullscreen, self.fail = fullscreen, fail
        self.exits = 0
    def focused(self, target, **_):
        if self.fail:
            raise RuntimeError("A different window or modal has keyboard focus")
        return Focus(target.process_id, object(), self.fullscreen)
    def exit_fullscreen(self, _):
        self.fullscreen = False
        self.exits += 1


class Keyboard:
    def __init__(self):
        self.keys = []
    def hotkey(self, *keys, guard=None):
        if guard is not None and not guard():
            raise RuntimeError("Dispatch guard rejected the shortcut")
        self.keys.append(keys)


class Browser:
    def __init__(self, *states):
        self.states = list(states)
        self.activations = 0
        self.dom_exits = 0
    def topology(self, _):
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]
    def activate(self, _):
        self.activations += 1
    def exit_dom_fullscreen(self, _):
        self.dom_exits += 1


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.keys, self.desktop = Clock(), Keyboard(), Desktop()
        self.lease = Event()
        self.lease.set()

    def actions(self, observer, browser=None, desktop=None):
        return Actions(observer, desktop or self.desktop, self.keys, browser or Browser(topology()),
                       sleeper=self.clock.sleep, clock=self.clock)

    def test_same_page_content_and_document_required(self):
        self.assertTrue(same_target(page(), page(), content=True))
        for field, value in (("bundle","other"), ("window_id","other"), ("tab_id","other"),
                             ("url","https://example.org/new"), ("title","other"),
                             ("document_id","reloaded-same-url"), ("process_id",99), ("text","changed")):
            with self.subTest(field=field):
                self.assertFalse(same_target(page(), page(**{field:value}), content=True))

    def test_refuses_missing_safari_identity(self):
        target = page(bundle="com.apple.Safari", tab_id="1", document_id="")
        result = self.actions(Observer(target)).prepare("event",target,True,self.lease)
        self.assertFalse(result.close_sent)
        self.assertEqual(self.keys.keys, [])

    def test_wrong_app_or_tab_at_initial_check_never_gets_keys(self):
        for changed in (page(bundle="notes"), page(tab_id="different"), page(document_id="new-document"), page(text="changed")):
            result = self.actions(Observer(changed)).prepare("event",page(),True,self.lease)
            self.assertFalse(result.close_sent)
        self.assertEqual(self.keys.keys, [])

    def test_tab_switch_during_final_check_never_gets_keys(self):
        result = self.actions(Observer(page(),page(tab_id="different"))).prepare("event",page(),True,self.lease)
        self.assertFalse(result.close_sent)
        self.assertEqual(self.keys.keys, [])

    def test_modal_focus_refuses_keys(self):
        result = self.actions(Observer(page()),desktop=Desktop(fail=True)).prepare("event",page(),True,self.lease)
        self.assertFalse(result.close_sent)
        self.assertEqual(self.keys.keys, [])

    def test_cancelled_session_never_gets_keys(self):
        self.lease.clear()
        result = self.actions(Observer(page())).prepare("event",page(),True,self.lease)
        self.assertFalse(result.close_sent)
        self.assertEqual(self.keys.keys, [])

    def test_cancel_during_focus_check_never_gets_keys(self):
        parent = self
        class CancellingDesktop(Desktop):
            def focused(self, target, **kwargs):
                parent.lease.clear()
                return super().focused(target, **kwargs)
        result = self.actions(Observer(page()),desktop=CancellingDesktop()).prepare("event",page(),True,self.lease)
        self.assertFalse(result.close_sent)
        self.assertEqual(self.keys.keys, [])

    def test_slow_final_check_refused(self):
        parent = self
        class SlowObserver(Observer):
            def observe(self, **kwargs):
                if kwargs.get("metadata_only"):
                    parent.clock.sleep(1)
                return page()
        result = self.actions(SlowObserver(page())).prepare("event",page(),True,self.lease)
        self.assertFalse(result.close_sent)
        self.assertEqual(self.keys.keys, [])

    def test_last_native_dispatch_guard_can_still_veto_keys(self):
        class GuardedDesktop(Desktop):
            def dispatch_guard(self, *_):
                return False
        result = self.actions(Observer(page()),desktop=GuardedDesktop()).prepare("event",page(),True,self.lease)
        self.assertFalse(result.close_sent)
        self.assertEqual(self.keys.keys,[])

    def test_dependency_load_happens_before_target_validation(self):
        parent=self
        class LoadingKeyboard(Keyboard):
            def ready(self):
                parent.lease.clear()  # User paused while a slow import was running.
        self.keys=LoadingKeyboard()
        result=self.actions(Observer(page())).prepare("event",page(),True,self.lease)
        self.assertFalse(result.close_sent)
        self.assertEqual(self.keys.keys,[])

    def test_close_verifies_expected_transition_and_creates_receipt(self):
        before = topology()
        after = after_removing(before,page())
        next_page = page(tab_id="next",url="https://example.org/next",title="Next page",document_id="next-doc")
        result = self.actions(Observer(page(),page(),next_page),Browser(before,after)).prepare("event",page(),True,self.lease)
        self.assertEqual(self.keys.keys, [("command","w")])
        self.assertTrue(result.close_sent)
        self.assertIsNotNone(result.receipt)
        self.assertEqual(result.receipt.after_page, next_page)

    def test_unverified_close_does_not_offer_automatic_restore(self):
        result = self.actions(Observer(page()),Browser(topology())).prepare("event",page(),True,self.lease)
        self.assertTrue(result.close_sent)
        self.assertIsNone(result.receipt)
        self.assertEqual(len(self.keys.keys),1)

    def test_warning_exits_fullscreen_without_any_keyboard_shortcut(self):
        self.desktop.fullscreen = True
        result = self.actions(Observer(page())).prepare("event",page(),False,self.lease)
        self.assertTrue(result.warning_ready)
        self.assertEqual(self.desktop.exits,1)
        self.assertEqual(self.keys.keys,[])

    def test_warning_does_not_toggle_normal_window_into_fullscreen(self):
        result = self.actions(Observer(page())).prepare("event",page(),False,self.lease)
        self.assertTrue(result.warning_ready)
        self.assertEqual(self.desktop.exits,0)

    def test_dom_fullscreen_exit_is_explicit_and_checked(self):
        target=page(page_fullscreen=True)
        browser=Browser(topology())
        result=self.actions(Observer(target,target,page()),browser).prepare("event",target,False,self.lease)
        self.assertTrue(result.warning_ready)
        self.assertEqual(browser.dom_exits,1)
        self.assertEqual(self.keys.keys,[])

    def test_page_switch_during_fullscreen_transition_suppresses_warning(self):
        self.desktop.fullscreen=True
        result=self.actions(Observer(page(),page(),page(tab_id="other"))).prepare("event",page(),False,self.lease)
        self.assertFalse(result.warning_ready)
        self.assertEqual(self.keys.keys,[])

    def test_warning_native_safari_text_does_not_require_js_token(self):
        target=page(bundle="com.apple.Safari",document_id="")
        self.desktop.fullscreen=True
        self.actions(Observer(target)).prepare("event",target,False,self.lease)
        self.assertEqual(self.desktop.exits,1)

    def receipt(self):
        after = after_removing(topology(),page())
        remaining = page(tab_id="next",url="https://example.org/next",title="Next page",document_id="next-doc")
        return CloseReceipt("event",page(),after,remaining,0)

    def test_restore_only_after_focus_and_topology_checks(self):
        receipt=self.receipt()
        browser=Browser(receipt.after_topology)
        result=self.actions(Observer(receipt.after_page,receipt.after_page,page()),browser).restore(receipt,self.lease)
        self.assertTrue(result.restored)
        self.assertEqual(self.keys.keys,[("command","shift","t")])
        self.assertEqual(browser.activations,1)
        self.assertFalse(receipt.valid)

    def test_restore_refuses_another_closed_tab_in_history(self):
        receipt=self.receipt()
        result=self.actions(Observer(receipt.after_page),Browser([])).restore(receipt,self.lease)
        self.assertFalse(result.restored)
        self.assertEqual(self.keys.keys,[])

    def test_restore_refuses_expired_or_consumed_receipt(self):
        for consumed in (False,True):
            receipt=self.receipt()
            receipt.valid=not consumed
            self.clock.now=121
            result=self.actions(Observer(receipt.after_page),Browser(receipt.after_topology)).restore(receipt,self.lease)
            self.assertFalse(result.restored)
        self.assertEqual(self.keys.keys,[])

    def test_restore_refuses_changed_active_tab_or_process(self):
        for changed in (replace(self.receipt().after_page,tab_id="other"), replace(self.receipt().after_page,process_id=99)):
            receipt=self.receipt()
            result=self.actions(Observer(changed),Browser(receipt.after_topology)).restore(receipt,self.lease)
            self.assertFalse(result.restored)
        self.assertEqual(self.keys.keys,[])

    def test_restore_never_sends_keys_to_another_app(self):
        receipt=self.receipt()
        result=self.actions(Observer(page(bundle="notes")),Browser(receipt.after_topology)).restore(receipt,self.lease)
        self.assertFalse(result.restored)
        self.assertEqual(self.keys.keys,[])

    def test_restore_refuses_focus_switch_immediately_before_keys(self):
        receipt=self.receipt()
        result=self.actions(Observer(receipt.after_page,page(bundle="notes")),Browser(receipt.after_topology)).restore(receipt,self.lease)
        self.assertFalse(result.restored)
        self.assertEqual(self.keys.keys,[])


if __name__ == "__main__":
    unittest.main()
