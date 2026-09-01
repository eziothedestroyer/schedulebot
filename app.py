from __future__ import annotations

import csv
import json
import os
import tkinter as tk
import uuid
import calendar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from schedule_parser import parse_request
from stream_studio import StreamStudio
from version import VERSION


APP_NAME = "ScheduleBot"


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

    def configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
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
        style.configure("TEntry", padding=10, fieldbackground="#151c32", foreground="#ffffff", insertcolor="#ffffff")
        style.configure("TCombobox", padding=7, fieldbackground="#151c32", foreground="#ffffff")
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

        content = ttk.Panedwindow(frame, orient="horizontal")
        content.pack(fill="both", expand=True, pady=14)
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
        ttk.Label(buttons, text="●  All changes saved", style="Saved.TLabel").pack(side="left", padx=14)
        ttk.Button(buttons, text="Export CSV", command=self.export_csv).pack(side="right")
        ttk.Button(buttons, text="Export calendar", command=self.export_ics).pack(side="right", padx=8)

    def load_data(self):
        try:
            saved = json.loads(data_file().read_text(encoding="utf-8"))
            if isinstance(saved, list):
                return saved, {}
            return saved.get("tasks", []), saved.get("stream", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return [], {}

    def save(self):
        data_file().write_text(json.dumps({"tasks": self.tasks, "stream": self.stream_settings}, indent=2), encoding="utf-8")

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
        for task in self.tasks:
            start = datetime.fromisoformat(task["start"])
            self.tree.insert("", "end", iid=task["id"], values=(start.strftime("%b %d, %Y"),
                start.strftime("%I:%M %p").lstrip("0"), task["title"],
                f'{task["duration"]} min', task.get("repeat", "").title()))
        self.draw_calendar()

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
