"""Opt-in desktop smoke check. Synthetic data and temporary storage only.

Run from the project directory: python3 -m tests.ui_smoke
Use --hold to inspect the synthetic completed report before closing the window.
"""
import argparse
import tempfile
import time
import tkinter as tk

from focusassistant.controller import Controller
from focusassistant.models import Settings, Snapshot, OverrideVerdict
from focusassistant.storage import Store
from focusassistant.ui import App


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="focusassistant2-ui-") as directory:
        controller = Controller(Store(directory))
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *exc: errors.append(str(exc))
        app = App(root, controller)
        root.title("Focus Assistant · synthetic UI check")
        root.update()
        app.task_input.insert("1.0", "Research photosynthesis · UI fixture")
        app.start_button.invoke()
        assert controller.state.current is not None
        assert not app.override_buttons, "Everyday correction buttons must remain absent"
        controller.apply_settings(Settings(distracting_domains="example.org"))
        page = Snapshot("com.apple.Safari", "Safari", url="https://example.org/distraction", title="Example distracting page",
                        text="Synthetic local UI check", observed_at=time.time())
        controller.observe(page)
        app.render()
        root.update()
        assert app.warning and app.warning.winfo_exists(), "Warning window did not appear"
        app.dismiss_warning(app.warning_id)
        app.render()
        assert app.warning is None, "Dismissed warning reappeared"
        assert str(app.review_button.cget("state")) == "normal", "Correction application should be visible and accessible"
        app.open_review(controller.latest_page.id)
        root.update()
        dialogs = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Classification correction application"]
        assert len(dialogs) == 1, "Correction application did not open"
        dialogs[0].destroy()
        class ReviewClient:
            def review_override(self, *_):
                return OverrideVerdict(True, "Synthetic UI fixture approval")
        controller.client = ReviewClient()
        controller.request_override(controller.latest_page.id, "relevant", "This is the relevant photosynthesis evidence for my task.")
        deadline = time.monotonic() + 2
        while controller.review_future and time.monotonic() < deadline:
            controller.tick_actions()
            root.update()
            time.sleep(0.01)
        app.render()
        assert controller.latest_page.is_override
        assert app.page_label.cget("text") == "RELEVANT"
        app.pause_button.invoke()
        assert controller.state.current.paused
        app.pause_button.invoke()
        assert not controller.state.current.paused
        app.end_button.invoke()
        assert controller.state.current is None
        app.tabs.select(1)
        app.refresh_reports()
        root.update()
        assert app.current_report is not None
        assert app.timeline.get_children(), "Timeline is empty"
        app.rank_distractions.set(False)
        app.render_ranking()
        assert app.ranking.get_children(), "Activity ranking is empty"
        app.tabs.select(2)
        root.update()
        assert app.setting_vars["base_url"].get().startswith("http://127.0.0.1")
        app.tabs.select(1)
        root.update()
        assert not errors, errors
        assert not controller.error, controller.error
        print("PASS: desktop start, warning, dismissal, correction, pause/resume, end, report, range, rankings and settings", flush=True)
        print(f"Tk {root.tk.call('info', 'patchlevel')}; window {root.winfo_width()}×{root.winfo_height()}", flush=True)
        if args.hold:
            root.mainloop()
        else:
            app.close()


if __name__ == "__main__":
    main()
