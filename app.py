from __future__ import annotations

import csv
import json
import os
import sys
import tkinter as tk
import uuid
import calendar
import webbrowser
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from schedule_parser import parse_request
from stream_studio import StreamStudio
from version import VERSION


APP_NAME = "ScheduleBot"

SETUP_GUIDES = {
    "Start here": (
        "ScheduleBot keeps secrets in your operating system credential vault. Never post a client secret, "
        "bot token, webhook URL, or API key in chat or commit one to Git.\n\n"
        "You only need credentials for the integrations you plan to use. OBS and Local Ollama do not need "
        "cloud API keys. Open Streaming Studio after completing a section below and enter the credential on "
        "the matching tab."
    ),
    "Twitch": (
        "1. Sign in to the Twitch Developer Console. Your Twitch account must have a verified email address "
        "and two-factor authentication enabled.\n\n"
        "2. Open Applications and choose Register Your Application. Give it a unique name such as "
        "ScheduleBot YourName.\n\n"
        "3. Add http://localhost as the OAuth Redirect URL, select an appropriate category, complete the "
        "verification, and create the app. ScheduleBot uses Twitch's device authorization page, so it does "
        "not receive your Twitch password.\n\n"
        "4. Choose Manage beside the new app and copy the Client ID. A client secret is optional for the "
        "device flow used here; if you create one, treat it like a password.\n\n"
        "5. In ScheduleBot, open Streaming Studio → Twitch, paste the Client ID (and optional secret), choose "
        "Save Twitch credentials securely, then Connect Twitch. Enter the displayed code in the browser."
    ),
    "YouTube": (
        "1. Open Google Cloud Console, create or select a project, then enable YouTube Data API v3. If you "
        "want the analytics features, also enable YouTube Analytics API.\n\n"
        "2. Open Google Auth Platform. Configure Branding and Audience. For personal testing, External is "
        "usually appropriate; add your Google account as a test user while the app is in testing.\n\n"
        "3. Open Clients, choose Create client, select Desktop app, name it ScheduleBot, and create it. "
        "Download the OAuth client JSON file. You do not need a separate API key for YouTube Live.\n\n"
        "4. In ScheduleBot, open Streaming Studio → YouTube, choose that JSON file, then click Connect "
        "YouTube. Sign in to the YouTube channel you want to manage and approve access.\n\n"
        "5. Keep the JSON private. Start by creating a private or unlisted test broadcast. Google may show an "
        "unverified-app warning while a personal OAuth app remains in testing."
    ),
    "Discord": (
        "Easiest option — webhook:\n"
        "1. In Discord, open Server Settings → Integrations → Webhooks. Create a webhook, choose a text "
        "channel, and copy its URL. You need Manage Webhooks permission.\n"
        "2. Paste the URL into Streaming Studio → Discord under Optional webhook fallback. A webhook URL is "
        "a secret because anyone holding it can post to that channel.\n\n"
        "Bot option — channel picker:\n"
        "1. In the Discord Developer Portal choose New Application. Open Bot and reset/copy the bot token. "
        "Save only the token in a plain .txt file; ScheduleBot moves it into the credential vault.\n"
        "2. Open Installation and add the bot scope with View Channels and Send Messages permissions. Copy "
        "the install link, open it, and add the bot to your server.\n"
        "3. In Streaming Studio → Discord choose the token file, then Load channels. Delete the temporary "
        "token file after ScheduleBot confirms it was secured. Regenerate the token immediately if exposed."
    ),
    "OpenAI": (
        "1. Sign in to the OpenAI Platform and open API Keys. API billing is separate from a ChatGPT "
        "subscription, so add billing or project credits if your API project requires it.\n\n"
        "2. Choose Create new secret key. Prefer a project-scoped key with restricted permissions when those "
        "controls are available. Copy it once and store it safely; do not share it.\n\n"
        "3. In ScheduleBot open Streaming Studio → AI VOD, select OpenAI, paste the key, choose a model, and "
        "click Save securely. ScheduleBot stores it in the OS credential vault and sends transcript text—not "
        "the source video—to the Responses API with response storage disabled.\n\n"
        "No-key alternative: select Local Ollama, install Ollama and run `ollama pull llama3.2`. Transcript "
        "processing then stays on this computer."
    ),
    "OBS": (
        "1. Open OBS Studio. In OBS 28 or newer, WebSocket support is built in.\n\n"
        "2. Choose Tools → WebSocket Server Settings, enable the server, keep port 4455 unless you have a "
        "reason to change it, enable authentication, and create a strong password.\n\n"
        "3. In Streaming Studio → OBS controls, use host localhost, the same port and password, then click "
        "Connect to OBS. This is a local connection and does not require an API key.\n\n"
        "4. Configure your streaming service and stream key inside OBS separately. Clicking Start streaming "
        "in ScheduleBot can broadcast publicly, so test scenes and destinations first."
    ),
}

SETUP_URLS = {
    "Twitch": "https://dev.twitch.tv/console/apps",
    "YouTube": "https://console.cloud.google.com/apis/credentials",
    "Discord": "https://discord.com/developers/applications",
    "OpenAI": "https://platform.openai.com/api-keys",
    "OBS": "https://obsproject.com/kb/remote-control-guide",
}


def bundled_file(name: str) -> Path:
    """Return an asset path in source runs and PyInstaller builds."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def data_file() -> Path:
    if os.getenv("APPDATA"):
        base = Path(os.environ["APPDATA"]) / APP_NAME
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base / "schedule.json"


class ScheduleBot(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"ScheduleBot {VERSION}")
        self.set_app_icon()
        self.geometry("1060x680")
        self.minsize(860, 560)
        self.configure(bg="#0b1020")
        self.configure_styles()
        self.tasks, self.stream_settings = self.load_data()
        today = datetime.now().date()
        self.calendar_year = today.year
        self.calendar_month = today.month
        self.selected_date = today
        self._build()
        self.refresh()
        if not self.stream_settings.get("onboarding_seen"):
            self.after(350, self.show_getting_started)

    def set_app_icon(self):
        """Apply the brand icon to the window, taskbar, and dialogs."""
        try:
            self._app_icon = tk.PhotoImage(file=bundled_file("schedulebot-icon.png"))
            self.iconphoto(True, self._app_icon)
        except (tk.TclError, OSError):
            # The app should still start if an external source checkout omits assets.
            self._app_icon = None

    def configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        # Keep native pop-up lists consistent with the dark theme as well.
        self.option_add("*TCombobox*Listbox.background", "#151c32")
        self.option_add("*TCombobox*Listbox.foreground", "#ffffff")
        self.option_add("*TCombobox*Listbox.selectBackground", "#6548dc")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        style.configure(".", background="#0b1020", foreground="#e8ecff",
                        fieldbackground="#151c32", bordercolor="#2a3558",
                        lightcolor="#2a3558", darkcolor="#2a3558", font=("Segoe UI", 10))
        style.configure("TFrame", background="#0b1020")
        style.configure("Card.TFrame", background="#121a2e", relief="flat")
        style.configure("TLabel", background="#0b1020", foreground="#e8ecff")
        style.configure("Card.TLabel", background="#121a2e", foreground="#e8ecff")
        style.configure("Hero.TLabel", background="#0b1020", foreground="#ffffff", font=("Segoe UI", 24, "bold"))
        style.configure("Muted.TLabel", background="#0b1020", foreground="#929dc2")
        style.configure("Saved.TLabel", background="#0b1020", foreground="#62d6a7")
        style.configure("TEntry", padding=10, background="#151c32", fieldbackground="#151c32",
                        foreground="#ffffff", insertcolor="#ffffff", bordercolor="#344368")
        style.map("TEntry",
                  fieldbackground=[("disabled", "#11182a"), ("readonly", "#151c32"), ("focus", "#19223b")],
                  foreground=[("disabled", "#aeb8d8"), ("readonly", "#ffffff")],
                  bordercolor=[("focus", "#9278ff")])
        style.configure("TCombobox", padding=7, background="#202a48", fieldbackground="#151c32",
                        foreground="#ffffff", arrowcolor="#ffffff", bordercolor="#344368")
        style.map("TCombobox",
                  fieldbackground=[("readonly", "#151c32"), ("disabled", "#11182a"), ("focus", "#19223b")],
                  foreground=[("readonly", "#ffffff"), ("disabled", "#aeb8d8")],
                  background=[("readonly", "#202a48"), ("active", "#303d66")],
                  arrowcolor=[("readonly", "#ffffff"), ("disabled", "#7f89aa")],
                  bordercolor=[("focus", "#9278ff")])
        style.configure("TButton", padding=(10, 8), background="#202a48", foreground="#eef0ff", borderwidth=0)
        style.map("TButton", background=[("active", "#303d66"), ("pressed", "#18213b")])
        style.configure("Accent.TButton", background="#7857ff", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#9278ff"), ("pressed", "#6242df")])
        style.configure("Danger.TButton", background="#8f3d58", foreground="#ffffff")
        style.map("Danger.TButton", background=[("active", "#b34d6c")])
        style.configure("Treeview", background="#121a2e", fieldbackground="#121a2e", foreground="#e8ecff",
                        rowheight=34, borderwidth=0)
        style.map("Treeview", background=[("selected", "#6548dc")], foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading", background="#1c2642", foreground="#aeb8d8", relief="flat",
                        padding=(8, 9), font=("Segoe UI", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", "#283555")])
        style.configure("TNotebook", background="#0b1020", borderwidth=0)
        style.configure("TNotebook.Tab", background="#18213a", foreground="#aeb8d8", padding=(18, 10), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#7857ff")], foreground=[("selected", "#ffffff")])
        style.configure("TCheckbutton", background="#0b1020", foreground="#dbe1fa", padding=3)
        style.map("TCheckbutton", background=[("active", "#0b1020")])
        style.configure("TLabelframe", background="#0b1020", bordercolor="#344368",
                        lightcolor="#344368", darkcolor="#344368", relief="solid")
        style.configure("TLabelframe.Label", background="#0b1020", foreground="#ffffff",
                        font=("Segoe UI", 10, "bold"))
        style.configure("TScrollbar", background="#202a48", troughcolor="#0b1020",
                        bordercolor="#0b1020", arrowcolor="#dbe1fa")
        style.map("TScrollbar", background=[("active", "#6548dc"), ("pressed", "#7857ff")])

    def _build(self):
        frame = ttk.Frame(self, padding=24)
        frame.pack(fill="both", expand=True)
        heading = ttk.Frame(frame)
        heading.pack(fill="x", pady=(0, 18))
        ttk.Label(heading, text="S", style="Hero.TLabel", foreground="#9a84ff").pack(side="left")
        ttk.Label(heading, text="cheduleBot", style="Hero.TLabel").pack(side="left")
        ttk.Label(heading, text="  CREATOR EDITION", style="Muted.TLabel").pack(side="left", pady=(10, 0))
        ttk.Button(heading, text="◉  Streaming Studio", style="Accent.TButton",
                   command=lambda: StreamStudio(self)).pack(side="right")
        ttk.Button(heading, text="API setup guide", command=self.show_getting_started).pack(
            side="right", padx=8)
        ttk.Label(frame, text="What do you want to schedule?", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Try: Study tomorrow at 7 pm for 2 hours — or select a calendar day",
                  style="Muted.TLabel").pack(anchor="w", pady=(3, 10))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        self.request = ttk.Entry(row, font=("Segoe UI", 12))
        self.request.pack(side="left", fill="x", expand=True)
        self.request.bind("<Return>", lambda _event: self.add_task())
        ttk.Button(row, text="＋  Add to schedule", style="Accent.TButton", command=self.add_task).pack(side="left", padx=(10, 0))
        self.request.focus_set()

        tools = ttk.Frame(frame)
        tools.pack(fill="x", pady=(12, 0))
        ttk.Label(tools, text="Search", style="Muted.TLabel").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self.refresh())
        search = ttk.Entry(tools, textvariable=self.search_var)
        search.pack(side="left", fill="x", expand=True, padx=(8, 12))
        self.show_completed = tk.BooleanVar(value=True)
        ttk.Checkbutton(tools, text="Show completed", variable=self.show_completed,
                        command=self.refresh).pack(side="left")
        self.summary_label = ttk.Label(tools, style="Muted.TLabel")
        self.summary_label.pack(side="right", padx=(12, 0))

        content = ttk.Panedwindow(frame, orient="horizontal")
        content.pack(fill="both", expand=True, pady=(10, 14))
        schedule_panel = ttk.Frame(content, style="Card.TFrame", padding=12)
        calendar_panel = ttk.Frame(content, style="Card.TFrame", padding=16)
        content.add(schedule_panel, weight=3)
        content.add(calendar_panel, weight=2)

        columns = ("date", "time", "task", "duration", "repeat")
        self.tree = ttk.Treeview(schedule_panel, columns=columns, show="headings", selectmode="extended")
        widths = (110, 85, 250, 80, 80)
        for col, width in zip(columns, widths):
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("completed", foreground="#7f89aa")
        self.tree.bind("<Double-1>", lambda _event: self.edit_selected())
        self.tree.bind("<Delete>", lambda _event: self.delete_selected())

        nav = ttk.Frame(calendar_panel)
        nav.pack(fill="x", pady=(0, 8))
        ttk.Button(nav, text="‹", width=3, command=lambda: self.change_month(-1)).pack(side="left")
        self.month_label = ttk.Label(nav, font=("Segoe UI", 13, "bold"), anchor="center")
        self.month_label.pack(side="left", fill="x", expand=True)
        ttk.Button(nav, text="›", width=3, command=lambda: self.change_month(1)).pack(side="right")
        self.calendar_grid = ttk.Frame(calendar_panel)
        self.calendar_grid.pack(fill="x")
        self.day_info = ttk.Label(calendar_panel, wraplength=270, justify="left")
        self.day_info.pack(fill="x", pady=(12, 0))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Delete selected", style="Danger.TButton", command=self.delete_selected).pack(side="left")
        ttk.Button(buttons, text="Edit", command=self.edit_selected).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="✓  Complete", command=self.toggle_completed).pack(side="left", padx=(8, 0))
        ttk.Label(buttons, text="●  All changes saved", style="Saved.TLabel").pack(side="left", padx=14)
        ttk.Button(buttons, text="Export CSV", command=self.export_csv).pack(side="right")
        ttk.Button(buttons, text="Export calendar", command=self.export_ics).pack(side="right", padx=8)

    def load_data(self):
        try:
            saved = json.loads(data_file().read_text(encoding="utf-8"))
            if isinstance(saved, list):
                return saved, {}
            if not isinstance(saved, dict):
                raise ValueError("Saved data must be a JSON object.")
            return saved.get("tasks", []), saved.get("stream", {})
        except FileNotFoundError:
            return [], {}
        except (json.JSONDecodeError, ValueError, AttributeError) as error:
            broken = data_file().with_name("schedule.invalid.json")
            try:
                data_file().replace(broken)
            except OSError:
                pass
            self.after(0, lambda detail=str(error), path=str(broken): messagebox.showwarning(
                "Schedule data could not be loaded",
                f"ScheduleBot started with an empty schedule because the saved data was invalid.\n\n"
                f"Details: {detail}\n\nA backup was kept at:\n{path}", parent=self))
            return [], {}

    def save(self):
        destination = data_file()
        payload = json.dumps({"tasks": self.tasks, "stream": self.stream_settings}, indent=2)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                                             prefix="schedule-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def show_getting_started(self):
        self.stream_settings["onboarding_seen"] = True
        self.save()
        dialog = tk.Toplevel(self)
        dialog.title("API keys & integration setup")
        dialog.geometry("760x610")
        dialog.minsize(620, 500)
        dialog.transient(self)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Connect your creator tools", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(body, text="Choose a service for exact setup steps. You only need the services you use.",
                  style="Muted.TLabel").pack(anchor="w", pady=(3, 12))
        selected = tk.StringVar(value="Start here")
        chooser = ttk.Combobox(body, textvariable=selected, values=tuple(SETUP_GUIDES),
                               state="readonly", font=("Segoe UI", 11))
        chooser.pack(fill="x")
        text_frame = ttk.Frame(body)
        text_frame.pack(fill="both", expand=True, pady=12)
        guide = tk.Text(text_frame, wrap="word", bg="#121a2e", fg="#e8ecff",
                        insertbackground="#ffffff", relief="flat", padx=16, pady=16,
                        font=("Segoe UI", 10), spacing1=3, spacing3=7)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=guide.yview)
        guide.configure(yscrollcommand=scroll.set)
        guide.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        actions = ttk.Frame(body)
        actions.pack(fill="x")
        portal = ttk.Button(actions, text="Open official setup page")
        portal.pack(side="left")
        ttk.Button(actions, text="Open Streaming Studio", style="Accent.TButton",
                   command=lambda: StreamStudio(self)).pack(side="right")
        ttk.Button(actions, text="Close", command=dialog.destroy).pack(side="right", padx=8)

        def show_section(*_args):
            section = selected.get()
            guide.configure(state="normal")
            guide.delete("1.0", "end")
            guide.insert("1.0", SETUP_GUIDES[section])
            guide.configure(state="disabled")
            guide.yview_moveto(0)
            url = SETUP_URLS.get(section)
            portal.configure(state="normal" if url else "disabled",
                             command=(lambda target=url: webbrowser.open(target)) if url else None)

        chooser.bind("<<ComboboxSelected>>", show_section)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        show_section()

    def add_task(self):
        request_text = self.request.get().strip()
        if request_text and not self.has_date_words(request_text):
            request_text += f" {self.selected_date:%B} {self.selected_date.day}, {self.selected_date.year}"
        try:
            task = parse_request(request_text)
        except ValueError as error:
            messagebox.showerror("Could not add task", str(error))
            return
        self.tasks.append({"id": uuid.uuid4().hex, "title": task.title,
                           "start": task.start.isoformat(), "duration": task.duration_minutes,
                           "repeat": task.repeat})
        self.tasks.sort(key=lambda item: item["start"])
        self.save()
        self.request.delete(0, "end")
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        visible = [task for task in self.tasks
                   if (self.show_completed.get() or not task.get("completed"))
                   and (not query or query in task["title"].lower())]
        for task in visible:
            start = datetime.fromisoformat(task["start"])
            self.tree.insert("", "end", iid=task["id"], values=(start.strftime("%b %d, %Y"),
                start.strftime("%I:%M %p").lstrip("0"), task["title"],
                f'{task["duration"]} min', task.get("repeat", "").title()),
                tags=("completed",) if task.get("completed") else ())
        if hasattr(self, "summary_label"):
            completed = sum(bool(task.get("completed")) for task in self.tasks)
            self.summary_label.configure(text=f"{len(self.tasks) - completed} open · {completed} completed")
        self.draw_calendar()

    def selected_tasks(self):
        selected = set(self.tree.selection())
        return [task for task in self.tasks if task["id"] in selected]

    def toggle_completed(self):
        selected = self.selected_tasks()
        if not selected:
            messagebox.showinfo("Select a task", "Select one or more tasks first.", parent=self)
            return
        mark_complete = any(not task.get("completed") for task in selected)
        for task in selected:
            task["completed"] = mark_complete
        self.save()
        self.refresh()

    def edit_selected(self):
        selected = self.selected_tasks()
        if len(selected) != 1:
            messagebox.showinfo("Edit a task", "Select exactly one task to edit.", parent=self)
            return
        task = selected[0]
        start = datetime.fromisoformat(task["start"])
        dialog = tk.Toplevel(self)
        dialog.title("Edit task")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)
        fields = (
            ("Title", tk.StringVar(value=task["title"])),
            ("Date (YYYY-MM-DD)", tk.StringVar(value=start.strftime("%Y-%m-%d"))),
            ("Time (HH:MM)", tk.StringVar(value=start.strftime("%H:%M"))),
            ("Duration (minutes)", tk.StringVar(value=str(task["duration"]))),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(body, textvariable=variable, width=34).grid(row=row, column=1, padx=(12, 0), pady=5)
        repeat = tk.BooleanVar(value=task.get("repeat") == "weekly")
        ttk.Checkbutton(body, text="Repeat weekly", variable=repeat).grid(
            row=4, column=1, sticky="w", padx=(12, 0), pady=5)

        def apply_changes():
            try:
                title = fields[0][1].get().strip()
                new_start = datetime.strptime(
                    f"{fields[1][1].get().strip()} {fields[2][1].get().strip()}", "%Y-%m-%d %H:%M")
                duration = int(fields[3][1].get())
                if not title:
                    raise ValueError("Title cannot be empty.")
                if duration < 1:
                    raise ValueError("Duration must be at least one minute.")
            except ValueError as error:
                messagebox.showerror("Check task details", str(error), parent=dialog)
                return
            task.update(title=title, start=new_start.isoformat(), duration=duration,
                        repeat="weekly" if repeat.get() else "")
            self.tasks.sort(key=lambda item: item["start"])
            self.save()
            dialog.destroy()
            self.refresh()

        actions = ttk.Frame(body)
        actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="left")
        ttk.Button(actions, text="Save changes", style="Accent.TButton",
                   command=apply_changes).pack(side="left", padx=(8, 0))
        dialog.bind("<Return>", lambda _event: apply_changes())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.wait_visibility()
        dialog.focus_set()

    @staticmethod
    def has_date_words(text):
        lowered = text.lower()
        words = ("today", "tomorrow", "monday", "tuesday", "wednesday", "thursday",
                 "friday", "saturday", "sunday", "january", "february", "march",
                 "april", "may", "june", "july", "august", "september", "october",
                 "november", "december")
        return any(word in lowered for word in words) or bool(__import__("re").search(r"\b\d{1,2}[/-]\d{1,2}\b", text))

    def change_month(self, amount):
        month = self.calendar_month + amount
        self.calendar_year += (month - 1) // 12
        self.calendar_month = (month - 1) % 12 + 1
        self.draw_calendar()

    def select_day(self, day):
        self.selected_date = datetime(self.calendar_year, self.calendar_month, day).date()
        self.draw_calendar()
        self.request.focus_set()
        day_tasks = [task for task in self.tasks
                     if datetime.fromisoformat(task["start"]).date() == self.selected_date]
        if day_tasks:
            details = []
            for task in day_tasks:
                start = datetime.fromisoformat(task["start"])
                repeat = " (repeats weekly)" if task.get("repeat") == "weekly" else ""
                details.append(f"{start:%I:%M %p} — {task['title']}\n"
                               f"Duration: {task['duration']} minutes{repeat}")
            messagebox.showinfo(f"Schedule for {self.selected_date:%B %d, %Y}",
                                "\n\n".join(details), parent=self)

    def draw_calendar(self):
        for widget in self.calendar_grid.winfo_children():
            widget.destroy()
        self.month_label.configure(text=f"{calendar.month_name[self.calendar_month]} {self.calendar_year}")
        for column, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            ttk.Label(self.calendar_grid, text=name, anchor="center").grid(row=0, column=column, sticky="ew", pady=2)
            self.calendar_grid.columnconfigure(column, weight=1)
        task_days = {datetime.fromisoformat(task["start"]).date() for task in self.tasks}
        weeks = calendar.monthcalendar(self.calendar_year, self.calendar_month)
        for row, week in enumerate(weeks, 1):
            for column, day in enumerate(week):
                if not day:
                    ttk.Label(self.calendar_grid, text="").grid(row=row, column=column)
                    continue
                current = datetime(self.calendar_year, self.calendar_month, day).date()
                label = f"{day}{' •' if current in task_days else ''}"
                style = "Accent.TButton" if current == self.selected_date else "TButton"
                ttk.Button(self.calendar_grid, text=label, width=4, style=style,
                           command=lambda value=day: self.select_day(value)).grid(row=row, column=column, sticky="ew", padx=1, pady=1)
        day_tasks = [task for task in self.tasks if datetime.fromisoformat(task["start"]).date() == self.selected_date]
        if day_tasks:
            details = "\n".join(f"• {datetime.fromisoformat(t['start']):%I:%M %p} — {t['title']}" for t in day_tasks)
        else:
            details = "No tasks yet. Type a task above to add it to this day."
        self.day_info.configure(text=f"Selected: {self.selected_date:%A, %B %d}\n{details}")

    def delete_selected(self):
        selected = set(self.tree.selection())
        if not selected:
            return
        noun = "task" if len(selected) == 1 else "tasks"
        if not messagebox.askyesno("Delete tasks", f"Delete {len(selected)} selected {noun}?", parent=self):
            return
        self.tasks = [task for task in self.tasks if task["id"] not in selected]
        self.save()
        self.refresh()

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(("Task", "Start", "Duration (minutes)", "Repeat"))
                writer.writerows((t["title"], t["start"], t["duration"], t.get("repeat", "")) for t in self.tasks)

    def export_ics(self):
        path = filedialog.asksaveasfilename(defaultextension=".ics", filetypes=[("Calendar", "*.ics")])
        if not path:
            return
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ScheduleBot//EN"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for task in self.tasks:
            start = datetime.fromisoformat(task["start"])
            end = start + timedelta(minutes=task["duration"])
            title = task["title"].replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
            lines += ["BEGIN:VEVENT", f'UID:{task["id"]}@schedulebot', f"DTSTAMP:{stamp}",
                      f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}", f"SUMMARY:{title}"]
            if task.get("repeat") == "weekly":
                lines.append("RRULE:FREQ=WEEKLY")
            lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")
        Path(path).write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        messagebox.showinfo("Export complete", "Your calendar file is ready.")


if __name__ == "__main__":
    ScheduleBot().mainloop()
