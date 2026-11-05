"""Fail-closed, fresh-target gating around global browser shortcuts.

Global key events and browser UI changes cannot be made atomic on macOS.
These checks deliberately refuse action when identity/focus cannot be proved.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import time

from .native import MacDesktop, PyAutoGUIKeyboard


def digest(text):
    return hashlib.sha256(text[:24000].encode()).hexdigest()


def same_target(expected, actual, content=False, require_document=True):
    # A per-document token is required even for Chrome: same URL after reload
    # must not inherit permission from a previously classified document.
    fields = ("bundle", "window_id", "tab_id", "url", "title", "document_id", "process_id")
    return ((bool(expected.document_id) or not require_document) and bool(expected.window_id) and bool(expected.tab_id)
            and all(getattr(expected, k) == getattr(actual, k) for k in fields)
            and (not content or digest(expected.text) == digest(actual.text)))


class BrowserControl:
    def call(self, bundle, action="topology", **kwargs):
        script = Path(__file__).with_name("browser_control.js")
        result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", str(script),
            json.dumps(dict(bundle=bundle, action=action, **kwargs))], capture_output=True, text=True, timeout=4)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout)

    def topology(self, bundle):
        return self.call(bundle)

    def activate(self, target):
        self.call(target.bundle, "activate", window_id=target.window_id)

    def exit_dom_fullscreen(self, target):
        if not target.document_id:
            raise RuntimeError("Cannot verify the full-screen document identity.")
        self.call(target.bundle, "exit_dom_fullscreen", window_id=target.window_id, tab_id=target.tab_id,
                  url=target.url, document_id=target.document_id)


def topology_signature(topology, bundle):
    return tuple(sorted((w["id"], tuple((t["key"] if bundle == "com.google.Chrome" else "", t["url"], t["title"])
                                      for t in w["tabs"])) for w in topology))


def after_removing(topology, target):
    result = json.loads(json.dumps(topology))
    windows = [w for w in result if w["id"] == target.window_id]
    if len(windows) != 1:
        raise RuntimeError("The classified window is missing from browser state.")
    tabs = windows[0]["tabs"]
    matches = [t for t in tabs if t["key"] == target.tab_id and t["url"] == target.url and t["title"][:500] == target.title]
    if len(matches) != 1:
        raise RuntimeError("The classified tab is missing or ambiguous.")
    tabs.remove(matches[0])
    return [w for w in result if w["tabs"]]


@dataclass
class CloseReceipt:
    event_id: str
    target: object
    after_topology: object
    after_page: object
    at: float
    valid: bool = True


@dataclass
class ActionResult:
    message: str
    receipt: CloseReceipt | None = None
    warning_ready: bool = False
    restored: bool = False
    close_sent: bool = False


class Actions:
    def __init__(self, observer, desktop=None, keyboard=None, browser=None, sleeper=time.sleep, clock=time.monotonic):
        self.observer = observer
        self.desktop = desktop or MacDesktop()
        self.keyboard = keyboard or PyAutoGUIKeyboard()
        self.browser = browser or BrowserControl()
        self.sleep, self.clock = sleeper, clock

    def validate(self, target, lease, content=False, require_document=True):
        if not lease.is_set():
            raise RuntimeError("Action cancelled by a session, settings, page or correction change.")
        page = self.observer.observe(metadata_only=not content)
        if not same_target(target, page, content, require_document):
            raise RuntimeError("Active browser/tab/document/content no longer matches the classified page.")
        focus = self.desktop.focused(page)
        if not lease.is_set():
            raise RuntimeError("Action authorization expired.")
        return page, focus

    def prepare(self, event_id, target, auto_close, lease):
        sent = False
        try:
            if hasattr(self.desktop, "ready"):
                self.desktop.ready()
            if auto_close and hasattr(self.keyboard, "ready"):
                self.keyboard.ready()
            self.validate(target, lease, content=True, require_document=auto_close)
            if auto_close:
                before = self.browser.topology(target.bundle)
                expected = after_removing(before, target)
                # Invalidate a slow check rather than using it as authority later.
                start = self.clock()
                _, focus = self.validate(target, lease)
                if self.clock() - start > 0.75 or not lease.is_set():
                    raise RuntimeError("The final focus check was too slow or was cancelled.")
                self.keyboard.hotkey("command", "w", guard=lambda: lease.is_set() and (
                    not hasattr(self.desktop, "dispatch_guard") or self.desktop.dispatch_guard(target, focus, lease)))
                sent = True
                deadline = self.clock() + 2
                while self.clock() < deadline:
                    actual = self.browser.topology(target.bundle)
                    if topology_signature(actual, target.bundle) == topology_signature(expected, target.bundle):
                        page = self.observer.observe(metadata_only=True)
                        return ActionResult("Closed the verified active distracting tab.",
                            CloseReceipt(event_id, target, actual, page, self.clock()), close_sent=True)
                    self.sleep(0.1)
                raise RuntimeError("Close was requested, but the expected browser state could not be verified; automatic recovery is disabled.")
            current_page, focus = self.validate(target, lease, require_document=False)
            if current_page.page_fullscreen:
                self.browser.exit_dom_fullscreen(target)
                deadline = self.clock() + 3
                while self.clock() < deadline:
                    self.sleep(0.15)
                    current_page, focus = self.validate(target, lease, require_document=False)
                    if not current_page.page_fullscreen:
                        break
                else:
                    raise RuntimeError("The page did not finish leaving DOM full screen.")
            if focus.fullscreen:
                # Explicitly set false. Never blindly toggle Ctrl+Command+F.
                self.desktop.exit_fullscreen(focus)
                deadline = self.clock() + 4
                while self.clock() < deadline:
                    self.sleep(0.15)
                    _, current = self.validate(target, lease, require_document=False)
                    if not current.fullscreen:
                        return ActionResult("Exited full screen; showing the reminder on the active desktop.", warning_ready=True)
                raise RuntimeError("The browser did not finish exiting full screen.")
            return ActionResult("Showing the focus reminder.", warning_ready=True)
        except Exception as exc:
            return ActionResult(str(exc), warning_ready=False, close_sent=sent)

    def restore(self, receipt, lease):
        try:
            if hasattr(self.desktop, "ready"):
                self.desktop.ready()
            if hasattr(self.keyboard, "ready"):
                self.keyboard.ready()
            if not receipt.valid or self.clock() - receipt.at > 120 or not lease.is_set():
                raise RuntimeError("The automatic restore window has expired or was cancelled.")
            signature = topology_signature(receipt.after_topology, receipt.target.bundle)
            if topology_signature(self.browser.topology(receipt.target.bundle), receipt.target.bundle) != signature:
                raise RuntimeError("Browser tabs/windows changed after the automatic close. Refusing a potentially unrelated reopen.")
            self.browser.activate(receipt.target)
            # Activation is asynchronous; allow a bounded transition, never send
            # restore keys while another app is foreground.
            deadline = self.clock() + 2
            while True:
                page = self.observer.observe(metadata_only=True)
                if page.bundle == receipt.target.bundle:
                    break
                if self.clock() >= deadline or not lease.is_set():
                    raise RuntimeError("The intended browser could not be brought into focus.")
                self.sleep(0.1)
            if receipt.target.process_id and page.process_id != receipt.target.process_id:
                raise RuntimeError("The browser was restarted after the close; refusing restore.")
            if receipt.after_topology:
                expected = receipt.after_page
                if not (expected.bundle == page.bundle and expected.window_id == page.window_id
                        and expected.tab_id == page.tab_id and expected.url == page.url and expected.title == page.title):
                    raise RuntimeError("The post-close active tab changed. Refusing the restore shortcut.")
            self.desktop.focused(page, allow_no_window=not bool(receipt.after_topology))
            if topology_signature(self.browser.topology(receipt.target.bundle), receipt.target.bundle) != signature or not lease.is_set():
                raise RuntimeError("Browser state changed during the restore check.")
            # Fresh foreground gate after the topology call and before key events.
            started = self.clock()
            final = self.observer.observe(metadata_only=True)
            if any(getattr(final,k) != getattr(page,k) for k in ("bundle","window_id","tab_id","url","title","document_id","process_id")):
                raise RuntimeError("Focus changed immediately before restore.")
            focus = self.desktop.focused(final, allow_no_window=not bool(receipt.after_topology))
            if not lease.is_set() or self.clock() - started > 0.75:
                raise RuntimeError("Restore cancelled.")
            receipt.valid = False  # Consume before dispatch: never repeat the shortcut.
            self.keyboard.hotkey("command", "shift", "t", guard=lambda: lease.is_set() and (
                not hasattr(self.desktop, "dispatch_guard") or self.desktop.dispatch_guard(final, focus, lease)))
            deadline = self.clock() + 2
            while self.clock() < deadline:
                restored = self.observer.observe(metadata_only=True)
                if restored.bundle == receipt.target.bundle and restored.url == receipt.target.url and restored.title == receipt.target.title:
                    return ActionResult("Reopened the approved page in its browser.", restored=True)
                self.sleep(0.1)
            raise RuntimeError("Restore shortcut was sent, but the recovered page could not be verified. No further keys were sent.")
        except Exception as exc:
            receipt.valid = False
            return ActionResult(str(exc))
