"""Make the two recordings the browser journey (frontend/scripts/studio-voice.e2e.mjs) uses as its microphone.

    python backend/scripts/make_voice_fixtures.py OUTPUT_DIR

Writes request.wav ("I want to build a transport management system ...") and apply.wav ("Go ahead and apply the change.") with Deepgram's
text-to-speech, then checks each one through Deepgram's speech-to-text so a recording the recognizer cannot understand is reported rather
than silently used. Needs DEEPGRAM_API_KEY (read from backend/.env or the environment); the key is never printed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings  # noqa: E402

PHRASES = {
    "request.wav": ("I want to build a transport management system for our company to manage transport requests, vehicle assignments, shipment tracking, deliveries, and exceptions.", "aura-2-thalia-en"),
    "apply.wav": ("Go ahead and apply the change.", "aura-2-thalia-en"),
}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    get_settings()
    key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not key:
        print("DEEPGRAM_API_KEY is not set")
        return 1
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Token {key}"}
    failed = False
    for name, (text, voice) in PHRASES.items():
        speech = httpx.post("https://api.deepgram.com/v1/speak", params={"model": voice, "encoding": "linear16", "container": "wav", "sample_rate": 16000}, headers=headers, json={"text": text}, timeout=60)
        speech.raise_for_status()
        (out / name).write_bytes(speech.content)
        heard = httpx.post("https://api.deepgram.com/v1/listen", params={"model": "nova-3", "smart_format": "true", "language": "en"}, headers={**headers, "Content-Type": "audio/wav"},
                           content=speech.content, timeout=60).json()["results"]["channels"][0]["alternatives"][0]["transcript"]
        ok = " ".join(heard.lower().split()).strip(".") == " ".join(text.lower().split()).strip(".")
        failed |= not ok
        print(f"{name}: " + ("ok" if ok else f"recognised differently: {heard!r}"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
