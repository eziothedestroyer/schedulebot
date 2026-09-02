"""Free local AI helper for ScheduleBot using Ollama; no API key required."""
import requests


def ask(prompt, model="llama3.2"):
    response = requests.post("http://127.0.0.1:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False}, timeout=180)
    response.raise_for_status()
    return response.json()["response"]


if __name__ == "__main__":
    print(ask("Write one short haiku about creators planning a livestream."))
