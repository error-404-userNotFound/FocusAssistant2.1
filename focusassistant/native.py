"""Lazy macOS Accessibility checks. No permission is granted automatically."""
from dataclasses import dataclass


@dataclass
class Focus:
    pid: int
    window: object
    fullscreen: bool


class MacDesktop:
    def ready(self):
        self.modules()
        import Quartz

    def modules(self):
        try:
            import AppKit
            import ApplicationServices as AX
        except ImportError as exc:
            raise RuntimeError("Install the macOS dependencies with python3 -m pip install -e .") from exc
        return AppKit, AX

    @staticmethod
    def value(AX, element, attribute, required=True):
        error, value = AX.AXUIElementCopyAttributeValue(element, attribute, None)
        if error and required:
            raise RuntimeError(f"Accessibility could not read {attribute} ({error}).")
        return None if error else value

    def focused(self, target, allow_no_window=False):
        AppKit, AX = self.modules()
        import Quartz
        flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateCombinedSessionState)
        if flags & (Quartz.kCGEventFlagMaskShift | Quartz.kCGEventFlagMaskControl |
                    Quartz.kCGEventFlagMaskAlternate | Quartz.kCGEventFlagMaskCommand):
            raise RuntimeError("Release modifier keys before automatic browser control.")
        if not AX.AXIsProcessTrusted():
            raise RuntimeError("Accessibility permission is required for safe browser control. Grant it to the Python launcher in System Settings.")
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None or app.bundleIdentifier() != target.bundle:
            raise RuntimeError("The classified browser is no longer in focus.")
        pid = app.processIdentifier()
        if target.process_id and pid != target.process_id:
            raise RuntimeError("The browser process changed.")
        element = AX.AXUIElementCreateApplication(pid)
        AX.AXUIElementSetMessagingTimeout(element, 0.3)
        window = self.value(AX, element, "AXFocusedWindow", required=not allow_no_window)
        if window is None and allow_no_window:
            return Focus(pid, None, False)
        if self.value(AX, window, "AXSubrole") != "AXStandardWindow":
            raise RuntimeError("A dialog or non-document browser window has focus.")
        if self.value(AX, window, "AXModal", required=False):
            raise RuntimeError("A modal dialog has focus.")
        focused = self.value(AX, element, "AXFocusedUIElement")
        focused_window = self.value(AX, focused, "AXWindow", required=False)
        if focused_window is not None and focused_window != window:
            raise RuntimeError("Keyboard focus belongs to another window.")
        role = self.value(AX, focused, "AXRole")
        if role in ("AXMenu", "AXMenuItem", "AXMenuBar", "AXSheet", "AXDialog"):
            raise RuntimeError("A menu or sheet has keyboard focus.")
        title = self.value(AX, window, "AXTitle") or ""
        if target.title and not (title == target.title or title.startswith(target.title + " ")):
            raise RuntimeError("The focused Accessibility window does not match the classified page title.")
        document = self.value(AX, window, "AXDocument", required=False)
        if document and target.url and str(document) != target.url:
            raise RuntimeError("The focused window's document URL changed.")
        fullscreen = bool(self.value(AX, window, "AXFullScreen"))
        return Focus(pid, window, fullscreen)

    def exit_fullscreen(self, focus):
        _, AX = self.modules()
        error = AX.AXUIElementSetAttributeValue(focus.window, "AXFullScreen", False)
        if error:
            raise RuntimeError(f"macOS refused to exit full screen ({error}).")

    def dispatch_guard(self, target, focus, lease):
        # Fast final native check, after imports and immediately before key dispatch.
        AppKit, AX = self.modules()
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if not lease.is_set() or app is None or app.bundleIdentifier() != target.bundle or app.processIdentifier() != focus.pid:
            return False
        import Quartz
        flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateCombinedSessionState)
        if flags & (Quartz.kCGEventFlagMaskShift | Quartz.kCGEventFlagMaskControl |
                    Quartz.kCGEventFlagMaskAlternate | Quartz.kCGEventFlagMaskCommand):
            return False
        application = AX.AXUIElementCreateApplication(focus.pid)
        AX.AXUIElementSetMessagingTimeout(application, 0.2)
        current = self.value(AX, application, "AXFocusedWindow", required=False)
        if current != focus.window:
            return False
        if current is None:
            return True  # Verified browser with no windows: restore-only path.
        element = self.value(AX, application, "AXFocusedUIElement")
        if self.value(AX, element, "AXRole") in ("AXMenu", "AXMenuItem", "AXMenuBar", "AXSheet", "AXDialog"):
            return False
        title = self.value(AX, current, "AXTitle") or ""
        return (not self.value(AX, current, "AXModal", required=False) and
                (not target.title or title == target.title or title.startswith(target.title + " ")))

    def place_reminder(self, title="Focus reminder"):
        # Called by Tk's main thread only, after the browser exits full screen.
        AppKit, _ = self.modules()
        for window in AppKit.NSApplication.sharedApplication().windows():
            if window.title() == title:
                window.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
                                              AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary |
                                              AppKit.NSWindowCollectionBehaviorTransient)
                window.setHidesOnDeactivate_(False)
                window.setLevel_(AppKit.NSFloatingWindowLevel)
                window.orderFrontRegardless()


class PyAutoGUIKeyboard:
    def __init__(self):
        self.module = None

    def ready(self):
        if self.module is None:
            try:
                import pyautogui
            except ImportError as exc:
                raise RuntimeError("PyAutoGUI is not installed. Run python3 -m pip install -e .") from exc
            self.module = pyautogui

    def hotkey(self, *keys, guard=None):
        self.ready()
        if guard is not None and not guard():
            raise RuntimeError("Focus or authorization changed at keyboard dispatch.")
        # Preserve PyAutoGUI's corner fail-safe. No screenshots or mouse moves.
        self.module.FAILSAFE = True
        self.module.hotkey(*keys, interval=0)
