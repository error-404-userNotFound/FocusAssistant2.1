import argparse
from pathlib import Path
import sys


def main():
    from . import __version__
    parser = argparse.ArgumentParser(description="Focus Assistant · extension-free macOS focus sessions")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--diagnose", action="store_true", help="Check installation without opening a window, reading pages or sending keys")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / "Library/Application Support/FocusAssistant")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("The desktop app requires macOS. Core tests can run without browser access.")
    if args.diagnose:
        from .diagnostics import main as diagnose
        return diagnose()
    try:
        import tkinter as tk
    except ImportError:
        print("Tk is missing. Use a Python 3.11+ macOS installation with Tk support (see README).", file=sys.stderr)
        return 1
    from tkinter import messagebox
    from .browsers import BrowserObserver
    from .actions import Actions
    from .controller import Controller
    from .storage import Store, StorageError
    from .ui import App
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Cannot start the desktop interface: {exc}", file=sys.stderr)
        return 1
    root.withdraw()
    try:
        store = Store(args.data_dir)
        observer = BrowserObserver()
        controller = Controller(store, observer, actions=Actions(observer))
        App(root, controller)
    except (StorageError, OSError) as exc:
        messagebox.showerror("Focus Assistant", str(exc), parent=root)
        root.destroy()
        return 1
    root.deiconify()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
