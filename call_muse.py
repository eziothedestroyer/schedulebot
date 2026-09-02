"""Call Muse without embedding or logging the API key."""
import os
from pathlib import Path
import requests

key = os.environ.get("MODEL_API_KEY")
if not key:
    key_file = Path.home() / "ScheduleBot" / "private" / "muse-api-key.txt"
    key = key_file.read_text(encoding="utf-8").strip() if key_file.is_file() else ""
if not key:
    raise SystemExit("MODEL_API_KEY is missing. Save it in private/muse-api-key.txt.")

response = requests.post(
    "https://api.meta.ai/v1/responses",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={"model": "muse-spark-1.2", "input": [{"role": "user", "content": [{
        "type": "input_text",
        "text": "Write a script that randomly generates a haiku about Meta, and briefly explain which language you chose."
    }]}], "stream": False},
    timeout=60,
)
response.raise_for_status()
print(response.json())
