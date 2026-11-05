"""Tk desktop UI; no browser window, extension, or web server is used for the UI."""
from datetime import datetime
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .models import LABELS, Settings
from . import __version__

COLORS = {"relevant": "#267346", "uncertain": "#626b79", "distracting": "#b15e13"}


def clock(seconds):
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def date_string(value):
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def parse_date(value):
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").timestamp()


class App:
    def __init__(self, root, controller):
        self.root, self.controller = root, controller
        self.closed = False
        self.warning = None
        self.warning_id = None
        self.dismissed = set()
        self.page_signature = None
        self.report_signature = None
        self.current_report = None
        self.selected_session_id = None
        self.session_ids = []
        self.last_error = None
        root.title("Focus Assistant")
        root.geometry("980x810")
        root.minsize(840, 720)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.configure("Title.TLabel", font=("Helvetica", 24, "bold"))
        style.configure("Heading.TLabel", font=("Helvetica", 14, "bold"))
        style.configure("Timer.TLabel", font=("Menlo", 22))
        style.configure("Muted.TLabel", foreground="#626b79")
        style.configure("Card.TLabelframe", padding=14)
        style.configure("TButton", padding=(9, 5))
        style.configure("Treeview", rowheight=27)
        self.install_menus()
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=16)
        focus_shell, self.focus = self.scroll_page(self.tabs)
        self.reports = ttk.Frame(self.tabs, padding=16)
        settings_shell, self.settings_tab = self.scroll_page(self.tabs)
        for frame, name in ((focus_shell, "Focus"), (self.reports, "Reports"), (settings_shell, "Settings")):
            self.tabs.add(frame, text=name)
        self.build_focus()
        self.build_reports()
        self.build_settings()
        self.tabs.bind("<<NotebookTabChanged>>", lambda _: self.refresh_reports())
        root.bind("<Command-q>", lambda _: self.close())
        root.bind("<Command-space>", lambda _: self.call(self.controller.pause))
        self.refresh()

    @staticmethod
    def scroll_page(parent):
        shell = ttk.Frame(parent)
        canvas = tk.Canvas(shell, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(canvas, padding=20)
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        def resized(event):
            canvas.itemconfigure(window, width=event.width)
            def wrap_children(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Label) and int(child.cget("wraplength") or 0) > 0:
                        child.configure(wraplength=max(280, event.width - 100))
                    wrap_children(child)
            wrap_children(content)
        canvas.bind("<Configure>", resized)
        return shell, content

    def install_menus(self):
        menu = tk.Menu(self.root)
        app = tk.Menu(menu, tearoff=False)
        app.add_command(label="About Focus Assistant", command=lambda: messagebox.showinfo(
            "Focus Assistant", f"Focus Assistant {__version__}\nExtension-free Safari and Chrome observation.\nInference uses your configured local server.", parent=self.root))
        app.add_separator()
        app.add_command(label="Quit", accelerator="⌘Q", command=self.close)
        menu.add_cascade(label="Focus Assistant", menu=app)
        edit = tk.Menu(menu, tearoff=False)
        for label, event in (("Undo", "<<Undo>>"), ("Cut", "<<Cut>>"), ("Copy", "<<Copy>>"), ("Paste", "<<Paste>>"), ("Select All", "<<SelectAll>>")):
            edit.add_command(label=label, command=lambda e=event: self.root.focus_get().event_generate(e) if self.root.focus_get() else None)
        menu.add_cascade(label="Edit", menu=edit)
        self.root.configure(menu=menu)

    @staticmethod
    def text(parent, value="", **kwargs):
        label = ttk.Label(parent, text=value, wraplength=790, justify="left", **kwargs)
        label.pack(anchor="w", pady=(0, 8))
        return label

    def card(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, style="Card.TLabelframe")
        frame.pack(fill="x", pady=(0, 16))
        return frame

    def build_focus(self):
        self.text(self.focus, "Focus Assistant", style="Title.TLabel")
        self.text(self.focus, "Stay with your task. Private, local classification for Safari and Chrome.", style="Muted.TLabel")
        session = self.card(self.focus, "Focus session")
        row = ttk.Frame(session)
        row.pack(fill="x", pady=(0, 8))
        self.session_status = ttk.Label(row, style="Heading.TLabel")
        self.session_status.pack(side="left")
        self.timer = ttk.Label(row, text="00:00", style="Timer.TLabel")
        self.timer.pack(side="right")
        self.task_input = tk.Text(session, height=3, wrap="word", font=("Helvetica", 13), relief="solid", borderwidth=1, undo=True)
        self.task_input.pack(fill="x", pady=(0, 10))
        self.task_input.insert("1.0", "")
        self.task_hint = self.text(session, "Describe your task, for example: Research causes of the French Revolution.", style="Muted.TLabel")
        buttons = ttk.Frame(session)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="Start focus session", command=lambda: self.call(self.start_session))
        self.start_button.pack(side="left")
        self.pause_button = ttk.Button(buttons, text="Pause", command=lambda: self.call(self.controller.pause))
        self.pause_button.pack(side="left", padx=8)
        self.end_button = ttk.Button(buttons, text="End session", command=lambda: self.call(self.controller.end))
        self.end_button.pack(side="left")
        page = self.card(self.focus, "Latest browser page")
        self.page_title = self.text(page, "Start a session, then switch to Safari or Chrome.", style="Heading.TLabel")
        self.page_host = self.text(page, "", style="Muted.TLabel")
        self.page_label = self.text(page, "UNCERTAIN")
        self.page_reason = self.text(page, "Page text is sent only to the local model. Other apps are recorded by name.")
        self.intervention = self.text(page, "", foreground=COLORS["distracting"])
        self.override_buttons = []
        corrections = ttk.Frame(page)
        corrections.pack(fill="x")
        self.review_button = ttk.Button(corrections, text="Request correction…", command=lambda: self.call(self.open_review))
        self.review_button.pack(side="left")
        self.closed_review_button = ttk.Button(corrections, text="Review last auto-closed page…", command=lambda: self.call(
            lambda: self.open_review(self.controller.close_receipt.event_id if self.controller.close_receipt else None)))
        self.closed_review_button.pack(side="left", padx=(8, 0))
        self.review_status = self.text(page, "", style="Muted.TLabel")
        connection = self.card(self.focus, "Status")
        self.monitor_status = self.text(connection, "", style="Muted.TLabel")
        self.connection_status = self.text(connection, "", style="Muted.TLabel")
        self.error_status = self.text(connection, "", foreground="#a43c2f")
        self.action_status = self.text(connection, "", style="Muted.TLabel")
        self.text(self.focus, "Only the active browser page is classified. Auto-close is optional in Settings.\nClassification corrections require a written reason and local-model approval.", style="Muted.TLabel")

    def build_settings(self):
        self.text(self.settings_tab, "Settings", style="Title.TLabel")
        frame = self.card(self.settings_tab, "Local model server (LM Studio / Ollama)")
        self.setting_vars = {name: (tk.BooleanVar if isinstance(getattr(self.controller.state.settings, name), bool) else tk.StringVar)(
            value=getattr(self.controller.state.settings, name)) for name in Settings.__dataclass_fields__}
        self.setting_entry(frame, "Server address", "base_url")
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text="Available model", width=21).pack(side="left")
        self.model_combo = ttk.Combobox(row, textvariable=self.setting_vars["model"])
        self.model_combo.pack(side="left", fill="x", expand=True)
        self.check_button = ttk.Button(row, text="Check connection", command=lambda: self.call(
            lambda: self.controller.check_connection(self.setting_vars["base_url"].get())))
        self.check_button.pack(side="left", padx=(8, 0))
        self.settings_connection = self.text(frame, "Connection not checked", style="Muted.TLabel")
        self.text(frame, "Start LM Studio, Ollama or another local OpenAI-compatible server and load a model. Only loopback addresses are accepted.", style="Muted.TLabel")
        rules = self.card(self.settings_tab, "Simple classification rules")
        for label, key in (("Relevant domains", "relevant_domains"), ("Distracting domains", "distracting_domains"),
                           ("Relevant keywords", "relevant_keywords"), ("Distracting keywords", "distracting_keywords")):
            self.setting_entry(rules, label, key)
        self.text(rules, "Separate entries with commas. Domain rules include subdomains; keyword matching ignores case and accents.", style="Muted.TLabel")
        behavior = self.card(self.settings_tab, "Distraction response")
        ttk.Checkbutton(behavior, text="Automatically close the verified active distracting tab (⌘W)",
                        variable=self.setting_vars["auto_close"]).pack(anchor="w", pady=(0, 8))
        self.text(behavior, "Off by default. Closing requires PyAutoGUI, Accessibility access, and a verified document identity. JavaScript from Apple Events must be enabled in either browser for automatic closing. A close may lose unsaved page data.")
        self.text(behavior, "With auto-close off, a distracting full-screen browser is taken out of full screen before its desktop reminder appears. Only the focused classified page may trigger this.", style="Muted.TLabel")
        ttk.Button(self.settings_tab, text="Save settings", command=lambda: self.call(self.save_settings)).pack(anchor="w", pady=(0, 16))
        access = self.card(self.settings_tab, "Browser access · no extension required")
        self.text(access, "macOS may ask the app launching Python for permission to control Safari and Google Chrome. Allow those browser Automation requests to read active pages.")
        self.text(access, "Safari can read native page text directly. For Chrome page text, enable View → Developer → Allow JavaScript from Apple Events. Without it, explicit domain rules still work; other pages remain uncertain.")
        self.text(access, "Automation permission allows page observation. Accessibility permission is additionally required for focused-window verification, full-screen exit and keyboard control. Screen Recording is not used.", style="Muted.TLabel")
        self.text(self.settings_tab, f"Saved sessions: {self.controller.store.path}", style="Muted.TLabel")

    def setting_entry(self, parent, label, key):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text=label, width=21).pack(side="left")
        ttk.Entry(row, textvariable=self.setting_vars[key]).pack(side="left", fill="x", expand=True)

    def build_reports(self):
        self.text(self.reports, "Session reports", style="Title.TLabel")
        self.session_combo = ttk.Combobox(self.reports, state="readonly")
        self.session_combo.pack(fill="x", pady=(0, 12))
        self.session_combo.bind("<<ComboboxSelected>>", self.select_report)
        self.report_task = self.text(self.reports, "Complete a session to generate a report.", style="Heading.TLabel")
        self.report_dates = self.text(self.reports, "", style="Muted.TLabel")
        self.report_totals = self.text(self.reports, "", style="Heading.TLabel")
        range_box = self.card(self.reports, "Selected time range")
        self.range_start, self.range_end = tk.StringVar(), tk.StringVar()
        row = ttk.Frame(range_box)
        row.pack(fill="x")
        for label, var in (("From", self.range_start), ("To", self.range_end)):
            ttk.Label(row, text=label).pack(side="left", padx=(0, 6))
            ttk.Entry(row, textvariable=var, width=21).pack(side="left", padx=(0, 12))
        ttk.Button(row, text="Apply range", command=lambda: self.call(self.apply_range)).pack(side="left")
        self.range_totals = self.text(range_box, "Use YYYY-MM-DD HH:MM:SS in your local time zone.", style="Muted.TLabel")
        self.rank_distractions = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.reports, text="Rank by distracting time", variable=self.rank_distractions, command=self.render_ranking).pack(anchor="w", pady=(0, 8))
        self.ranking = self.tree(self.reports, ("Site or app", "Time"), height=4, widths=(630, 130))
        self.text(self.reports, "Timeline", style="Heading.TLabel")
        self.timeline = self.tree(self.reports, ("Started", "Activity", "Classification", "Duration"), height=7, widths=(150, 360, 130, 100))
        self.report_warnings = self.text(self.reports, "", foreground="#a43c2f")

    @staticmethod
    def tree(parent, columns, height, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=(0, 10))
        view = ttk.Treeview(frame, columns=columns, show="headings", height=height)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=view.yview)
        view.configure(yscrollcommand=scroll.set)
        view.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for column, width in zip(columns, widths):
            view.heading(column, text=column)
            view.column(column, width=width, minwidth=75)
        return view

    def start_session(self):
        self.controller.start(self.task_input.get("1.0", "end"))

    def save_settings(self):
        self.controller.apply_settings(Settings(**{k: v.get() if k == "auto_close" else v.get().strip()
                                                  for k, v in self.setting_vars.items()}))
        self.settings_connection.configure(text="Settings saved. " + self.controller.connection_message)

    def correct_latest(self, label):
        # The ordinary UI submits an application, never applies a label directly.
        self.open_review()

    def open_review(self, event_id=None):
        controller = self.controller
        session = controller.state.current
        if not session or session.paused:
            raise ValueError("An active, unpaused session is required.")
        events = [e for e in reversed(controller.state.pages) if e.session_id == session.id and e.id in controller.page_contexts]
        if not events:
            raise ValueError("No captured pages are available to review.")
        controller.cancel_actions()
        dialog = tk.Toplevel(self.root)
        dialog.title("Classification correction application")
        dialog.transient(self.root)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Apply for a classification correction", style="Heading.TLabel").pack(anchor="w", pady=(0, 10))
        selector = ttk.Combobox(frame, state="readonly", width=65,
            values=[f"{e.label.upper()} · {'AUTO-CLOSED · ' if e.closed_at else ''}{e.title[:65]}" for e in events])
        selector.pack(fill="x", pady=(0, 10))
        selected_index = next((i for i, e in enumerate(events) if e.id == event_id), 0)
        selector.current(selected_index)
        label = tk.StringVar(value="relevant")
        ttk.Combobox(frame, textvariable=label, values=LABELS, state="readonly").pack(anchor="w", pady=(0, 10))
        ttk.Label(frame, text="Explain concretely how the page relates to your task (at least 20 characters).", wraplength=540).pack(anchor="w")
        explanation = tk.Text(frame, height=5, width=65, wrap="word")
        explanation.pack(fill="x", pady=10)
        status = ttk.Label(frame, text=controller.review_message, wraplength=540)
        status.pack(anchor="w", pady=(0, 10))
        deadline = time.monotonic() + 5
        def submit():
            selected = events[selector.current()]
            try:
                if time.monotonic() < deadline:
                    raise ValueError("Wait for the confirmation delay.")
                controller.request_override(selected.id, label.get(), explanation.get("1.0", "end"))
            except ValueError as exc:
                messagebox.showerror("Correction application", str(exc), parent=dialog)
        button = ttk.Button(frame, text="Submit for local-model review", command=submit)
        button.pack(anchor="w")
        def update():
            if not dialog.winfo_exists():
                return
            remaining = max(0, int(deadline - time.monotonic() + 0.999))
            button.configure(text=f"Please wait {remaining}s…" if remaining else "Submit for local-model review",
                             state="disabled" if remaining or controller.review_future else "normal")
            status.configure(text=controller.review_message)
            dialog.after(200, update)
        update()

    def call(self, action):
        try:
            action()
            self.render()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Focus Assistant", str(exc), parent=self.root)

    def totals_text(self, total):
        return "     ".join(f"{label.title()}  {clock(total[label])}" for label in LABELS)

    def refresh_reports(self):
        completed = sorted((s for s in self.controller.state.sessions if s.ended_at is not None), key=lambda s: s.started_at, reverse=True)
        signature = (tuple(s.id for s in completed), self.controller.state.revision)
        if signature == self.report_signature:
            return
        self.report_signature = signature
        self.session_ids = [s.id for s in completed]
        self.session_combo.configure(values=[f"{date_string(s.started_at)} · {s.task[:80]}" for s in completed])
        if not completed:
            return
        if self.selected_session_id not in self.session_ids:
            self.session_combo.current(0)
            self.select_report()
        else:
            self.session_combo.current(self.session_ids.index(self.selected_session_id))
            self.select_report(preserve_range=True)

    def select_report(self, _event=None, preserve_range=False):
        index = self.session_combo.current()
        if index < 0 or index >= len(self.session_ids):
            return
        session_id = self.session_ids[index]
        session = next(s for s in self.controller.state.sessions if s.id == session_id)
        preserve_range = preserve_range and session_id == self.selected_session_id
        self.selected_session_id = session_id
        self.current_report = self.controller.report(session)
        self.report_task.configure(text=session.task)
        self.report_dates.configure(text=f"{date_string(session.started_at)} — {date_string(session.ended_at)}")
        self.report_totals.configure(text=self.totals_text(self.current_report.total))
        if not preserve_range:
            self.range_start.set(date_string(session.started_at))
            # Round outwards so second-resolution fields include fractional boundaries.
            self.range_end.set(date_string(session.ended_at + 1))
        self.apply_range()
        self.render_ranking()
        self.timeline.delete(*self.timeline.get_children())
        for span in self.current_report.spans:
            self.timeline.insert("", "end", values=(datetime.fromtimestamp(span.start).strftime("%H:%M:%S"),
                span.title or span.host, span.label.title(), clock(span.duration)), tags=(span.label,))
        for label, color in COLORS.items():
            self.timeline.tag_configure(label, foreground=color)
        self.report_warnings.configure(text="\n".join(self.current_report.warnings))

    def apply_range(self):
        if self.current_report:
            start, end = parse_date(self.range_start.get()), parse_date(self.range_end.get())
            if end < start:
                raise ValueError("Choose an end time after the start time.")
            self.range_totals.configure(text=self.totals_text(self.current_report.prefix.totals(start, end)))

    def render_ranking(self):
        self.ranking.delete(*self.ranking.get_children())
        if self.current_report:
            ranking = self.current_report.distraction_ranking if self.rank_distractions.get() else self.current_report.ranking
            for host, seconds in ranking:
                self.ranking.insert("", "end", values=(host, clock(seconds)))

    def render(self):
        controller, session = self.controller, self.controller.state.current
        self.session_status.configure(text="Ready for a focus session" if not session else "Session paused" if session.paused else "Session in progress")
        self.timer.configure(text=clock(controller.elapsed()))
        self.start_button.configure(state="disabled" if session else "normal")
        self.pause_button.configure(state="normal" if session else "disabled", text="Resume" if session and session.paused else "Pause")
        self.end_button.configure(state="normal" if session else "disabled")
        if session:
            if self.task_input.get("1.0", "end").strip() != session.task:
                self.task_input.configure(state="normal")
                self.task_input.delete("1.0", "end")
                self.task_input.insert("1.0", session.task)
            self.task_input.configure(state="disabled")
        else:
            self.task_input.configure(state="normal")
        page = controller.latest_page
        signature = repr(page)
        if self.page_signature != signature:
            self.page_signature = signature
            if page:
                self.page_title.configure(text=page.title)
                attempts = f" · {page.attempts} model attempt(s)" if page.attempts else ""
                self.page_host.configure(text=f"{page.host} · {page.source}{attempts}")
                self.page_label.configure(text=page.label.upper(), foreground=COLORS[page.label])
                self.page_reason.configure(text=page.reason)
                self.intervention.configure(text=page.intervention or "")
            else:
                self.page_title.configure(text="Start a session, then switch to Safari or Chrome." if not session else "Waiting for the active browser page…")
                self.page_host.configure(text="")
                self.page_label.configure(text="UNCERTAIN", foreground=COLORS["uncertain"])
                self.page_reason.configure(text="Other applications are recorded by name and marked uncertain.")
                self.intervention.configure(text="")
        for button in self.override_buttons:
            button.configure(state="normal" if page else "disabled")
        self.monitor_status.configure(text=controller.monitoring_message[:650])
        self.connection_status.configure(text=controller.connection_message)
        self.settings_connection.configure(text=controller.connection_message)
        self.error_status.configure(text="\n".join(filter(None, [controller.error, *controller.state.storage_warnings])))
        self.action_status.configure(text=controller.action_message)
        self.review_status.configure(text=controller.review_message)
        self.review_button.configure(state="normal" if session and page and page.source != "pending" and not session.paused else "disabled")
        self.closed_review_button.configure(state="normal" if session and not session.paused and controller.close_receipt else "disabled")
        self.model_combo.configure(values=controller.model_choices)
        self.check_button.configure(state="disabled" if controller.connection_future else "normal")
        self.render_warning()
        if self.tabs.index(self.tabs.select()) == 1:
            self.refresh_reports()

    def render_warning(self):
        event = self.controller.warning_event()
        signature = (event.id, event.label, event.reason, event.intervention) if event else None
        if signature is None or signature in self.dismissed:
            self.hide_warning()
            return
        if self.warning_id == signature and self.warning and self.warning.winfo_exists():
            return
        self.hide_warning()
        warning = tk.Toplevel(self.root)
        warning.withdraw()
        if self.root.tk.call("tk", "windowingsystem") == "aqua":
            try:
                self.root.tk.call("::tk::unsupported::MacWindowStyle", "style", warning._w,
                                  "help", "noActivates nonActivating doesNotHide canJoinAllSpaces")
            except tk.TclError:
                pass
        warning.title("Focus reminder")
        warning.resizable(False, False)
        warning.attributes("-topmost", True)
        frame = ttk.Frame(warning, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Return to your task?", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text=event.intervention, wraplength=360).pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text=event.reason, wraplength=360, foreground=COLORS["distracting"]).pack(anchor="w", pady=(0, 10))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Button(row, text="Request correction…", command=lambda eid=event.id: self.call(lambda: self.open_review(eid))).pack(side="left")
        ttk.Button(row, text="Dismiss", command=lambda: self.dismiss_warning(signature)).pack(side="right")
        warning.protocol("WM_DELETE_WINDOW", lambda: self.dismiss_warning(signature))
        warning.update_idletasks()
        width, height = warning.winfo_reqwidth(), warning.winfo_reqheight()
        warning.geometry(f"+{max(0, warning.winfo_screenwidth() - width - 28)}+{max(30, warning.winfo_screenheight() - height - 80)}")
        self.warning, self.warning_id = warning, signature
        warning.deiconify()
        try:
            if self.controller.actions:
                self.controller.actions.desktop.place_reminder()
        except Exception as exc:
            self.controller.action_message = f"Reminder placement could not be confirmed: {exc}"
        # No focus_set/focus_force: a reminder should not take keyboard input.

    def dismiss_warning(self, signature):
        self.dismissed.add(signature)
        self.hide_warning()

    def hide_warning(self):
        if self.warning and self.warning.winfo_exists():
            self.warning.destroy()
        self.warning = self.warning_id = None

    def refresh(self):
        if self.closed:
            return
        try:
            self.controller.tick()
            self.render()
        except Exception as exc:
            self.controller.error = f"Refresh failed: {exc}"
            self.error_status.configure(text=self.controller.error)
        self.root.after(250, self.refresh)

    def close(self):
        if not self.closed:
            self.closed = True
            self.hide_warning()
            self.controller.close()
            self.root.destroy()
