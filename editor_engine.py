"""Non-destructive FFmpeg editing helpers used by ScheduleBot."""
from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path

PRESETS = {
    "YouTube 1080p": ("1920:1080", "8000k", "192k"),
    "Twitch 1080p": ("1920:1080", "6000k", "160k"),
    "Vertical video": ("1080:1920", "6000k", "160k"),
    "YouTube Shorts": ("1080:1920", "6000k", "160k"),
    "Instagram Reels": ("1080:1920", "6000k", "160k"),
    "Discord compact": ("1280:720", "2500k", "128k"),
}

def available():
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

def preview(path):
    """Open a non-destructive preview using the FFmpeg companion player."""
    player = shutil.which("ffplay")
    if not player:
        raise FileNotFoundError("Video preview needs ffplay from the FFmpeg package.")
    subprocess.Popen([player, "-autoexit", str(path)], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def probe(path):
    output = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_name,width,height", "-of", "json", str(path)], text=True)
    return json.loads(output)

def trim(source, destination, start, end):
    subprocess.run(["ffmpeg", "-y", "-ss", start, "-to", end, "-i", str(source),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac",
        "-b:a", "160k", "-movflags", "+faststart", str(destination)], check=True)

def combine(sources, destination):
    command = ["ffmpeg", "-y"]
    for source in sources: command += ["-i", str(source)]
    joins = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(len(sources)))
    command += ["-filter_complex", f"{joins}concat=n={len(sources)}:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "20",
        "-c:a", "aac", "-movflags", "+faststart", str(destination)]
    subprocess.run(command, check=True)

def export(source, destination, preset):
    resolution, video_rate, audio_rate = PRESETS[preset]
    width, height = resolution.split(":")
    vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    subprocess.run(["ffmpeg", "-y", "-i", str(source), "-vf", vf, "-c:v", "libx264",
        "-preset", "medium", "-b:v", video_rate, "-maxrate", video_rate,
        "-bufsize", str(int(video_rate[:-1]) * 2) + "k", "-c:a", "aac", "-b:a", audio_rate,
        "-movflags", "+faststart", str(destination)], check=True)

def thumbnail(source, destination, timestamp="00:00:01"):
    subprocess.run(["ffmpeg", "-y", "-ss", timestamp, "-i", str(source), "-frames:v", "1",
                    "-q:v", "2", str(destination)], check=True)

def extract_audio(source, destination):
    subprocess.run(["ffmpeg", "-y", "-i", str(source), "-vn", "-c:a", "libmp3lame",
                    "-q:a", "2", str(destination)], check=True)

def animated_gif(source, destination, start="00:00:00"):
    vf = "fps=12,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    subprocess.run(["ffmpeg", "-y", "-ss", start, "-t", "6", "-i", str(source),
                    "-filter_complex", vf, str(destination)], check=True)
