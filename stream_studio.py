from __future__ import annotations

import tkinter as tk
import webbrowser
import json
import threading
import urllib.error
import urllib.request
import os
import subprocess
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from credential_store import get as get_secret, set_secret
from youtube_client import YouTubeClient
from twitch_client import TwitchClient
import editor_engine
import ai_vod

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
        status_bar = ttk.Frame(self, style="Card.TFrame", padding=(16, 10))
        status_bar.pack(fill="x", padx=20, pady=(4, 0))
        ttk.Label(status_bar, text="NOW", style="Card.TLabel",
                  font=("Segoe UI", 9, "bold"), foreground="#9a84ff").pack(side="left")
        self.activity_status = tk.StringVar(value="Ready — choose a tab or run Check readiness")
        ttk.Label(status_bar, textvariable=self.activity_status, style="Card.TLabel",
                  font=("Segoe UI", 11, "bold"), wraplength=650).pack(side="left", padx=(12, 0))
        book = ttk.Notebook(self, padding=16)
        book.pack(fill="both", expand=True)
        planner, controls, recording, ai_editor, vtuber, discord, youtube, twitch, activity = (
            ttk.Frame(book, padding=20) for _ in range(9))
        book.add(planner, text="Stream setup")
        book.add(controls, text="OBS controls")
        book.add(recording, text="Record + Edit")
        book.add(ai_editor, text="AI VOD")
        book.add(vtuber, text="VTuber")
        book.add(discord, text="Discord")
        book.add(youtube, text="YouTube")
        book.add(twitch, text="Twitch")
        book.add(activity, text="Activity")

        ttk.Label(activity, text="What ScheduleBot is doing", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(activity, text="Newest activity appears at the top. Errors and waiting steps stay visible here.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 12))
        activity_frame = ttk.Frame(activity)
        activity_frame.pack(fill="both", expand=True)
        self.activity_log = tk.Text(activity_frame, wrap="word", state="disabled", bg="#121a2e",
                                    fg="#e8ecff", relief="flat", padx=14, pady=14,
                                    font=("Segoe UI", 10), spacing3=7)
        activity_scroll = ttk.Scrollbar(activity_frame, orient="vertical", command=self.activity_log.yview)
        self.activity_log.configure(yscrollcommand=activity_scroll.set)
        self.activity_log.pack(side="left", fill="both", expand=True)
        activity_scroll.pack(side="right", fill="y")
        ttk.Button(activity, text="Clear activity", command=self.clear_activity).pack(anchor="e", pady=(10, 0))
        self.log_activity("Ready", "Choose a tab or run Check readiness.")

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
        launch = ttk.LabelFrame(planner, text="Creator Launch", padding=12)
        launch.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.launch_record = tk.BooleanVar(value=True)
        self.launch_discord = tk.BooleanVar(value=False)
        self.launch_vtuber = tk.BooleanVar(value=False)
        ttk.Checkbutton(launch, text="Record in OBS", variable=self.launch_record).pack(side="left")
        ttk.Checkbutton(launch, text="Post Discord announcement", variable=self.launch_discord).pack(
            side="left", padx=10)
        ttk.Checkbutton(launch, text="Start Virtual Camera", variable=self.launch_vtuber).pack(side="left")
        launch_buttons = ttk.Frame(planner)
        launch_buttons.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(launch_buttons, text="Check readiness", command=self.show_preflight).pack(side="left")
        ttk.Button(launch_buttons, text="●  Start complete session", style="Accent.TButton",
                   command=self.start_creator_session).pack(side="right")
        ttk.Button(launch_buttons, text="■  End session", style="Danger.TButton",
                   command=self.end_creator_session).pack(side="right", padx=8)
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

        ttk.Label(recording, text="Recording & Editing Studio", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(recording, text="Record through OBS, then trim, combine, and export with FFmpeg. Originals are never changed.",
                  style="Muted.TLabel", wraplength=700).pack(anchor="w", pady=(4, 12))
        recorder = ttk.Frame(recording); recorder.pack(fill="x")
        ttk.Button(recorder, text="● Start recording", style="Accent.TButton", command=self.start_recording).pack(side="left")
        ttk.Button(recorder, text="Pause / Resume", command=self.pause_recording).pack(side="left", padx=6)
        ttk.Button(recorder, text="Split clip", command=self.split_recording).pack(side="left")
        ttk.Button(recorder, text="■ Stop", style="Danger.TButton", command=self.stop_recording).pack(side="left", padx=6)
        ttk.Button(recorder, text="Open recordings", command=self.open_recordings).pack(side="right")
        self.record_status = ttk.Label(recording, text="Connect to OBS before recording")
        self.record_status.pack(anchor="w", pady=(8, 14))
        self.edit_files = []
        self.edit_list = tk.Listbox(recording, height=6, bg="#151c32", fg="#ffffff",
                                    selectbackground="#6548dc", relief="flat")
        self.edit_list.pack(fill="both", expand=True)
        files = ttk.Frame(recording); files.pack(fill="x", pady=8)
        ttk.Button(files, text="Add clips", command=self.add_edit_clips).pack(side="left")
        ttk.Button(files, text="Remove selected", command=self.remove_edit_clip).pack(side="left", padx=6)
        ttk.Button(files, text="Move up", command=lambda: self.move_edit_clip(-1)).pack(side="left")
        ttk.Button(files, text="Move down", command=lambda: self.move_edit_clip(1)).pack(side="left", padx=6)
        ttk.Button(files, text="Preview", command=self.preview_clip).pack(side="left")
        ttk.Button(files, text="Add to OBS", style="Accent.TButton",
                   command=self.add_clip_to_obs).pack(side="right")
        self.trim_start, self.trim_end = tk.StringVar(value="00:00:00"), tk.StringVar(value="00:00:10")
        ttk.Label(files, text="Trim start").pack(side="left", padx=(18, 4)); ttk.Entry(files, textvariable=self.trim_start, width=9).pack(side="left")
        ttk.Label(files, text="end").pack(side="left", padx=(8, 4)); ttk.Entry(files, textvariable=self.trim_end, width=9).pack(side="left")
        edit = ttk.Frame(recording); edit.pack(fill="x", pady=6)
        ttk.Button(edit, text="Trim selected", command=self.trim_clip).pack(side="left")
        ttk.Button(edit, text="Combine all", command=self.combine_clips).pack(side="left", padx=6)
        self.export_preset = tk.StringVar(value="YouTube 1080p")
        ttk.Combobox(edit, textvariable=self.export_preset, values=tuple(editor_engine.PRESETS),
                     state="readonly", width=20).pack(side="right")
        ttk.Button(edit, text="Export MP4", style="Accent.TButton", command=self.export_clip).pack(side="right", padx=6)
        content = ttk.Frame(recording); content.pack(fill="x", pady=6)
        ttk.Label(content, text="Creator tools:").pack(side="left")
        ttk.Button(content, text="Save thumbnail", command=self.save_thumbnail).pack(side="left", padx=6)
        ttk.Button(content, text="Extract MP3", command=self.extract_clip_audio).pack(side="left")
        ttk.Button(content, text="Make 6s GIF", command=self.make_clip_gif).pack(side="left", padx=6)

        ttk.Label(ai_editor, text="AI VOD Highlight Editor", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(ai_editor, text="Use a local transcript and Ollama to find highlight timestamps, titles, and clip ideas. Nothing is uploaded.",
                  style="Muted.TLabel", wraplength=690).pack(anchor="w", pady=(4, 14))
        self.ai_vod_path, self.ai_transcript_path = tk.StringVar(), tk.StringVar()
        self.ai_provider = tk.StringVar(value="OpenAI")
        self.ai_model = tk.StringVar(value="gpt-5.6-luna")
        self.openai_key = tk.StringVar()
        self.ai_highlights = []
        for label, variable, command in (("VOD", self.ai_vod_path, self.choose_ai_vod),
                                          ("Transcript", self.ai_transcript_path, self.choose_ai_transcript)):
            row = ttk.Frame(ai_editor); row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, width=12).pack(side="left")
            ttk.Entry(row, textvariable=variable, state="readonly").pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Choose", command=command).pack(side="left", padx=(8, 0))
        provider = ttk.Frame(ai_editor); provider.pack(fill="x", pady=4)
        ttk.Label(provider, text="AI provider", width=12).pack(side="left")
        provider_picker = ttk.Combobox(provider, textvariable=self.ai_provider,
            values=("OpenAI", "Local Ollama"), state="readonly", width=16)
        provider_picker.pack(side="left"); provider_picker.bind("<<ComboboxSelected>>", self.change_ai_provider)
        ttk.Label(provider, text="Model").pack(side="left", padx=(12, 4))
        ttk.Entry(provider, textvariable=self.ai_model, width=22).pack(side="left", fill="x", expand=True)
        keyrow = ttk.Frame(ai_editor); keyrow.pack(fill="x", pady=4)
        ttk.Label(keyrow, text="OpenAI API key", width=12).pack(side="left")
        ttk.Entry(keyrow, textvariable=self.openai_key, show="•").pack(side="left", fill="x", expand=True)
        ttk.Button(keyrow, text="Save securely", command=self.save_openai_settings).pack(side="left", padx=(8, 0))
        actions = ttk.Frame(ai_editor); actions.pack(fill="x", pady=10)
        ttk.Button(actions, text="Analyze with local AI", style="Accent.TButton",
                   command=self.analyze_ai_vod).pack(side="left")
        ttk.Button(actions, text="Render selected highlight", command=self.render_ai_highlight).pack(side="left", padx=8)
        self.ai_highlight_list = tk.Listbox(ai_editor, height=12, bg="#151c32", fg="#ffffff",
            selectbackground="#6548dc", relief="flat")
        self.ai_highlight_list.pack(fill="both", expand=True)
        self.ai_status = ttk.Label(ai_editor, text="Choose OpenAI or local Ollama, then provide a timestamped transcript.", wraplength=690)
        self.ai_status.pack(anchor="w", pady=8)

        ttk.Label(vtuber, text="VTuber Studio", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(vtuber, text="Launch your avatar software, prepare a dedicated OBS scene, and control OBS Virtual Camera.",
                  style="Muted.TLabel", wraplength=690).pack(anchor="w", pady=(4, 16))
        self.vtuber_app = tk.StringVar(value="VTube Studio")
        self.vtuber_executable = tk.StringVar()
        line = ttk.Frame(vtuber); line.pack(fill="x", pady=5)
        ttk.Label(line, text="Avatar software", width=18).pack(side="left")
        ttk.Combobox(line, textvariable=self.vtuber_app,
                     values=("VTube Studio", "PNGTuber Plus", "VSeeFace", "Custom"),
                     state="readonly").pack(side="left", fill="x", expand=True)
        line = ttk.Frame(vtuber); line.pack(fill="x", pady=5)
        ttk.Label(line, text="Custom executable", width=18).pack(side="left")
        ttk.Entry(line, textvariable=self.vtuber_executable).pack(side="left", fill="x", expand=True)
        ttk.Button(line, text="Choose", command=self.choose_vtuber_executable).pack(side="left", padx=(8, 0))
        actions = ttk.Frame(vtuber); actions.pack(fill="x", pady=14)
        ttk.Button(actions, text="Launch avatar app", style="Accent.TButton",
                   command=self.launch_vtuber_app).pack(side="left")
        ttk.Button(actions, text="Create / open OBS scene", command=self.setup_vtuber_scene).pack(side="left", padx=8)
        camera = ttk.Frame(vtuber); camera.pack(fill="x", pady=5)
        ttk.Button(camera, text="Start OBS Virtual Camera", command=self.start_virtual_camera).pack(side="left")
        ttk.Button(camera, text="Stop Virtual Camera", command=self.stop_virtual_camera).pack(side="left", padx=8)
        self.vtuber_status = ttk.Label(vtuber,
            text="Choose an avatar app. VTube Studio and PNGTuber Plus launch through Steam.", wraplength=690)
        self.vtuber_status.pack(anchor="w", pady=12)

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

        ttk.Label(youtube, text="YouTube Live scheduler", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(youtube, text="Connect your channel and create a scheduled broadcast from the stream setup.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 16))
        self.youtube_start = tk.StringVar(value=(datetime.now() + timedelta(days=1)).replace(
            hour=19, minute=0, second=0, microsecond=0).isoformat(timespec="minutes"))
        self.youtube_privacy = tk.StringVar(value="private")
        self.youtube_credentials = tk.StringVar()
        self.youtube_upload_path = tk.StringVar()
        line = ttk.Frame(youtube); line.pack(fill="x", pady=5)
        ttk.Label(line, text="Google OAuth JSON", width=18).pack(side="left")
        ttk.Entry(line, textvariable=self.youtube_credentials, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(line, text="Choose", command=self.choose_youtube_credentials).pack(side="left", padx=(8, 0))
        line = ttk.Frame(youtube); line.pack(fill="x", pady=5)
        ttk.Label(line, text="Video or VOD file", width=18).pack(side="left")
        ttk.Entry(line, textvariable=self.youtube_upload_path, state="readonly").pack(
            side="left", fill="x", expand=True)
        ttk.Button(line, text="Choose", command=self.choose_youtube_upload).pack(side="left", padx=(8, 0))
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
        ttk.Button(actions, text="Upload video / VOD",
                   command=self.upload_youtube_video).pack(side="left")
        self.youtube_status = ttk.Label(youtube, text="Not connected", wraplength=690)
        self.youtube_status.pack(anchor="w", pady=10)

        ttk.Label(twitch, text="Twitch channel", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(twitch, text="Authorize your Twitch account, load its channel details, and apply the title, category, and tags from Stream setup.",
                  style="Muted.TLabel", wraplength=690).pack(anchor="w", pady=(4, 16))
        self.twitch_client_id, self.twitch_client_secret = tk.StringVar(), tk.StringVar()
        for label, variable, hidden in (("Client ID", self.twitch_client_id, False),
                                         ("Client secret", self.twitch_client_secret, True)):
            line = ttk.Frame(twitch); line.pack(fill="x", pady=4)
            ttk.Label(line, text=label, width=16).pack(side="left")
            ttk.Entry(line, textvariable=variable, show="•" if hidden else "").pack(side="left", fill="x", expand=True)
        ttk.Button(twitch, text="Save Twitch credentials securely",
                   command=self.save_twitch_credentials).pack(anchor="w", pady=(5, 10))
        twitch_actions = ttk.Frame(twitch); twitch_actions.pack(fill="x", pady=8)
        ttk.Button(twitch_actions, text="Connect Twitch", style="Accent.TButton",
                   command=self.connect_twitch).pack(side="left")
        ttk.Button(twitch_actions, text="Load channel", command=self.load_twitch_channel).pack(side="left", padx=8)
        ttk.Button(twitch_actions, text="Apply stream setup", command=self.update_twitch_channel).pack(side="left")
        go_live = ttk.Frame(twitch)
        go_live.pack(fill="x", pady=(10, 6))
        ttk.Button(go_live, text="●  Go live on Twitch", style="Accent.TButton",
                   command=self.start_twitch_stream).pack(side="left", fill="x", expand=True)
        ttk.Button(go_live, text="■  End Twitch stream", style="Danger.TButton",
                   command=self.stop_twitch_stream).pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Label(twitch, text="Go Live applies your Stream setup to Twitch, then starts streaming through OBS. "
                  "Connect OBS first and make sure Twitch is selected as its streaming service.",
                  style="Muted.TLabel", wraplength=690).pack(anchor="w", pady=(0, 8))
        tools = ttk.Frame(twitch); tools.pack(fill="x", pady=8)
        self.twitch_marker = tk.StringVar()
        ttk.Entry(tools, textvariable=self.twitch_marker).pack(side="left", fill="x", expand=True)
        ttk.Button(tools, text="Add stream marker", command=self.create_twitch_marker).pack(side="left", padx=8)
        ttk.Button(tools, text="Create 30s clip", command=self.create_twitch_clip).pack(side="left")
        links = ttk.Frame(twitch); links.pack(fill="x", pady=5)
        ttk.Button(links, text="Check live status", command=self.check_twitch_live).pack(side="left")
        ttk.Button(links, text="Open chat", command=self.open_twitch_chat).pack(side="left", padx=8)
        ttk.Button(links, text="Creator Dashboard", command=lambda: webbrowser.open(
            "https://dashboard.twitch.tv/")).pack(side="left")
        self.twitch_status = ttk.Label(twitch, text="Not connected", wraplength=690)
        self.twitch_status.pack(anchor="w", pady=10)


    def load(self):
        values = self.settings
        self.platform.set(values.get("platform", "YouTube"))
        self.title_var.set(values.get("title", "")); self.category.set(values.get("category", ""))
        self.tags.set(values.get("tags", "")); self.channel.set(values.get("channel", ""))
        self.description.insert("1.0", values.get("description", ""))
        self.obs_host.set(values.get("obs_host", "localhost")); self.obs_port.set(str(values.get("obs_port", 4455)))
        self.obs_password.set(get_secret("obs_password"))
        self.twitch_client_id.set(values.get("twitch_client_id", "") or
            get_secret("twitch_client_id") or self._private_text("twitch-client-id.txt"))
        self.twitch_client_secret.set(get_secret("twitch_client_secret") or
            self._private_text("twitch-client-secret.txt"))
        self.vtuber_app.set(values.get("vtuber_app", "VTube Studio"))
        self.vtuber_executable.set(values.get("vtuber_executable", ""))
        self.ai_provider.set(values.get("ai_provider", "OpenAI"))
        self.ai_model.set(values.get("ai_model", "gpt-5.6-luna"))
        self.openai_key.set(get_secret("openai_api_key"))
        self.discord_webhook.set(get_secret("discord_webhook"))
        self.youtube_credentials.set(values.get("youtube_credentials_path", ""))
        self.launch_record.set(values.get("launch_record", True))
        self.launch_discord.set(values.get("launch_discord", False))
        self.launch_vtuber.set(values.get("launch_vtuber", False))
        for variable, checked in zip(self.check_vars, values.get("checklist", [])):
            variable.set(checked)

    def log_activity(self, action, detail=""):
        """Keep one plain-language current status plus a readable session history."""
        message = f"{action}" + (f" — {detail}" if detail else "")
        self.activity_status.set(message)
        if hasattr(self, "activity_log"):
            line = f"{datetime.now():%I:%M:%S %p}  {message}\n"
            self.activity_log.configure(state="normal")
            self.activity_log.insert("1.0", line)
            self.activity_log.configure(state="disabled")

    def clear_activity(self):
        self.activity_log.configure(state="normal")
        self.activity_log.delete("1.0", "end")
        self.activity_log.configure(state="disabled")
        self.log_activity("Activity cleared", "ScheduleBot is ready.")

    def save(self):
        self.settings.update(platform=self.platform.get(), title=self.title_var.get(),
            category=self.category.get(), tags=self.tags.get(), channel=self.channel.get().strip(),
            description=self.description.get("1.0", "end-1c"), obs_host=self.obs_host.get().strip(),
            obs_port=self.obs_port.get().strip(),
            vtuber_app=self.vtuber_app.get(), vtuber_executable=self.vtuber_executable.get().strip(),
            ai_provider=self.ai_provider.get(), ai_model=self.ai_model.get().strip(),
            launch_record=self.launch_record.get(), launch_discord=self.launch_discord.get(),
            launch_vtuber=self.launch_vtuber.get(),
            checklist=[item.get() for item in self.check_vars])
        self.owner.save()

    def choose_vtuber_executable(self):
        path = filedialog.askopenfilename(parent=self, title="Choose VTuber application")
        if path:
            self.vtuber_executable.set(path)
            self.vtuber_app.set("Custom")
            self.save()

    def launch_vtuber_app(self):
        app = self.vtuber_app.get()
        steam_apps = {"VTube Studio": "1325860", "PNGTuber Plus": "2596880"}
        try:
            if app in steam_apps:
                webbrowser.open(f"steam://rungameid/{steam_apps[app]}")
            else:
                path = Path(self.vtuber_executable.get()).expanduser()
                if not path.is_file():
                    raise FileNotFoundError(
                        f"Choose the installed {app} executable first. VSeeFace may be launched through Wine on Linux.")
                command = [str(path)]
                if os.name != "nt" and path.suffix.casefold() == ".exe":
                    wine = shutil.which("wine")
                    if not wine:
                        raise FileNotFoundError("Wine is required to launch this Windows VTuber application on Linux.")
                    command.insert(0, wine)
                subprocess.Popen(command, start_new_session=True)
            self.save()
            self.vtuber_status.configure(text=f"Launching {app}…")
        except Exception as error:
            messagebox.showerror("Could not launch VTuber app", str(error), parent=self)

    def setup_vtuber_scene(self):
        if not self._require_obs():
            return
        scene_name = "ScheduleBot VTuber"
        try:
            response = self.obs_client.get_scene_list()
            names = [item["sceneName"] for item in response.scenes]
            if scene_name not in names:
                self.obs_client.create_scene(scene_name)
                names.append(scene_name)
            self.obs_client.set_current_program_scene(scene_name)
            self.scene.configure(values=names); self.scene.set(scene_name)
            self.vtuber_status.configure(text=f"OBS scene ready for {self.vtuber_app.get()}")
            messagebox.showinfo("VTuber scene ready",
                "ScheduleBot opened the 'ScheduleBot VTuber' scene. In OBS, add a Window Capture or Game Capture "
                "source and choose your avatar application's window. Enable transparency in the avatar app when supported.",
                parent=self)
        except Exception as error:
            messagebox.showerror("Could not prepare VTuber scene", str(error), parent=self)

    def start_virtual_camera(self):
        if not self._require_obs():
            return
        try:
            self.obs_client.start_virtual_cam()
            self.vtuber_status.configure(text="OBS Virtual Camera is running")
        except Exception as error:
            messagebox.showerror("Could not start Virtual Camera", str(error), parent=self)

    def stop_virtual_camera(self):
        if not self._require_obs():
            return
        try:
            self.obs_client.stop_virtual_cam()
            self.vtuber_status.configure(text="OBS Virtual Camera stopped")
        except Exception as error:
            messagebox.showerror("Could not stop Virtual Camera", str(error), parent=self)

    def _twitch_client(self):
        return TwitchClient(self.twitch_client_id.get(), self.twitch_client_secret.get(), get_secret("twitch_access_token"),
            get_secret("twitch_refresh_token"), token_callback=self._save_twitch_tokens)

    @staticmethod
    def _save_twitch_tokens(access_token, refresh_token):
        """Persist Twitch's rotated tokens immediately without touching Tk from a worker thread."""
        if not set_secret("twitch_access_token", access_token):
            raise RuntimeError("The operating system credential vault is unavailable.")
        if refresh_token and not set_secret("twitch_refresh_token", refresh_token):
            raise RuntimeError("The operating system credential vault is unavailable.")

    def save_twitch_credentials(self):
        client_id, client_secret = self.twitch_client_id.get().strip(), self.twitch_client_secret.get().strip()
        if not client_id:
            messagebox.showerror("Client ID needed", "Enter the Twitch application Client ID.", parent=self); return False
        if not set_secret("twitch_client_id", client_id) or not set_secret("twitch_client_secret", client_secret):
            messagebox.showerror("Could not save credentials", "The operating system credential vault is unavailable.", parent=self); return False
        self.settings["twitch_client_id"] = client_id
        self.owner.save(); self.twitch_status.configure(text="Twitch credentials saved securely"); return True

    def connect_twitch(self):
        if not self.save_twitch_credentials():
            return
        self.twitch_status.configure(text="Starting Twitch authorization…")
        self.log_activity("Connecting Twitch", "Requesting a sign-in code…")
        def work():
            try:
                client = self._twitch_client()
                device = client.start_device_authorization()
                code = device.get("user_code", "")
                def show_authorization():
                    self.clipboard_clear()
                    self.clipboard_append(code)
                    self.twitch_status.configure(
                        text=f"Code {code} copied. Approve ScheduleBot in the Twitch page…")
                    self.log_activity("Waiting for Twitch", f"Approve code {code} in your browser.")
                    webbrowser.open(device["verification_uri"])
                self.after(0, show_authorization)
                token = client.finish_device_authorization(device)
                user = client.user()
                name = user.get("display_name", user["login"])
                def apply_connected():
                    self.settings["twitch_broadcaster_id"] = user["id"]
                    self.channel.set(user["login"])
                    self.owner.save()
                    self.twitch_status.configure(text=f"Connected to Twitch as {name}")
                    self.log_activity("Twitch connected", f"Signed in as {name}.")
                self.after(0, apply_connected)
            except Exception as error:
                self.after(0, lambda detail=str(error): (self.log_activity("Twitch error", detail),
                    messagebox.showerror("Twitch connection failed", detail, parent=self)))
        threading.Thread(target=work, daemon=True).start()

    def load_twitch_channel(self):
        self.twitch_status.configure(text="Loading Twitch channel…")
        def work():
            try:
                client = self._twitch_client(); user = client.user(); channel = client.channel(user["id"])
                def apply():
                    self.settings["twitch_broadcaster_id"] = user["id"]
                    self.channel.set(user["login"])
                    self.title_var.set(channel.get("title", ""))
                    self.category.set(channel.get("game_name", ""))
                    self.tags.set(", ".join(channel.get("tags", [])))
                    self.save()
                    self.twitch_status.configure(text=f"Loaded channel for {user.get('display_name', user['login'])}")
                self.after(0, apply)
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("Could not load Twitch channel", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def update_twitch_channel(self):
        title = self.title_var.get().strip()
        if not title:
            messagebox.showerror("Title needed", "Enter a stream title on the Stream setup tab first.", parent=self); return
        self.twitch_status.configure(text="Updating Twitch channel…")
        category = self.category.get().strip()
        tags = [tag.strip() for tag in self.tags.get().split(",") if tag.strip()]
        def work():
            try:
                client = self._twitch_client(); user = client.user()
                client.update_channel(user["id"], title, category, tags)
                self.after(0, lambda: self.twitch_status.configure(text="Twitch title, category, and tags updated"))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("Twitch update failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def start_twitch_stream(self):
        """Apply Twitch metadata and start the configured OBS stream as one guarded action."""
        if not self.obs_client:
            messagebox.showwarning("Connect OBS first",
                "Open the OBS controls tab and connect to OBS before going live on Twitch.", parent=self)
            return
        title = self.title_var.get().strip()
        if not title:
            messagebox.showerror("Title needed",
                "Enter a stream title on the Stream setup tab before going live.", parent=self)
            return
        if not messagebox.askyesno("Go live on Twitch?",
                "ScheduleBot will update your Twitch title, category, and tags, then tell OBS to start "
                "streaming. This can immediately begin a public broadcast. Continue?", parent=self):
            return
        self.platform.set("Twitch")
        self.save()
        category = self.category.get().strip()
        tags = [tag.strip() for tag in self.tags.get().split(",") if tag.strip()]
        self.twitch_status.configure(text="Preparing Twitch channel…")
        self.log_activity("Preparing Twitch", "Updating title, category, and tags…")

        def work():
            try:
                client = self._twitch_client()
                user = client.user()
                client.update_channel(user["id"], title, category, tags)
                self.after(0, begin_obs)
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror(
                    "Could not prepare Twitch", detail, parent=self))

        def begin_obs():
            try:
                status = self.obs_client.get_stream_status()
                if getattr(status, "output_active", False):
                    self.obs_status.configure(text="OBS is already streaming")
                    self.twitch_status.configure(text="LIVE — OBS stream is already active")
                    return
                self.obs_client.start_stream()
                self.obs_status.configure(text="OBS is streaming to Twitch")
                self.twitch_status.configure(text="LIVE — OBS is sending your stream to Twitch")
                self.log_activity("LIVE on Twitch", "OBS is sending video and audio.")
                self._start_session_extras()
            except Exception as error:
                messagebox.showerror("Could not start Twitch stream",
                    f"Twitch channel details were updated, but OBS could not start streaming:\n\n{error}",
                    parent=self)

        threading.Thread(target=work, daemon=True).start()

    def stop_twitch_stream(self):
        if not self.obs_client:
            messagebox.showwarning("Connect OBS first", "Connect to OBS before stopping its stream.", parent=self)
            return
        if not messagebox.askyesno("End Twitch stream?",
                "Tell OBS to stop the current broadcast?", parent=self):
            return
        try:
            status = self.obs_client.get_stream_status()
            if not getattr(status, "output_active", False):
                self.obs_status.configure(text="Stream is already stopped")
                self.twitch_status.configure(text="Twitch channel is offline")
                return
            self.obs_client.stop_stream()
            self.obs_status.configure(text="Stream stopped")
            self.twitch_status.configure(text="Twitch stream ended")
        except Exception as error:
            messagebox.showerror("Could not stop Twitch stream", str(error), parent=self)

    def check_twitch_live(self):
        def work():
            try:
                client = self._twitch_client(); user = client.user(); live = client.stream_status(user["id"])
                text = (f"LIVE — {live.get('viewer_count', 0)} viewers — {live.get('game_name', 'No category')}"
                        if live else f"{user.get('display_name', user['login'])} is offline")
                self.after(0, lambda: self.twitch_status.configure(text=text))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("Twitch status failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def create_twitch_marker(self):
        description = self.twitch_marker.get().strip()
        def work():
            try:
                client = self._twitch_client(); user = client.user()
                marker = client.create_marker(user["id"], description)
                position = marker.get("position_seconds", 0)
                self.after(0, lambda: self.twitch_status.configure(text=f"Stream marker added at {position} seconds"))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("Marker failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def create_twitch_clip(self):
        title = self.title_var.get().strip()
        def work():
            try:
                client = self._twitch_client(); user = client.user(); clip = client.create_clip(user["id"], title, 30)
                edit_url = clip.get("edit_url", "")
                self.after(0, lambda: self._show_created_clip(edit_url))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("Clip failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def _show_created_clip(self, edit_url):
        self.twitch_status.configure(text="Twitch clip created")
        if edit_url:
            webbrowser.open(edit_url)

    def open_twitch_chat(self):
        channel = self.channel.get().strip()
        if not channel:
            messagebox.showerror("Channel needed", "Load your Twitch channel first.", parent=self); return
        webbrowser.open(f"https://www.twitch.tv/popout/{channel}/chat?popout=")

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

    def youtube_credentials_path(self):
        selected = Path(self.youtube_credentials.get()).expanduser() if self.youtube_credentials.get() else None
        if selected and selected.is_file():
            return selected
        candidates = [Path.home() / "ScheduleBot" / "private" / "youtube-client-secret.json"]
        if os.getenv("APPDATA"):
            candidates.insert(0, Path(os.environ["APPDATA"]) / "ScheduleBot" / "private" / "youtube-client-secret.json")
        return next((path for path in candidates if path.is_file()), candidates[0])

    def choose_youtube_credentials(self):
        path = filedialog.askopenfilename(parent=self, title="Choose Google Desktop OAuth JSON",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")))
        if path:
            try:
                YouTubeClient(Path(path))
            except Exception as error:
                messagebox.showerror("Invalid Google OAuth file", str(error), parent=self); return
            self.youtube_credentials.set(path)
            self.settings["youtube_credentials_path"] = path
            self.owner.save(); self.youtube_status.configure(text="Google OAuth file selected")

    def connect_youtube(self):
        path = self.youtube_credentials_path()
        if not path.is_file():
            messagebox.showerror("Google OAuth file needed",
                "Choose a Google Desktop OAuth JSON file on the YouTube tab first.", parent=self); return
        self.youtube_status.configure(text="Waiting for Google login and consent in your browser…")
        self.log_activity("Connecting YouTube", "Waiting for Google sign-in in your browser…")
        def work():
            try:
                YouTubeClient(path).connect()
                self.after(0, lambda: (self.youtube_status.configure(text="YouTube account connected"),
                    self.log_activity("YouTube connected", "Your channel is authorized.")))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("YouTube connection failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def choose_youtube_upload(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a video or VOD to upload",
            filetypes=(("Video files", "*.mp4 *.mkv *.mov *.webm *.avi *.m4v"),
                       ("All files", "*.*")))
        if path:
            self.youtube_upload_path.set(path)
            if not self.title_var.get().strip():
                self.title_var.set(Path(path).stem)

    def upload_youtube_video(self):
        path = Path(self.youtube_upload_path.get())
        credentials = self.youtube_credentials_path()
        title = self.title_var.get().strip()
        description = self.description.get("1.0", "end-1c")
        privacy = self.youtube_privacy.get()
        tags = self.tags.get().split(",")
        if not path.is_file():
            messagebox.showerror("Video or VOD needed",
                "Choose a video or VOD file on the YouTube tab first.", parent=self); return
        if not credentials.is_file():
            messagebox.showerror("Google OAuth file needed",
                "Choose your Google Desktop OAuth JSON file first.", parent=self); return
        if not title:
            messagebox.showerror("Title needed", "Enter a stream/video title first.", parent=self); return
        if not messagebox.askyesno("Upload to YouTube?",
                f"Upload {path.name} as {privacy}?\n\nYou can keep it private until processing and checks finish.",
                parent=self):
            return
        self.youtube_status.configure(text="Starting resumable YouTube upload…")
        self.log_activity("Uploading to YouTube", f"{path.name} ({privacy})")

        def progress(sent, total):
            percent = int(sent * 100 / total)
            self.after(0, lambda value=percent: self.youtube_status.configure(
                text=f"Uploading {path.name}… {value}%"))

        def work():
            try:
                result = YouTubeClient(credentials).upload_video(
                    path, title, description, privacy, tags, progress_callback=progress)
                video_id = result.get("id", "")
                url = f"https://youtu.be/{video_id}" if video_id else "YouTube Studio"
                self.after(0, lambda: (self.youtube_status.configure(text=f"Upload complete: {url}"),
                    self.log_activity("YouTube upload complete", url)))
            except Exception as error:
                self.after(0, lambda detail=str(error): (self.log_activity("YouTube upload failed", detail),
                    messagebox.showerror("YouTube upload failed", detail, parent=self)))
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

    def preflight_items(self):
        """Return integration readiness without making external changes."""
        platform = self.platform.get()
        items = [
            ("Stream title", bool(self.title_var.get().strip()), "Enter it on Stream setup"),
            ("OBS connection", self.obs_client is not None, "Connect on OBS controls"),
        ]
        if platform == "Twitch":
            items.append(("Twitch authorization", bool(get_secret("twitch_access_token")),
                          "Connect on the Twitch tab"))
        else:
            items.append(("YouTube authorization", bool(get_secret("youtube_refresh_token")),
                          "Connect on the YouTube tab"))
        if self.launch_discord.get():
            discord_ready = bool(self.discord_webhook.get().strip() or self.discord_token())
            items.append(("Discord destination", discord_ready, "Configure Discord bot or webhook"))
        if self.launch_vtuber.get():
            items.append(("VTuber software", bool(self.vtuber_app.get().strip()), "Choose it on the VTuber tab"))
        return items

    def show_preflight(self):
        items = self.preflight_items()
        report = "\n".join(f"{'✓' if ready else '✗'}  {name}" + ("" if ready else f" — {help_text}")
                           for name, ready, help_text in items)
        ready_count = sum(ready for _name, ready, _help in items)
        self.log_activity("Readiness checked", f"{ready_count} of {len(items)} checks are ready.")
        messagebox.showinfo("Creator Launch readiness",
            f"{ready_count} of {len(items)} checks ready\n\n{report}", parent=self)

    def start_creator_session(self):
        missing = [(name, help_text) for name, ready, help_text in self.preflight_items() if not ready]
        if missing:
            details = "\n".join(f"• {name}: {help_text}" for name, help_text in missing)
            messagebox.showwarning("Setup needed", f"Finish these items before going live:\n\n{details}", parent=self)
            return
        platform = self.platform.get()
        self.log_activity("Starting creator session", f"Preparing {platform} and selected extras…")
        if platform == "Twitch":
            self.start_twitch_stream()
            return
        if not messagebox.askyesno("Go live on YouTube?",
                "ScheduleBot will tell OBS to begin streaming to its configured YouTube destination. "
                "Make sure you created or selected the correct YouTube broadcast. Continue?", parent=self):
            return
        try:
            status = self.obs_client.get_stream_status()
            if not getattr(status, "output_active", False):
                self.obs_client.start_stream()
            self.obs_status.configure(text="OBS is streaming to YouTube")
            self.youtube_status.configure(text="LIVE — OBS is sending your stream to YouTube")
            self.log_activity("LIVE on YouTube", "OBS is sending video and audio.")
            self._start_session_extras()
        except Exception as error:
            messagebox.showerror("Could not start creator session", str(error), parent=self)

    def _start_session_extras(self):
        warnings = []
        if self.launch_record.get():
            try:
                status = self.obs_client.get_record_status()
                if not getattr(status, "output_active", False):
                    self.obs_client.start_record()
                self.record_status.configure(text="Recording live session in OBS…")
                self.log_activity("Recording started", "OBS is saving a local copy.")
            except Exception as error:
                warnings.append(f"Recording: {error}")
        if self.launch_vtuber.get():
            try:
                self.obs_client.start_virtual_cam()
                self.vtuber_status.configure(text="OBS Virtual Camera is running")
                self.log_activity("Virtual Camera started", "Your avatar output is available.")
            except Exception as error:
                warnings.append(f"Virtual Camera: {error}")
        if self.launch_discord.get():
            try:
                self.generate_announcement()
                self.send_discord()
                self.log_activity("Discord announcement", "Sending the generated live message…")
            except Exception as error:
                warnings.append(f"Discord: {error}")
        if warnings:
            messagebox.showwarning("Session started with warnings", "\n\n".join(warnings), parent=self)

    def end_creator_session(self):
        if not self.obs_client:
            messagebox.showwarning("Connect OBS", "Connect to OBS before ending the session.", parent=self)
            return
        if not messagebox.askyesno("End complete session?",
                "Stop streaming, recording, and Virtual Camera in OBS?", parent=self):
            return
        errors = []
        for label, status_call, stop_call in (
                ("stream", self.obs_client.get_stream_status, self.obs_client.stop_stream),
                ("recording", self.obs_client.get_record_status, self.obs_client.stop_record),
                ("Virtual Camera", self.obs_client.get_virtual_cam_status, self.obs_client.stop_virtual_cam)):
            try:
                if getattr(status_call(), "output_active", False):
                    stop_call()
            except Exception as error:
                errors.append(f"{label}: {error}")
        self.obs_status.configure(text="Creator session ended")
        self.record_status.configure(text="Recording stopped")
        self.twitch_status.configure(text="Twitch stream ended")
        self.youtube_status.configure(text="YouTube stream ended")
        self.log_activity("Creator session ended", "Streaming, recording, and Virtual Camera were stopped.")
        if errors:
            messagebox.showwarning("Some tools did not stop cleanly", "\n".join(errors), parent=self)

    def _require_obs(self):
        if not self.obs_client:
            messagebox.showwarning("Connect OBS", "Open OBS controls and connect to OBS first.", parent=self); return False
        return True

    def start_recording(self):
        if self._require_obs():
            try: self.obs_client.start_record(); self.record_status.configure(text="Recording in OBS…")
            except Exception as error: messagebox.showerror("Recording failed", str(error), parent=self)

    def pause_recording(self):
        if self._require_obs():
            try: self.obs_client.toggle_record_pause(); self.record_status.configure(text="Recording pause toggled")
            except Exception as error: messagebox.showerror("Pause failed", str(error), parent=self)

    def split_recording(self):
        if self._require_obs():
            try: self.obs_client.split_record_file(); self.record_status.configure(text="Started a new recording clip")
            except Exception as error: messagebox.showerror("Split failed", str(error), parent=self)

    def stop_recording(self):
        if self._require_obs():
            try:
                result = self.obs_client.stop_record(); path = getattr(result, "output_path", "")
                self.record_status.configure(text=f"Saved recording: {path}" if path else "Recording stopped")
            except Exception as error: messagebox.showerror("Stop failed", str(error), parent=self)

    def recording_directory(self):
        if self.obs_client:
            try: return Path(self.obs_client.get_record_directory().record_directory)
            except Exception: pass
        return Path.home() / "Videos"

    def open_recordings(self):
        webbrowser.open(self.recording_directory().resolve().as_uri())

    def add_edit_clips(self):
        paths = filedialog.askopenfilenames(parent=self, title="Choose recordings",
            filetypes=(("Video", "*.mp4 *.mkv *.mov *.webm"), ("All files", "*.*")))
        for path in paths:
            if path not in self.edit_files: self.edit_files.append(path); self.edit_list.insert("end", Path(path).name)

    def choose_ai_vod(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a VOD",
            filetypes=(("Video", "*.mp4 *.mkv *.mov *.webm"), ("All files", "*.*")))
        if path:
            self.ai_vod_path.set(path)
            stem = Path(path).with_suffix("")
            transcript = next((candidate for extension in (".srt", ".vtt", ".txt")
                               if (candidate := stem.with_suffix(extension)).is_file()), None)
            if transcript:
                self.ai_transcript_path.set(str(transcript))

    def choose_ai_transcript(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a timestamped transcript",
            filetypes=(("Transcript", "*.txt *.srt *.vtt"), ("All files", "*.*")))
        if path:
            self.ai_transcript_path.set(path)

    def save_openai_settings(self):
        if self.openai_key.get().strip() and not self.openai_key.get().strip().startswith("sk-"):
            messagebox.showerror("Invalid API key", "OpenAI API keys normally begin with sk-.", parent=self); return
        if not set_secret("openai_api_key", self.openai_key.get().strip()):
            messagebox.showerror("Could not save key", "The operating system credential vault is unavailable.", parent=self); return
        self.save()
        self.ai_status.configure(text="OpenAI settings saved securely")

    def change_ai_provider(self, _event=None):
        self.ai_model.set("gpt-5.6-luna" if self.ai_provider.get() == "OpenAI" else "llama3.2")

    def analyze_ai_vod(self):
        vod, transcript = Path(self.ai_vod_path.get()), Path(self.ai_transcript_path.get())
        if not vod.is_file() or not transcript.is_file():
            messagebox.showerror("VOD and transcript needed", "Choose both a VOD and its timestamped transcript.", parent=self); return
        self.ai_status.configure(text="Local AI is analyzing the VOD transcript…")
        self.log_activity("Analyzing VOD", "AI is reading the selected transcript…")
        def work():
            try:
                text = transcript.read_text(encoding="utf-8", errors="replace")
                provider = self.ai_provider.get()
                if provider == "OpenAI":
                    highlights = ai_vod.analyze_openai(text, self.openai_key.get(), self.ai_model.get())
                else:
                    highlights = ai_vod.analyze_local(text, self.ai_model.get() or "llama3.2")
                def apply():
                    self.ai_highlights = highlights; self.ai_highlight_list.delete(0, "end")
                    for item in highlights:
                        self.ai_highlight_list.insert("end", f"{item['start']}–{item['end']}  {item['title']}")
                    self.ai_status.configure(text=f"Found {len(highlights)} highlight candidates. Select one to render.")
                    self.log_activity("VOD analysis complete", f"Found {len(highlights)} highlight candidates.")
                self.after(0, apply)
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("AI VOD analysis failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def render_ai_highlight(self):
        selected = self.ai_highlight_list.curselection()
        if not selected:
            messagebox.showinfo("Choose a highlight", "Select an AI highlight first.", parent=self); return
        item = self.ai_highlights[selected[0]]; source = Path(self.ai_vod_path.get())
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in item["title"]).strip()
        destination = filedialog.asksaveasfilename(parent=self, title="Save AI highlight",
            initialfile=(safe or "highlight") + ".mp4", defaultextension=".mp4",
            filetypes=(("MP4 video", "*.mp4"),))
        if destination:
            self._edit_job("Rendering AI highlight…", editor_engine.trim, source, Path(destination),
                           item["start"], item["end"])

    def remove_edit_clip(self):
        selected = self.edit_list.curselection()
        if selected:
            index = selected[0]; self.edit_list.delete(index); self.edit_files.pop(index)

    def move_edit_clip(self, direction):
        selected = self.edit_list.curselection()
        if not selected:
            return
        old = selected[0]; new = old + direction
        if new < 0 or new >= len(self.edit_files):
            return
        self.edit_files[old], self.edit_files[new] = self.edit_files[new], self.edit_files[old]
        label = self.edit_list.get(old)
        self.edit_list.delete(old); self.edit_list.insert(new, label); self.edit_list.selection_set(new)

    def preview_clip(self):
        source = self._selected_clip()
        if not source:
            messagebox.showinfo("Choose a clip", "Select a clip in the editor first.", parent=self); return
        try:
            editor_engine.preview(source)
            details = editor_engine.probe(source)
            duration = float(details.get("format", {}).get("duration", 0))
            self.record_status.configure(text=f"Previewing {source.name} — {duration:.1f} seconds")
        except Exception as error:
            messagebox.showerror("Preview failed", str(error), parent=self)

    def add_clip_to_obs(self):
        """Add the selected edit as an OBS Media Source in the active scene."""
        source = self._selected_clip()
        if not source:
            messagebox.showinfo("Choose a clip", "Select a clip in the editor first.", parent=self); return
        if not self._require_obs():
            return
        try:
            scene = self.obs_client.get_current_program_scene().current_program_scene_name
            safe_stem = "".join(character if character.isalnum() or character in " -_" else "_"
                                for character in source.stem).strip() or "Edited video"
            input_name = f"ScheduleBot - {safe_stem} - {datetime.now():%H%M%S}"
            settings = {"local_file": str(source.resolve()), "is_local_file": True,
                        "looping": False, "restart_on_activate": True, "clear_on_media_end": False}
            self.obs_client.create_input(scene, input_name, "ffmpeg_source", settings, True)
            self.record_status.configure(text=f"Added {source.name} to OBS scene: {scene}")
            messagebox.showinfo("Added to OBS",
                f"{source.name} is now a Media Source in the {scene} scene.\n\n"
                "Resize and position it in the OBS preview if needed.", parent=self)
        except Exception as error:
            messagebox.showerror("Could not add video to OBS", str(error), parent=self)

    def _selected_clip(self):
        selected = self.edit_list.curselection()
        return Path(self.edit_files[selected[0]]) if selected else None

    def _save_mp4(self, title):
        return filedialog.asksaveasfilename(parent=self, title=title, defaultextension=".mp4",
                                            filetypes=(("MP4 video", "*.mp4"),))

    def _edit_job(self, label, function, *args):
        self.record_status.configure(text=label)
        self.log_activity("Editing video", label.rstrip("…"))
        def work():
            try:
                function(*args); self.after(0, lambda: (self.record_status.configure(text=f"Finished: {args[-1]}"),
                    self.log_activity("Video edit complete", str(args[-1]))))
            except Exception as error:
                self.after(0, lambda detail=str(error): messagebox.showerror("Editing failed", detail, parent=self))
        threading.Thread(target=work, daemon=True).start()

    def trim_clip(self):
        source, destination = self._selected_clip(), self._save_mp4("Save trimmed clip")
        if source and destination: self._edit_job("Trimming clip…", editor_engine.trim, source, Path(destination), self.trim_start.get(), self.trim_end.get())

    def combine_clips(self):
        destination = self._save_mp4("Save combined video")
        if len(self.edit_files) < 2: messagebox.showwarning("Clips needed", "Add at least two clips.", parent=self); return
        if destination: self._edit_job("Combining clips…", editor_engine.combine, list(map(Path, self.edit_files)), Path(destination))

    def export_clip(self):
        source, destination = self._selected_clip(), self._save_mp4("Export platform video")
        if source and destination: self._edit_job("Exporting video…", editor_engine.export, source, Path(destination), self.export_preset.get())

    def save_thumbnail(self):
        source = self._selected_clip()
        destination = filedialog.asksaveasfilename(parent=self, title="Save thumbnail",
            defaultextension=".jpg", filetypes=(("JPEG image", "*.jpg"),)) if source else ""
        if source and destination:
            self._edit_job("Creating thumbnail…", editor_engine.thumbnail, source, Path(destination), self.trim_start.get())

    def extract_clip_audio(self):
        source = self._selected_clip()
        destination = filedialog.asksaveasfilename(parent=self, title="Save audio",
            defaultextension=".mp3", filetypes=(("MP3 audio", "*.mp3"),)) if source else ""
        if source and destination:
            self._edit_job("Extracting audio…", editor_engine.extract_audio, source, Path(destination))

    def make_clip_gif(self):
        source = self._selected_clip()
        destination = filedialog.asksaveasfilename(parent=self, title="Save animated GIF",
            defaultextension=".gif", filetypes=(("Animated GIF", "*.gif"),)) if source else ""
        if source and destination:
            self._edit_job("Creating GIF…", editor_engine.animated_gif, source, Path(destination), self.trim_start.get())


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
        if not set_secret("discord_webhook", url):
            messagebox.showerror("Could not save webhook",
                "The operating system credential vault is unavailable.", parent=self); return
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
            self.log_activity("Connecting OBS", f"Contacting {self.obs_host.get()}:{self.obs_port.get()}…")
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
            self.log_activity("OBS connected", f"Current scene: {response.current_program_scene_name}")
        except Exception as error:
            self.obs_client = None
            self.log_activity("OBS error", str(error))
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
