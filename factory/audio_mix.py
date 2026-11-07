"""Builds the pre-loudness mix. Stage A: voice only, gently compressed.
Stage B adds the music bed (ducked under the voice) and SFX from timeline beats."""
import json, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "factory", "assets")


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])


def build_premix(reel_dir, voice, out):
    tl = json.load(open(os.path.join(reel_dir, "timeline.json"), encoding="utf-8"))
    voice_fx = tl["profile"]["voice"].get("fx") or "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=2"
    music = os.path.join(ASSETS, "music", "bed.wav")
    sfx = []
    for b in tl["beats"]:
        name = b.get("sfx")
        if name:
            p = os.path.join(ASSETS, "sfx", f"{name}.wav")
            if os.path.exists(p):
                sfx.append((p, max(0.0, b["start"])))
        for item in b.get("screen", []):
            if "tap_t" in item:
                p = os.path.join(ASSETS, "sfx", "tap.wav")
                if os.path.exists(p):
                    sfx.append((p, item["tap_t"]))

    if not os.path.exists(music) and not sfx:
        _run(["ffmpeg", "-y", "-v", "error", "-i", voice, "-af", voice_fx, "-ar", "48000", out])
        return

    inputs = ["-i", voice]
    filt = [f"[0:a]{voice_fx},asplit=2[v][vkey]"]
    mix_labels = ["[v]"]
    idx = 1
    if os.path.exists(music):
        inputs += ["-stream_loop", "-1", "-i", music]
        dur = tl["duration"]
        filt.append(f"[{idx}:a]atrim=0:{dur},volume=0.22,afade=t=in:d=0.6,afade=t=out:st={max(0, dur - 1.2)}:d=1.2[m]")
        filt.append("[m][vkey]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[mduck]")
        mix_labels.append("[mduck]")
        idx += 1
    else:
        filt.append("[vkey]anullsink")
    for p, t in sfx:
        inputs += ["-i", p]
        ms = int(t * 1000)
        filt.append(f"[{idx}:a]volume=0.5,adelay={ms}|{ms}[s{idx}]")
        mix_labels.append(f"[s{idx}]")
        idx += 1
    filt.append("".join(mix_labels) + f"amix=inputs={len(mix_labels)}:normalize=0:duration=first[out]")
    _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filt),
          "-map", "[out]", "-ac", "1", "-ar", "48000", out])
