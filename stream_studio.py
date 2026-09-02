from __future__ import annotations

import tkinter as tk
import webbrowser
import json
import threading
import urllib.error
import urllib.request
import os
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from credential_store import get as get_secret, set_secret
from tiktok_client import TikTokClient
from youtube_client import YouTubeClient

try:
    import obsws_python as obs
except ImportError:
    obs = None


PLATFORM_URLS = {
    "YouTube": {
        "dashboard": "https://studio.youtube.com/",
        "live": "https://www.youtube.com/live_dashboard",
    },
    "Twitch": {
        "dashboard": "https://dashboard.twitch.tv/",
        "live": "https://dashboard.twitch.tv/u/{channel}/stream-manager",
    },
}
DEFAULT_CHECKLIST = ["Internet checked", "Microphone tested", "Camera/scene ready",
                     "Title and category set", "Chat rules/moderators ready"]


class StreamStudio(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.settings = owner.stream_settings
        self.obs_client = None
        self.title("ScheduleBot — Streaming Studio")
        self.geometry("820x700")
        self.minsize(700, 600)
        self.configure(bg="#0b1020")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self.load()

    def _build(self):
        header = ttk.Frame(self, padding=(20, 18, 20, 6))
        header.pack(fill="x")
        ttk.Label(header, text="Streaming Studio", style="Hero.TLabel").pack(side="left")
        ttk.Label(header, text="  YouTube  •  Twitch  •  OBS", style="Muted.TLabel").pack(side="left", pady=(10, 0))
        book = ttk.Notebook(self, padding=16)
        book.pack(fill="both", expand=True)
        planner, controls, discord, youtube, tiktok = (ttk.Frame(book, padding=20) for _ in range(5))
        book.add(planner, text="Stream setup")
        book.add(controls, text="OBS controls")
        book.add(discord, text="Discord")
        book.add(youtube, text="YouTube")
        book.add(tiktok, text="TikTok")

        self.platform = tk.StringVar(value="YouTube")
        self.title_var, self.category, self.tags, self.channel = (tk.StringVar() for _ in range(4))
        fields = (("Platform", ttk.Combobox(planner, textvariable=self.platform,
                   values=("YouTube", "Twitch"), state="readonly")),
                  ("Stream title", ttk.Entry(planner, textvariable=self.title_var)),
                  ("Category / game", ttk.Entry(planner, textvariable=self.category)),
                  ("Tags (comma separated)", ttk.Entry(planner, textvariable=self.tags)),
                  ("Channel name", ttk.Entry(planner, textvariable=self.channel)))
        for row, (label, widget) in enumerate(fields):
            ttk.Label(planner, text=label).grid(row=row, column=0, sticky="w", pady=4)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Label(planner, text="Description").grid(row=5, column=0, sticky="nw", pady=4)
        self.description = tk.Text(planner, height=6, wrap="word", bg="#151c32", fg="#ffffff",
                                   insertbackground="#ffffff", relief="flat", padx=10, pady=10,
                                   selectbackground="#6548dc")
        self.description.grid(row=5, column=1, sticky="nsew", pady=4)
        ttk.Label(planner, text="Pre-stream checklist").grid(row=6, column=0, sticky="nw", pady=8)
        checks = ttk.Frame(planner)
        checks.grid(row=6, column=1, sticky="ew", pady=8)
        self.check_vars = []
        for item in DEFAULT_CHECKLIST:
            value = tk.BooleanVar()
            self.check_vars.append(value)
            ttk.Checkbutton(checks, text=item, variable=value, command=self.save).pack(anchor="w")
        actions = ttk.Frame(planner)
        actions.grid(row=7, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Button(actions, text="Save setup", style="Accent.TButton", command=self.save_with_notice).pack(side="left")
        ttk.Button(actions, text="Open dashboard", command=self.open_dashboard).pack(side="left", padx=6)
        ttk.Button(actions, text="Open stream manager / chat", command=self.open_live).pack(side="left")
        planner.columnconfigure(1, weight=1)
        planner.rowconfigure(5, weight=1)

        self.obs_host = tk.StringVar(value="localhost")
        self.obs_port = tk.StringVar(value="4455")
        self.obs_password = tk.StringVar()
        for row, (label, variable, secret) in enumerate((("OBS host", self.obs_host, False),
                ("OBS WebSocket port", self.obs_port, False), ("OBS password", self.obs_password, True))):
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(controls, textvariable=variable, show="•" if secret else "").grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Button(controls, text="Connect to OBS", style="Accent.TButton", command=self.connect_obs).grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)
        self.obs_status = ttk.Label(controls, text="Not connected")
        self.obs_status.grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(controls, text="Scene").grid(row=5, column=0, sticky="w", pady=(18, 5))
        self.scene = ttk.Combobox(controls, state="readonly")
        self.scene.grid(row=5, column=1, sticky="ew", pady=(18, 5))
        self.scene.bind("<<ComboboxSelected>>", self.change_scene)
        row = ttk.Frame(controls)
        row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Button(row, text="●  Start streaming", style="Accent.TButton", command=self.start_stream).pack(side="left", expand=True, fill="x")
        ttk.Button(row, text="■  Stop streaming", style="Danger.TButton", command=self.stop_stream).pack(side="left", expand=True, fill="x", padx=(8, 0))
        ttk.Label(controls, text="In OBS, enable Tools → WebSocket Server Settings first.\n"
                  "Starting a stream broadcasts publicly if OBS is configured with a stream key.",
                  wraplength=560).grid(row=7, column=0, columnspan=2, sticky="w", pady=12)
        controls.columnconfigure(1, weight=1)

        ttk.Label(discord, text="Post to a Discord channel", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(discord, text="Load every server and text channel visible to your ScheduleBot account.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 12))
        picker = ttk.Frame(discord)
        picker.pack(fill="x", pady=(0, 12))
        self.discord_guild = ttk.Combobox(picker, state="readonly", width=24)
        self.discord_guild.pack(side="left", fill="x", expand=True)
        self.discord_guild.bind("<<ComboboxSelected>>", self.show_discord_channels)
        self.discord_channel = ttk.Combobox(picker, state="readonly", width=28)
        self.discord_channel.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(picker, text="Load channels", style="Accent.TButton",
                   command=self.load_discord).pack(side="right")
        ttk.Button(discord, text="Choose bot token file", command=self.choose_discord_token).pack(anchor="w", pady=(0, 10))
        self.discord_guilds = {}
        self.discord_channels = {}
        ttk.Separator(discord).pack(fill="x", pady=(0, 12))
        ttk.Label(discord, text="Optional webhook fallback", style="Muted.TLabel").pack(anchor="w")
        self.discord_webhook = tk.StringVar()
        ttk.Entry(discord, textvariable=self.discord_webhook, show="•").pack(fill="x", pady=(5, 14))
        ttk.Label(discord, text="Announcement preview").pack(anchor="w")
        self.discord_message = tk.Text(discord, height=12, wrap="word", bg="#151c32", fg="#ffffff",
                                       insertbackground="#ffffff", relief="flat", padx=12, pady=12,
                                       selectbackground="#6548dc")
        self.discord_message.pack(fill="both", expand=True, pady=(5, 14))
        discord_actions = ttk.Frame(discord)
        discord_actions.pack(fill="x")
        ttk.Button(discord_actions, text="Generate from stream setup", command=self.generate_announcement).pack(side="left")
        ttk.Button(discord_actions, text="Send to Discord", style="Accent.TButton",
                   command=self.send_discord).pack(side="right")
        ttk.Button(discord_actions, text="Webhook help", command=lambda: webbrowser.open(
            "https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks")).pack(side="right", padx=8)

        ttk.Label(tiktok, text="TikTok draft uploader", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(tiktok, text="Connect your own account, choose a video, then send it to TikTok as a draft.\n"
                  "You finish editing and publishing from the TikTok inbox notification.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 16))
        self.tiktok_key = tk.StringVar()
        self.tiktok_secret = tk.StringVar()
        self.tiktok_video = tk.StringVar()
        self.tiktok_publish_id = tk.StringVar()
        for label, variable, hidden in (("Client key", self.tiktok_key, False),
                                        ("Client secret", self.tiktok_secret, True)):
            line = ttk.Frame(tiktok); line.pack(fill="x", pady=5)
            ttk.Label(line, text=label, width=16).pack(side="left")
            ttk.Entry(line, textvariable=variable, show="•" if hidden else "").pack(side="left", fill="x", expand=True)
        ttk.Button(tiktok, text="Save credentials", command=self.save_tiktok_credentials).pack(anchor="w", pady=(8, 14))
        row = ttk.Frame(tiktok); row.pack(fill="x", pady=5)
        ttk.Entry(row, textvariable=self.tiktok_video, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Choose video", command=self.choose_tiktok_video).pack(side="left", padx=(8, 0))
        actions = ttk.Frame(tiktok); actions.pack(fill="x", pady=14)
        ttk.Button(actions, text="Connect TikTok", style="Accent.TButton", command=self.connect_tiktok).pack(side="left")
        ttk.Button(actions, text="Upload as draft", command=self.upload_tiktok).pack(side="left", padx=8)
        ttk.Button(actions, text="Check status", command=self.check_tiktok_status).pack(side="left")
        self.tiktok_status = ttk.Label(tiktok, text="Not connected", wraplength=690)
        self.tiktok_status.pack(anchor="w", pady=10)

        ttk.Label(youtube, text="YouTube Live scheduler", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(youtube, text="Connect your channel and create a scheduled broadcast from the stream setup.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 16))
        self.youtube_start = tk.StringVar(value=(datetime.now() + timedelta(days=1)).replace(
            hour=19, minute=0, second=0, microsecond=0).isoformat(timespec="minutes"))
        self.youtube_privacy = tk.StringVar(value="private")
        line = ttk.Frame(youtube); line.pack(fill="x", pady=5)
        ttk.Label(line, text="Start (local time)", width=18).pack(side="left")
        ttk.Entry(line, textvariable=self.youtube_start).pack(side="left", fill="x", expand=True)
        ttk.Label(youtube, text="Use YYYY-MM-DDTHH:MM, for example 2026-09-02T19:00",
                  style="Muted.TLabel").pack(anchor="w", padx=(145, 0))
        line = ttk.Frame(youtube); line.pack(fill="x", pady=10)
        ttk.Label(line, text="Privacy", width=18).pack(side="left")
        ttk.Combobox(line, textvariable=self.youtube_privacy, values=("private", "unlisted", "public"),
                     state="readonly").pack(side="left", fill="x", expand=True)
        actions = ttk.Frame(youtube); actions.pack(fill="x", pady=14)
        ttk.Button(actions, text="Connect YouTube", style="Accent.TButton",
                   command=self.connect_youtube).pack(side="left")
        ttk.Button(actions, text="Create scheduled broadcast",
                   command=self.create_youtube_broadcast).pack(side="left", padx=8)
        self.youtube_status = ttk.Label(youtube, text="Not connected", wraplength=690)
        self.youtube_status.pack(anchor="w", pady=10)

    def load(self):
        values = self.settings
        self.platform.set(values.get("platform", "YouTube"))
        self.title_var.set(values.get("title", "")); self.category.set(values.get("category", ""))
        self.tags.set(values.get("tags", "")); self.channel.set(values.get("channel", ""))
        self.description.insert("1.0", values.get("description", ""))
        self.obs_host.set(values.get("obs_host", "localhost")); self.obs_port.set(str(values.get("obs_port", 4455)))
        self.obs_password.set(get_secret("obs_password"))
        self.tiktok_key.set(values.get("tiktok_client_key", "") or
                            get_secret("tiktok_client_key") or self._private_text("tiktok-client-key.txt"))
        self.tiktok_secret.set(get_secret("tiktok_client_secret") or
                               self._private_text("tiktok-client-secret.txt"))
        self.tiktok_publish_id.set(values.get("tiktok_publish_id", ""))
        for variable, checked in zip(self.check_vars, values.get("checklist", [])):
            variable.set(checked)

    def save(self):
        self.settings.update(platform=self.platform.get(), title=self.title_var.get(),
            category=self.category.get(), tags=self.tags.get(), channel=self.channel.get().strip(),
            description=self.description.get("1.0", "end-1c"), obs_host=self.obs_host.get().strip(),
            obs_port=self.obs_port.get().strip(),
            checklist=[item.get() for item in self.check_vars])
        self.owner.save()

    def save_tiktok_credentials(self):
        self.settings["tiktok_client_key"] = self.tiktok_key.get().strip()
        set_secret("tiktok_client_key", self.tiktok_key.get().strip())
        set_secret("tiktok_client_secret", self.tiktok_secret.get().strip())
        self.owner.save()
        self.tiktok_status.configure(text="TikTok credentials saved in the local credential vault")

    @staticmethod
    def _private_text(filename):
        """Load a locally protected credential without logging or displaying it."""
        candidates = [Path.home() / "ScheduleBot" / "private" / filename]
        if os.getenv("APPDATA"):
            candidates.insert(0, Path(os.environ["APPDATA"]) / "ScheduleBot" / "private" / filename)
        for path in candidates:
            try:
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return value
            except OSError:
                pass
        return ""

    def choose_tiktok_video(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a TikTok video",
            filetypes=(("Videos", "*.mp4 *.mov *.webm"), ("All files", "*.*")))
        if path:
            self.tiktok_video.set(path)

    def _tiktok_client(self):
        return TikTokClient(self.tiktok_key.get(), self.tiktok_secret.get())

    def connect_tiktok(self):
        self.save_tiktok_credentials()
        self.tiktok_status.configure(text="Waiting for TikTok login and consent in your browser…")
        def work():
            try:
                self._tiktok_client().connect()
                self.after(0, lambda: self.tiktok_status.configure(text="TikTok account connected"))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("TikTok connection failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def upload_tiktok(self):
        self.save_tiktok_credentials()
        path = Path(self.tiktok_video.get())
        if not path.is_file():
            messagebox.showerror("Video needed", "Choose an MP4, MOV, or WebM video first.", parent=self); return
        self.tiktok_status.configure(text="Uploading draft to TikTok…")
        def work():
            try:
                publish_id = self._tiktok_client().upload_draft(path)
                self.tiktok_publish_id.set(publish_id)
                self.settings["tiktok_publish_id"] = publish_id; self.owner.save()
                self.after(0, lambda: self.tiktok_status.configure(
                    text="Draft uploaded. Open TikTok and use the inbox notification to finish publishing."))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("TikTok upload failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def check_tiktok_status(self):
        if not self.tiktok_publish_id.get():
            messagebox.showerror("No upload", "Upload a draft first.", parent=self); return
        def work():
            try:
                result = self._tiktok_client().status(self.tiktok_publish_id.get())
                status = result.get("data", {}).get("status", json.dumps(result.get("data", {})))
                self.after(0, lambda: self.tiktok_status.configure(text=f"TikTok status: {status}"))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("TikTok status failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def youtube_credentials_path():
        candidates = [Path.home() / "ScheduleBot" / "private" / "youtube-client-secret.json"]
        if os.getenv("APPDATA"):
            candidates.insert(0, Path(os.environ["APPDATA"]) / "ScheduleBot" / "private" / "youtube-client-secret.json")
        return next((path for path in candidates if path.is_file()), candidates[0])

    def connect_youtube(self):
        path = self.youtube_credentials_path()
        if not path.is_file():
            messagebox.showerror("Google OAuth file needed",
                "Put your Desktop OAuth JSON at ScheduleBot/private/youtube-client-secret.json.", parent=self); return
        self.youtube_status.configure(text="Waiting for Google login and consent in your browser…")
        def work():
            try:
                YouTubeClient(path).connect()
                self.after(0, lambda: self.youtube_status.configure(text="YouTube account connected"))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("YouTube connection failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def create_youtube_broadcast(self):
        title = self.title_var.get().strip()
        if not title:
            messagebox.showerror("Title needed", "Enter a stream title on the Stream setup tab first.", parent=self); return
        description = self.description.get("1.0", "end-1c")
        start, privacy, path = self.youtube_start.get(), self.youtube_privacy.get(), self.youtube_credentials_path()
        self.youtube_status.configure(text="Creating YouTube broadcast…")
        def work():
            try:
                result = YouTubeClient(path).create_broadcast(title, description, start, privacy)
                video_id = result.get("id", "")
                self.after(0, lambda: self.youtube_status.configure(
                    text=f"Broadcast created: https://youtu.be/{video_id}"))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("YouTube scheduling failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def save_with_notice(self):
        self.save()
        messagebox.showinfo("Saved", "Your stream setup is saved inside ScheduleBot.", parent=self)

    def close(self):
        self.save()
        self.destroy()

    def open_dashboard(self):
        self.save(); webbrowser.open(PLATFORM_URLS[self.platform.get()]["dashboard"])

    def open_live(self):
        self.save()
        url = PLATFORM_URLS[self.platform.get()]["live"]
        if "{channel}" in url and not self.channel.get().strip():
            messagebox.showerror("Channel needed", "Enter your Twitch channel name first.", parent=self); return
        webbrowser.open(url.format(channel=self.channel.get().strip()))

    def generate_announcement(self):
        self.save()
        platform = self.platform.get()
        parts = [f"🔴 **Going live on {platform}!**"]
        if self.title_var.get().strip(): parts.append(f"**{self.title_var.get().strip()}**")
        if self.category.get().strip(): parts.append(f"Category: {self.category.get().strip()}")
        if self.description.get("1.0", "end-1c").strip(): parts.append(self.description.get("1.0", "end-1c").strip())
        channel = self.channel.get().strip()
        if channel:
            url = f"https://twitch.tv/{channel}" if platform == "Twitch" else f"https://youtube.com/@{channel}/live"
            parts.append(url)
        self.discord_message.delete("1.0", "end")
        self.discord_message.insert("1.0", "\n\n".join(parts))

    def send_discord(self):
        channel_name = self.discord_channel.get()
        if channel_name and channel_name in self.discord_channels:
            message = self.discord_message.get("1.0", "end-1c").strip()
            if not message:
                messagebox.showerror("Nothing to send", "Generate or type an announcement first.", parent=self); return
            threading.Thread(target=self._post_discord_bot,
                             args=(self.discord_channels[channel_name], message), daemon=True).start()
            return
        url = self.discord_webhook.get().strip()
        message = self.discord_message.get("1.0", "end-1c").strip()
        if not (url.startswith("https://discord.com/api/webhooks/") or
                url.startswith("https://discordapp.com/api/webhooks/")):
            messagebox.showerror("Invalid webhook", "Paste a Discord channel webhook URL.", parent=self); return
        if not message:
            messagebox.showerror("Nothing to send", "Generate or type an announcement first.", parent=self); return
        self.obs_status.configure(text="Sending Discord announcement…")
        threading.Thread(target=self._post_discord, args=(url, message), daemon=True).start()

    @staticmethod
    def discord_token():
        secured = get_secret("discord_bot_token")
        if secured:
            return secured
        candidates = [Path.home() / "ScheduleBot" / "private" / "discord-token.txt"]
        if os.getenv("APPDATA"):
            candidates.insert(0, Path(os.environ["APPDATA"]) / "ScheduleBot" / "discord-token.txt")
        for path in candidates:
            try:
                token = path.read_text(encoding="utf-8").strip()
                if token: return token
            except OSError:
                pass
        return ""

    def choose_discord_token(self):
        path = filedialog.askopenfilename(title="Choose Discord bot token file",
                                          filetypes=(("Text files", "*.txt"), ("All files", "*.*")), parent=self)
        if not path:
            return
        try:
            token = Path(path).read_text(encoding="utf-8").strip()
            if not token or "." not in token:
                raise ValueError("The selected file does not contain a Discord bot token.")
            if not set_secret("discord_bot_token", token):
                raise RuntimeError("The operating system credential vault is unavailable.")
            messagebox.showinfo("Token secured", "The bot token was saved in your operating system credential vault.", parent=self)
        except Exception as error:
            messagebox.showerror("Could not use token file", str(error), parent=self)

    @classmethod
    def discord_api(cls, path, method="GET", payload=None):
        token = cls.discord_token()
        if not token: raise RuntimeError("Discord token file is missing or empty.")
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request("https://discord.com/api/v10" + path, data=data, method=method,
            headers={"Authorization": "Bot " + token, "Content-Type": "application/json",
                     "User-Agent": "ScheduleBot/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read()
            return json.loads(body) if body else None

    def load_discord(self):
        self.discord_guild.configure(values=("Loading…",)); self.discord_guild.set("Loading…")
        threading.Thread(target=self._load_discord, daemon=True).start()

    def _load_discord(self):
        try:
            guilds = self.discord_api("/users/@me/guilds")
            loaded = {}
            for guild in guilds:
                channels = self.discord_api(f"/guilds/{guild['id']}/channels")
                text_channels = sorted((c for c in channels if c.get("type") in (0, 5)),
                                       key=lambda c: (c.get("position", 0), c.get("name", "")))
                loaded[guild["name"]] = {"# " + c["name"]: c["id"] for c in text_channels}
            self.after(0, lambda: self._apply_discord_guilds(loaded))
        except Exception as error:
            self.after(0, lambda detail=str(error): messagebox.showerror("Discord connection failed", detail, parent=self))

    def _apply_discord_guilds(self, loaded):
        self.discord_guilds = loaded
        names = sorted(loaded, key=str.casefold)
        self.discord_guild.configure(values=names)
        self.discord_guild.set(names[0] if names else "No servers visible")
        self.show_discord_channels()

    def show_discord_channels(self, _event=None):
        self.discord_channels = self.discord_guilds.get(self.discord_guild.get(), {})
        names = list(self.discord_channels)
        self.discord_channel.configure(values=names)
        self.discord_channel.set(names[0] if names else "")

    def _post_discord_bot(self, channel_id, message):
        try:
            self.discord_api(f"/channels/{channel_id}/messages", method="POST", payload={"content": message})
            self.after(0, lambda: messagebox.showinfo("Posted", "Announcement sent to the selected Discord channel.", parent=self))
        except Exception as error:
            self.after(0, lambda detail=str(error): messagebox.showerror("Discord post failed", detail, parent=self))

    def _post_discord(self, url, message):
        try:
            request = urllib.request.Request(url, data=json.dumps({"content": message}).encode(),
                                             headers={"Content-Type": "application/json", "User-Agent": "ScheduleBot/1.0"},
                                             method="POST")
            with urllib.request.urlopen(request, timeout=12) as response:
                if response.status not in (200, 204): raise RuntimeError(f"Discord returned status {response.status}")
            self.after(0, lambda: messagebox.showinfo("Posted", "Announcement sent to the Discord channel.", parent=self))
        except Exception as error:
            self.after(0, lambda detail=str(error): messagebox.showerror("Discord post failed", detail, parent=self))

    def connect_obs(self):
        if obs is None:
            messagebox.showerror("OBS support missing", "Reinstall the latest ScheduleBot build.", parent=self); return
        try:
            self.save()
            password = self.obs_password.get() or self.local_obs_password()
            if password:
                self.obs_password.set(password)
                set_secret("obs_password", password)
            self.obs_client = obs.ReqClient(host=self.obs_host.get(), port=int(self.obs_port.get()),
                                            password=password, timeout=3)
            response = self.obs_client.get_scene_list()
            names = [item["sceneName"] for item in response.scenes]
            self.scene.configure(values=names)
            self.scene.set(response.current_program_scene_name)
            self.obs_status.configure(text="Connected to OBS")
        except Exception as error:
            self.obs_client = None
            messagebox.showerror("OBS connection failed", str(error), parent=self)

    @staticmethod
    def local_obs_password():
        """Read credentials only from OBS on this computer; never log them."""
        candidates = [
            Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) /
                "obs-studio" / "plugin_config" / "obs-websocket" / "config.json",
        ]
        if os.getenv("APPDATA"):
            candidates.append(Path(os.environ["APPDATA"]) / "obs-studio" /
                              "plugin_config" / "obs-websocket" / "config.json")
        for path in candidates:
            try:
                config = json.loads(path.read_text(encoding="utf-8"))
                if config.get("auth_required"):
                    return config.get("server_password", "")
            except (OSError, ValueError):
                continue
        return ""

    def change_scene(self, _event=None):
        if self.obs_client:
            try: self.obs_client.set_current_program_scene(self.scene.get())
            except Exception as error: messagebox.showerror("Scene change failed", str(error), parent=self)

    def start_stream(self):
        if not self.obs_client: messagebox.showwarning("Connect first", "Connect to OBS first.", parent=self); return
        if messagebox.askyesno("Start streaming?", "This can begin a public broadcast. Continue?", parent=self):
            try: self.obs_client.start_stream(); self.obs_status.configure(text="OBS is streaming")
            except Exception as error: messagebox.showerror("Could not start", str(error), parent=self)

    def stop_stream(self):
        if not self.obs_client: return
        if messagebox.askyesno("Stop streaming?", "End the current broadcast?", parent=self):
            try: self.obs_client.stop_stream(); self.obs_status.configure(text="Stream stopped")
            except Exception as error: messagebox.showerror("Could not stop", str(error), parent=self)
