"""Local-AI highlight planning for VOD transcripts."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


def _json_from_text(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("The AI did not return a highlight list. Try Analyze again.")
    items = json.loads(match.group(0))
    cleaned = []
    for item in items[:12]:
        if not all(key in item for key in ("start", "end", "title")):
            continue
        cleaned.append({"start": str(item["start"]), "end": str(item["end"]),
                        "title": str(item["title"])[:100],
                        "reason": str(item.get("reason", ""))[:200]})
    if not cleaned:
        raise ValueError("The AI response contained no usable highlights.")
    return cleaned


def _prompt(transcript):
    if not transcript.strip():
        raise ValueError("Choose a transcript (.txt, .srt, or .vtt) for this VOD first.")
    return """You are a professional livestream highlight editor. Analyze this timestamped VOD transcript.
Choose 3 to 8 self-contained, entertaining clips between 15 and 60 seconds. Prefer funny reactions,
strong opinions, wins, failures, surprises, and useful explanations. Avoid dead air and private information.
Return ONLY a JSON array. Each object must contain start, end, title, and reason. Times must be HH:MM:SS.

TRANSCRIPT:
""" + transcript[:120000]


def analyze_local(transcript, model="llama3.2"):
    prompt = _prompt(transcript)
    request = urllib.request.Request("http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": model, "prompt": prompt, "stream": False}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("Local AI is unavailable. Start Ollama and install llama3.2 with: ollama pull llama3.2") from error
    return _json_from_text(result.get("response", ""))


def analyze_openai(transcript, api_key, model="gpt-5.6-luna"):
    if not api_key.strip():
        raise ValueError("Enter and save an OpenAI API key first.")
    request = urllib.request.Request("https://api.openai.com/v1/responses",
        data=json.dumps({"model": model.strip(), "input": _prompt(transcript),
                         "store": False, "max_output_tokens": 3000}).encode(),
        headers={"Authorization": "Bearer " + api_key.strip(),
                 "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read()).get("error", {}).get("message", str(error))
        except Exception:
            detail = str(error)
        raise RuntimeError("OpenAI request failed: " + detail) from error
    text = "".join(content.get("text", "") for item in result.get("output", [])
                   if item.get("type") == "message" for content in item.get("content", [])
                   if content.get("type") == "output_text")
    return _json_from_text(text)
