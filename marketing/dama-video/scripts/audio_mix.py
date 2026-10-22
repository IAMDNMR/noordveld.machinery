"""Synthesise the music bed + sound effects, lay in the voiceover with ducking, write audio/mix.wav.

Everything is generated here (no third-party music), driven by src/timeline.json.
"""
import json
import os
import subprocess

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = json.load(open(os.path.join(ROOT, "src", "timeline.json")))
SR = 48000
DUR = TL["duration"]
N = int(SR * DUR)
rng = np.random.default_rng(7)


def note(n):  # MIDI -> Hz
    return 440.0 * 2 ** ((n - 69) / 12)


def lp(x, hz, order=2):
    return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), x)


def hp(x, hz, order=2):
    return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi):
    return sosfilt(butter(2, [lo, hi], "band", fs=SR, output="sos"), x)


def env_adsr(n, a, r):
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    e[:na] = np.linspace(0, 1, na) if na else 1
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def add(buf, sig, t):
    i = int(t * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


def tt(d):
    return np.arange(int(d * SR)) / SR


def saw(f, d, harm=10):
    t = tt(d)
    return sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, harm + 1) if f * k < 12000)


def pad(notes, d, bright=1800):
    s = sum(saw(note(n) * (1 + dt), d, 8) for n in notes for dt in (-0.003, 0.003))
    return lp(s, bright) * env_adsr(len(s), 0.9, 1.0) / (len(notes) * 4)


def pluck(n, d=0.9, bright=4000):
    t = tt(d)
    f = note(n)
    s = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t))
    return lp(s * np.exp(-t * 6), bright) * 0.35


def kick(d=0.45):
    t = tt(d)
    f = 45 + 90 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * 0.9


def hat(d=0.08):
    t = tt(d)
    return hp(rng.standard_normal(len(t)), 7000) * np.exp(-t * 60) * 0.12


def reverb(x, secs=2.2, wet=0.28):
    ir = rng.standard_normal(int(secs * SR)) * np.exp(-np.arange(int(secs * SR)) / SR * 3.2)
    ir = lp(ir, 5000)
    y = fftconvolve(x, ir)[: len(x)]
    y *= np.max(np.abs(x)) / (np.max(np.abs(y)) + 1e-9)
    return x * (1 - wet) + y * wet


# ---------------- music ----------------
mus = np.zeros(N)
S = TL["scenes"]

# opening: tension. low drone + muted minor pad + clock ticks
d0 = S["opening"][1]
drone = saw(note(33), d0, 6)
drone = lp(drone, 220) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * tt(d0))) * 0.22
add(mus, drone * env_adsr(len(drone), 0.4, 0.8), 0)
add(mus, pad([57, 60, 64, 71], d0, 900) * 0.8, 0)
for k in np.arange(0.3, d0 - 0.4, 0.6):
    add(mus, hp(rng.standard_normal(int(0.03 * SR)), 2500) * np.exp(-tt(0.03) * 120) * 0.05, k)

# yoa: hope. F maj7 -> C -> G with arpeggio
s, e = S["yoa"]
chords = [([53, 57, 60, 64], [65, 69, 72, 76]), ([48, 55, 60, 64], [64, 67, 72, 76]), ([55, 59, 62, 67], [67, 71, 74, 79])]
seg = (e - s) / len(chords)
for i, (ch, arp) in enumerate(chords):
    add(mus, pad(ch, seg + 0.8, 2200), s + i * seg)
    for j, b in enumerate(np.arange(0, seg, 0.3)):
        add(mus, pluck(arp[j % 4]) * 0.8, s + i * seg + b)

# turn: drop + riser
s, e = S["turn"]
add(mus, kick(1.2) * 1.2, s + 0.25)
rd = e - s - 0.2
ris = bp(rng.standard_normal(int(rd * SR)), 300, 6000) * np.linspace(0, 1, int(rd * SR)) ** 2 * 0.12
add(mus, ris, s + 0.2)
add(mus, pad([45, 52, 57], e - s, 600) * 0.7, s)

# gecko: drive. Am F C G, kick + hats + bright arp
s, e = S["gecko"]
prog = [([57, 60, 64], 45), ([53, 57, 60], 41), ([48, 55, 64], 48), ([55, 59, 62], 43)]
beat = 0.6
bar = beat * 4
t0 = s
i = 0
while t0 < e - 0.05:
    ch, bass = prog[i % 4]
    L = min(bar, e - t0)
    add(mus, pad(ch, L + 0.6, 2600) * 0.9, t0)
    add(mus, lp(saw(note(bass), L, 4), 300) * env_adsr(int(L * SR), 0.02, 0.2) * 0.16, t0)
    for b in range(4):
        tb = t0 + b * beat
        if tb < e - 0.1:
            add(mus, kick() * 0.55, tb)
            add(mus, hat(), tb + beat / 2)
        for h in range(2):
            th = tb + h * beat / 2
            if th < e - 0.1:
                add(mus, pluck(ch[(b * 2 + h) % 3] + 12, 0.5, 5000) * 0.5, th)
    t0 += bar
    i += 1

# invite: warm resolution C Am F, sparse plucks, ring out
s, e = S["invite"]
prog = [[48, 55, 64, 67], [45, 52, 60, 64], [41, 53, 57, 60]]
seg = (e - s) / 3
for i, ch in enumerate(prog):
    L = seg + (1.6 if i == 2 else 0.8)
    add(mus, pad(ch, L, 2400), s + i * seg)
    for j, b in enumerate(np.arange(0, seg, 0.6)):
        add(mus, pluck(ch[(j + 1) % 4] + 12, 1.2, 3500) * 0.55, s + i * seg + b)

mus = reverb(mus, 2.4, 0.3)
fade = np.ones(N)
fade[-int(0.8 * SR):] = np.linspace(1, 0, int(0.8 * SR))
mus *= fade

# ---------------- sfx ----------------
fx = np.zeros(N)


def alarm():
    t = tt(0.32)
    f = np.where(t < 0.16, 880, 660)
    s = np.sign(np.sin(2 * np.pi * f * t)) * 0.5 + np.sin(2 * np.pi * f * t) * 0.5
    return lp(s, 2500) * env_adsr(len(t), 0.01, 0.06) * 0.16


def stop():
    t = tt(0.9)
    f = 180 * np.exp(-t * 3) + 30
    s = lp(saw(1, 0.9, 1) * 0 + np.sin(2 * np.pi * np.cumsum(f) / SR), 400) * np.exp(-t * 3) * 0.5
    return s + lp(rng.standard_normal(len(t)), 300) * np.exp(-t * 10) * 0.4


def stamp():
    t = tt(0.5)
    return (np.sin(2 * np.pi * 70 * t) * np.exp(-t * 14) * 0.9 + lp(rng.standard_normal(len(t)), 1200) * np.exp(-t * 30) * 0.6)


def nomatch():
    t = tt(0.26)
    f = np.where(t < 0.11, 330, 247)
    s = sum(np.sin(2 * np.pi * f * k * t) / k for k in (1, 2, 3))
    return lp(s, 1800) * env_adsr(len(t), 0.005, 0.08) * 0.14


def whoosh():
    d = 0.6
    n = int(d * SR)
    x = rng.standard_normal(n)
    e = np.sin(np.linspace(0, np.pi, n)) ** 2
    lo = bp(x, 400, 1500)
    hi = bp(x, 1500, 6000)
    m = np.linspace(0, 1, n)
    return (lo * (1 - m) + hi * m) * e * 0.22


def typing(d):
    out = np.zeros(int(d * SR))
    t = 0.0
    while t < d - 0.03:
        c = hp(rng.standard_normal(int(0.02 * SR)), 3000) * np.exp(-tt(0.02) * 300) * 0.12
        add(out, c, t)
        t += rng.uniform(0.055, 0.11)
    return out


def pop():
    t = tt(0.12)
    f = 600 + 900 * (t / 0.12)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35) * 0.2


def shatter():
    out = np.zeros(int(1.2 * SR))
    for _ in range(70):
        tp = rng.uniform(0, 0.5) ** 1.6
        f = rng.uniform(2500, 7500)
        t = tt(0.3)
        add(out, np.sin(2 * np.pi * f * t) * np.exp(-t * rng.uniform(15, 40)) * 0.03, tp)
    add(out, hp(rng.standard_normal(int(0.4 * SR)), 2000) * np.exp(-tt(0.4) * 12) * 0.25, 0)
    return out


def count(d):
    out = np.zeros(int((d + 1.2) * SR))
    steps = 14
    for k in range(steps):
        t = tt(0.06)
        f = 700 + k * 45
        add(out, np.sin(2 * np.pi * f * t) * np.exp(-t * 60) * 0.1, d * (k / steps) ** 0.8)
    t = tt(1.1)
    ding = sum(np.sin(2 * np.pi * note(n) * t) for n in (84, 88, 91)) / 3
    add(out, ding * np.exp(-t * 4) * 0.22, d)
    return out


F = TL["sfx"]
for t in F["alarm"]:
    add(fx, alarm(), t)
for t in F["stop"]:
    add(fx, stop(), t)
for t in F["stamp"]:
    add(fx, stamp(), t)
for t in F["nomatch"]:
    add(fx, nomatch(), t)
for t in F["whoosh"]:
    add(fx, whoosh(), t - 0.3)
add(fx, typing(F["type"][1] - F["type"][0]), F["type"][0])
for t in F["pop"]:
    add(fx, pop(), t)
for t in F["shatter"]:
    add(fx, shatter(), t)
add(fx, count(F["count"][1] - F["count"][0]), F["count"][0])
fx = reverb(fx, 1.2, 0.18)

# ---------------- voice ----------------
vo = np.zeros(N)
for k, t in TL["vo"].items():
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(ROOT, "audio", f"{k}.mp3"),
                          "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    add(vo, np.frombuffer(raw, np.float32).astype(np.float64), t)
vo = hp(vo, 80)
vo /= np.max(np.abs(vo)) + 1e-9

# duck music under the voice
env = lp(np.abs(vo), 6, 1)
env = np.clip(env / (np.percentile(env[env > 1e-4], 90) + 1e-9), 0, 1)
duck = 1 - 0.55 * env

mus /= np.max(np.abs(mus)) + 1e-9
fx /= np.max(np.abs(fx)) + 1e-9
mix_m = mus * 0.30 * duck + fx * 0.32 + vo * 0.9

# simple stereo: music/fx slightly widened, voice centred
d = int(0.012 * SR)
wide = mus * 0.30 * duck + fx * 0.32
L = mix_m
R = vo * 0.9 + np.concatenate([np.zeros(d), wide[:-d]])
st = np.stack([L, R], 1)
st /= np.max(np.abs(st)) / 0.89

import wave

with wave.open(os.path.join(ROOT, "audio", "mix.wav"), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((st * 32767).astype(np.int16).tobytes())
print("mix.wav", DUR, "s")
