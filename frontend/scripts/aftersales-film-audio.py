"""Create narrated film timing, word-aligned captions and a quiet original score.

Uses the existing Edge TTS dependency and the existing workflow film's original
music synthesizer. Only the public narration in story.json is sent to TTS.
Run from frontend/: python scripts/aftersales-film-audio.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import wave

import edge_tts
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "agentic-commerce/film-sources/aftersales"
PUBLIC = ROOT / "public/films"
STORY = json.loads((SOURCE / "story.json").read_text(encoding="utf-8"))


def stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def duration(path: Path) -> float:
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path),
    ], text=True).strip())


async def build() -> None:
    SOURCE.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    music_module = runpy.run_path(str(ROOT / "scripts/workflow-film-audio.py"))
    for film, scenes in STORY["films"].items():
        at, timeline, captions = 0.0, [], []
        folder = SOURCE / film
        folder.mkdir(exist_ok=True)
        for index, scene in enumerate(scenes):
            path = folder / f"{index}.mp3"
            metadata = folder / f"{index}.words.json"
            signature = hashlib.sha256(json.dumps([
                scene["vo"], STORY["voice"], STORY["rate"]
            ]).encode()).hexdigest()
            cached = json.loads(metadata.read_text(encoding="utf-8")) if metadata.exists() else {}
            if not path.exists() or not cached or (
                isinstance(cached, dict) and cached.get("signature") != signature
            ):
                words = []
                voice = edge_tts.Communicate(
                    scene["vo"], STORY["voice"], rate=STORY["rate"], boundary="WordBoundary"
                )
                with path.open("wb") as audio:
                    async for chunk in voice.stream():
                        if chunk["type"] == "audio":
                            audio.write(chunk["data"])
                        elif chunk["type"] == "WordBoundary":
                            words.append({"text": chunk["text"], "start": chunk["offset"] / 1e7,
                                          "end": (chunk["offset"] + chunk["duration"]) / 1e7})
                cached = words
            words = cached if isinstance(cached, list) else cached["words"]
            metadata.write_text(json.dumps({"signature": signature, "words": words}), encoding="utf-8")
            voice_seconds = duration(path)
            frames = int(np.ceil((voice_seconds + 1.65) * STORY["fps"]))
            seconds = frames / STORY["fps"]
            # Restore the authored punctuation; keep short cues at sentence boundaries.
            authored = scene["vo"].split()
            if len(authored) != len(words):
                raise ValueError(f"Review the word alignment for {film} scene {index + 1}")
            groups, group = [], []
            for word, text in zip(words, authored):
                group.append({**word, "text": text})
                if len(group) == 8 or text.endswith((".", "?", "!")):
                    groups.append(group)
                    group = []
            if group:
                groups.append(group)
            for group_index, group in enumerate(groups):
                end = group[-1]["end"] + .12
                if group_index + 1 < len(groups):
                    end = min(end, groups[group_index + 1][0]["start"] - .02)
                captions.append({"text": " ".join(w["text"] for w in group),
                                 "start": round(at + .55 + group[0]["start"], 3),
                                 "end": round(at + .55 + end, 3)})
            timeline.append({**scene, "start": round(at, 5), "frames": frames,
                             "seconds": seconds, "audio": f"{film}/{index}.mp3"})
            at += seconds
            print(f"{film}: scene {index + 1}/{len(scenes)} ready", flush=True)
        data = {"fps": STORY["fps"], "frames": sum(s["frames"] for s in timeline),
                "seconds": at, "scenes": timeline, "captions": captions}
        (SOURCE / f"{film}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        vtt = ["WEBVTT", ""]
        for cue in captions:
            vtt += [f"{stamp(cue['start'])} --> {stamp(cue['end'])}", cue["text"], ""]
        (folder / "captions.vtt").write_text("\n".join(vtt), encoding="utf-8")
        (SOURCE / f"{film}-transcript.txt").write_text(
            "\n\n".join(s["vo"] for s in scenes), encoding="utf-8")
        if "--captions-only" in sys.argv:
            print(f"{film}: captions and timing refreshed", flush=True)
            continue
        # Reuse the site's original score, mixed quietly beneath the narration.
        score = (music_module["music"](at) * 32767).astype(np.int16)
        masters = ROOT / "agentic-commerce/film-masters"
        masters.mkdir(parents=True, exist_ok=True)
        wav = masters / f"{film}-music.wav"
        with wave.open(str(wav), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(music_module["SR"])
            output.writeframes(score.tobytes())
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav),
                        "-b:a", "160k", str(folder / "music.mp3")], check=True)
        print(f"{film}: {at:.1f}s, voiceover, captions and music ready", flush=True)


if __name__ == "__main__":
    asyncio.run(build())
