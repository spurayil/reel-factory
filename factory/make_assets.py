"""Generates the factory's own music bed and sound effects (no licences needed: all synthesized here).
Run with .venv-asr python (has numpy):  python factory/make_assets.py"""
import os, wave
import numpy as np

SR = 48000
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "assets")
rng = np.random.default_rng(7)


def save(path, x):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.clip(x / (np.max(np.abs(x)) + 1e-9) * 0.89, -1, 1)
    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    os.replace(tmp, path)


def env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(t / max(a, 1e-4), 1) * np.exp(-t / d)


def lowpass(x, cutoff):
    # simple one-pole
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x); s = 0.0
    for i, v in enumerate(x):
        s = (1 - a) * v + a * s; y[i] = s
    return y


def sfx():
    n = int(0.55 * SR); t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    sweep = np.sin(2 * np.pi * (300 + 2600 * (t / t[-1]) ** 2) * t) * 0.15
    w = (lowpass(noise, 2500) + sweep) * np.sin(np.pi * t / t[-1]) ** 2
    save(os.path.join(OUT, "sfx", "whoosh.wav"), w)

    n = int(0.16 * SR); t = np.arange(n) / SR
    f = 900 * np.exp(-t * 18) + 380
    pop = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, 0.04)
    save(os.path.join(OUT, "sfx", "pop.wav"), pop)

    n = int(0.08 * SR); t = np.arange(n) / SR
    tap = (np.sin(2 * np.pi * 1800 * t) * 0.6 + rng.standard_normal(n) * 0.25) * env(n, 0.0005, 0.012)
    save(os.path.join(OUT, "sfx", "tap.wav"), tap * 0.6)


def music(bars=8, bpm=100):
    beat = 60 / bpm; bar = 4 * beat
    total = int(bars * bar * SR)
    mix = np.zeros(total)
    # A minor-ish uplifting loop: Am - F - C - G
    chords = [[57, 60, 64], [53, 57, 60], [48, 55, 64], [55, 59, 62]]
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    for b in range(bars):
        start = int(b * bar * SR); n = int(bar * SR); t = np.arange(n) / SR
        pad = np.zeros(n)
        for m in chords[b % 4]:
            for det in (-0.08, 0.08):
                pad += np.sin(2 * np.pi * hz(m) * (1 + det / 100) * t) + 0.3 * np.sin(2 * np.pi * 2 * hz(m) * t)
        pad *= np.minimum(t / 0.25, 1) * np.minimum((bar - t) / 0.2, 1) * 0.05
        bass = np.sin(2 * np.pi * hz(chords[b % 4][0] - 12) * t) * 0.18
        mix[start:start + n] += pad + bass * (0.6 + 0.4 * np.cos(2 * np.pi * t / beat) ** 2)
        for k in range(8):  # pluck arpeggio on eighths
            m = chords[b % 4][k % 3] + 12
            s = start + int(k * beat / 2 * SR); ln = int(0.3 * SR)
            tt = np.arange(ln) / SR
            mix[s:s + ln] += np.sin(2 * np.pi * hz(m) * tt) * env(ln, 0.003, 0.09) * 0.07
        for k in range(4):  # soft kick + hat
            s = start + int(k * beat * SR); ln = int(0.25 * SR); tt = np.arange(ln) / SR
            mix[s:s + ln] += np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * env(ln, 0.001, 0.12) * 0.5
            h = s + int(beat / 2 * SR); hl = int(0.05 * SR)
            mix[h:h + hl] += rng.standard_normal(hl) * env(hl, 0.0005, 0.012) * 0.06
    save(os.path.join(OUT, "music", "bed.wav"), mix)


if __name__ == "__main__":
    sfx(); music(); print("assets ready in", OUT)
