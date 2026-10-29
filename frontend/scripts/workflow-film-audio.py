"""Builds the audio of the workflow film: one neural voice-over clip per scene (edge-tts), the scene timing derived from those clips, and an original music bed.

    python frontend/scripts/workflow-film-audio.py            # voice + timing + music
    python frontend/scripts/workflow-film-audio.py --music    # music only (timing.json must exist)

Writes into frontend/agentic-commerce/film-sources/workflow/: vo/<scene>.mp3, timing.json, captions.vtt, music.mp3, sfx.mp3. The voice text is film.json's `vo`; edge-tts sends it to
Microsoft's online text-to-speech service. The music is synthesised here (no samples, no licence): a four-chord pad, bass, a plucked arpeggio and soft drums.
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1] / "agentic-commerce" / "film-sources" / "workflow"
FILM = json.loads((ROOT / "film.json").read_text(encoding="utf-8"))
SR = 44100
LEAD_IN, TAIL = 0.7, 1.0  # silence before and after each voice clip
MIN_SECONDS = {"hook": 5.5, "outro": 7.5}


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


async def voice() -> None:
    import edge_tts

    (ROOT / "vo").mkdir(exist_ok=True)
    for scene in FILM["scenes"]:
        await edge_tts.Communicate(scene["vo"], FILM["voice"], rate=FILM["rate"]).save(str(ROOT / "vo" / f"{scene['id']}.mp3"))


def timing() -> dict:
    t, scenes = 0.0, []
    for scene in FILM["scenes"]:
        vo = duration(ROOT / "vo" / f"{scene['id']}.mp3")
        length = round(max(MIN_SECONDS.get(scene["id"], 0), LEAD_IN + vo + TAIL), 2)
        scenes.append({"id": scene["id"], "start": round(t, 2), "seconds": length, "vo_start": round(t + LEAD_IN, 2), "vo_seconds": round(vo, 2)})
        t += length
    out = {"total": round(t, 2), "scenes": scenes}
    (ROOT / "timing.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


# ── music ──────────────────────────────────────────────────────────────────────────────────────
BPM = 96
BEAT = 60 / BPM
BAR = 4 * BEAT
# A minor 7, F major 7, C major 7, G 6 (MIDI notes)
CHORDS = [[57, 60, 64, 67], [53, 57, 60, 64], [48, 55, 59, 64], [55, 59, 62, 64]]
ROOTS = [45, 41, 48, 43]


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def lowpass(x: np.ndarray, f: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)


def highpass(x: np.ndarray, f: float) -> np.ndarray:
    return sosfilt(butter(2, f, btype="high", fs=SR, output="sos"), x)


def saw(freq: float, n: int, harmonics: int = 14) -> np.ndarray:
    t = np.arange(n) / SR
    return sum(np.sin(2 * np.pi * freq * k * t) / k for k in range(1, harmonics + 1) if freq * k < 9000)


def music(total: float) -> np.ndarray:
    n = int((total + 1.0) * SR)
    pad, bass, arp, drums = (np.zeros(n) for _ in range(4))
    bars = int(np.ceil(total / BAR)) + 1
    rng = np.random.default_rng(7)
    for b in range(bars):
        start = int(b * BAR * SR)
        if start >= n:
            break
        chord, root = CHORDS[b % 4], ROOTS[b % 4]
        # pad: detuned saws, soft attack and release, overlapping the next bar a little
        length = int(BAR * 1.25 * SR)
        env = np.minimum(1, np.arange(length) / (0.6 * SR)) * np.minimum(1, (length - np.arange(length)) / (0.8 * SR))
        voice_ = sum(saw(hz(m) * d, length, 10) for m in chord for d in (0.997, 1.003))
        seg = slice(start, min(n, start + length))
        pad[seg] += (voice_ * env)[: seg.stop - seg.start]
        # bass: eighth notes on the root, pumping
        for e in range(8):
            s = start + int(e * BEAT / 2 * SR)
            ln = int(BEAT / 2 * SR)
            if s >= n:
                break
            tt = np.arange(ln) / SR
            note = np.sin(2 * np.pi * hz(root) * tt) + 0.3 * np.sin(2 * np.pi * hz(root) * 2 * tt)
            env_b = np.minimum(1, tt / 0.01) * np.exp(-tt * 5)
            bass[s: s + ln] += (note * env_b)[: max(0, min(ln, n - s))]
        # arpeggio: chord tones an octave up, eighth notes, plucked triangle
        pattern = [0, 2, 1, 3, 2, 1, 3, 2]
        for e, idx in enumerate(pattern):
            s = start + int(e * BEAT / 2 * SR)
            ln = int(0.6 * SR)
            if s >= n:
                break
            tt = np.arange(ln) / SR
            f = hz(chord[idx] + 12)
            tri = 2 / np.pi * np.arcsin(np.sin(2 * np.pi * f * tt))
            arp[s: s + ln] += (tri * np.exp(-tt * 7) * np.minimum(1, tt / 0.004))[: max(0, min(ln, n - s))]
        # drums: soft kick on every beat, closed hat on the off-beats
        for k in range(4):
            s = start + int(k * BEAT * SR)
            ln = int(0.32 * SR)
            if s >= n:
                break
            tt = np.arange(ln) / SR
            kick = np.sin(2 * np.pi * (45 * tt + (110 - 45) * (1 - np.exp(-tt * 30)) / 30)) * np.exp(-tt * 9)
            drums[s: s + ln] += kick[: max(0, min(ln, n - s))]
            h = s + int(BEAT / 2 * SR)
            hl = int(0.06 * SR)
            if h + hl < n:
                drums[h: h + hl] += 0.18 * highpass(rng.standard_normal(hl), 7000) * np.exp(-np.arange(hl) / SR * 60)
    pad = lowpass(pad, 1400) * 0.05
    arp_d = arp.copy()
    delay = int(BEAT * 0.75 * SR)
    arp_d[delay:] += 0.35 * arp[:-delay]  # dotted-eighth echo
    arp = lowpass(arp_d, 3500) * 0.09
    bass = lowpass(bass, 400) * 0.16
    drums = drums * 0.22
    t = np.arange(n) / SR
    # arrangement: pad alone at first, bass and arpeggio join, drums carry the middle, then drop out for the ending
    intro = np.clip((t - 4.0) / 2.0, 0, 1)
    groove = np.clip((t - 10.0) / 2.0, 0, 1) * np.clip((total - 7.0 - t) / 1.5, 0, 1)
    mix = pad * (0.75 + 0.25 * intro) + (arp + bass) * intro + drums * groove
    fade = np.clip((total + 0.6 - t) / 3.5, 0, 1) * np.clip(t / 1.2, 0, 1)
    mix *= fade
    left = mix + 0.15 * np.roll(arp, int(0.012 * SR))
    right = mix - 0.05 * np.roll(arp, int(0.006 * SR))
    stereo = np.stack([left, right], axis=1)
    return stereo / np.max(np.abs(stereo)) * 0.89


def write_music(total: float) -> None:
    data = (music(total) * 32767).astype(np.int16)
    wav = ROOT / "music.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-b:a", "192k", str(ROOT / "music.mp3")], check=True)
    wav.unlink()


# ── sound effects ──────────────────────────────────────────────────────────────────────────────
def sfx(info: dict) -> None:
    """Synthesised effects on the film's own cues: a whoosh into each scene, a soft tick as each highlight appears, a low hit under the opening title."""
    n = int((info["total"] + 1.0) * SR)
    out = np.zeros(n)
    rng = np.random.default_rng(11)

    def put(at: float, x: np.ndarray) -> None:
        s = int(at * SR)
        if 0 <= s < n:
            out[s: s + len(x)] += x[: n - s]

    def whoosh() -> np.ndarray:
        ln = int(0.8 * SR)
        tt = np.arange(ln) / SR
        noise = rng.standard_normal(ln)
        # rising then falling band: two low-passes blended over time
        swept = lowpass(noise, 600) * (1 - tt / 0.8) + lowpass(noise, 3000) * (tt / 0.8)
        env = np.sin(np.pi * np.clip(tt / 0.8, 0, 1)) ** 2
        return highpass(swept, 120) * env * 0.5

    def tick() -> np.ndarray:
        ln = int(0.09 * SR)
        tt = np.arange(ln) / SR
        return (np.sin(2 * np.pi * 1760 * tt) + 0.4 * np.sin(2 * np.pi * 2640 * tt)) * np.exp(-tt * 55) * 0.22

    def hit() -> np.ndarray:
        ln = int(0.6 * SR)
        tt = np.arange(ln) / SR
        return np.sin(2 * np.pi * (52 * tt + 40 * (1 - np.exp(-tt * 18)) / 18)) * np.exp(-tt * 6) * 0.7

    for i, (scene, tm) in enumerate(zip(FILM["scenes"], info["scenes"])):
        if i:
            put(tm["start"] - 0.35, whoosh())
        if scene["kind"] == "hook":
            put(tm["start"] + 2.6, hit())
        for k, shot in enumerate(scene.get("shots", [])):
            a = scene["shots"][k - 1]["until"] if k else 0
            for h in shot["highlights"]:
                put(tm["start"] + (a + h[0] * (shot["until"] - a)) * tm["seconds"] + 0.05, tick())
    stereo = np.stack([out, out], axis=1)
    data = (stereo / max(1e-9, np.max(np.abs(stereo))) * 0.8 * 32767).astype(np.int16)
    wav = ROOT / "sfx.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-b:a", "192k", str(ROOT / "sfx.mp3")], check=True)
    wav.unlink()


def captions(info: dict) -> None:
    """WebVTT of the voice-over, sentence by sentence, timed the same way the film's burnt-in captions are (proportional to sentence length)."""
    def stamp(s: float) -> str:
        return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"

    cues = ["WEBVTT", ""]
    for scene, tm in zip(FILM["scenes"], info["scenes"]):
        parts = re.findall(r"[^.!?]+[.!?]+", scene["vo"]) or [scene["vo"]]
        total, at = sum(len(p) for p in parts), tm["vo_start"]
        for p in parts:
            length = len(p) / total * tm["vo_seconds"]
            cues += [f"{stamp(at)} --> {stamp(at + length)}", p.strip(), ""]
            at += length
    (ROOT / "captions.vtt").write_text("\n".join(cues), encoding="utf-8")


if __name__ == "__main__":
    if "--music" not in sys.argv:
        asyncio.run(voice())
        info = timing()
    else:
        info = json.loads((ROOT / "timing.json").read_text(encoding="utf-8"))
    captions(info)
    write_music(info["total"])
    sfx(info)
    print(json.dumps(info, indent=1))
