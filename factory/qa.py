"""Quality check after every render -> out/REPORT.md + out/contact_sheet.jpg. Returns True on PASS."""
import json, os, re, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASR_PY = os.path.join(ROOT, ".venv-asr", "Scripts", "python.exe")
if not os.path.exists(ASR_PY):
    ASR_PY = os.path.join(ROOT, ".venv-asr", "bin", "python")


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(path):
    r = sh(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    return json.loads(r.stdout)


def check(reel_dir, mp4, tl):
    out = os.path.join(reel_dir, "out")
    rows = []  # (name, ok, detail, hard)

    def add(name, ok, detail, hard=True):
        rows.append((name, ok, detail, hard))

    info = probe(mp4)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    add("Resolution", v["width"] == 1080 and v["height"] == 1920, f"{v['width']}x{v['height']}")
    num, den = map(int, v["r_frame_rate"].split("/"))
    add("Frame rate", abs(num / den - 30) < 0.01, f"{num / den:.2f} fps")
    add("Codec", v["codec_name"] == "h264" and v.get("pix_fmt") == "yuv420p", f"{v['codec_name']} {v.get('pix_fmt')}")
    lo, hi = tl["profile"].get("length_seconds", [30, 45])
    add("Duration", 15 <= dur <= 90, f"{dur:.1f}s (target {lo}-{hi}s)")
    if not (lo - 3 <= dur <= hi + 5):
        add("Duration vs target", False, f"{dur:.1f}s is outside {lo}-{hi}s", hard=False)

    if a:
        vd = float(v.get("duration", dur)); ad = float(a.get("duration", dur))
        add("Audio/video sync", abs(vd - ad) < 0.12, f"video {vd:.2f}s, audio {ad:.2f}s")
    else:
        add("Audio present", False, "no audio stream")

    r = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4, "-af", "ebur128=peak=true", "-f", "null", "-"])
    I = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    TP = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    if I:
        li = float(I[-1]); tp = float(TP[-1]) if TP else 0
        add("Loudness", abs(li + 14) <= 1.0, f"{li:.1f} LUFS (target -14)")
        add("True peak", tp <= -1.0, f"{tp:.1f} dBTP (target <= -1.5)")
    else:
        add("Loudness", False, "could not measure")

    r = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4, "-vf", "blackdetect=d=0.4:pix_th=0.06", "-an", "-f", "null", "-"])
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)
    add("No black frames", not blacks, "none" if not blacks else ", ".join(f"{s}-{e}s" for s, e in blacks))
    r = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4, "-vf", "freezedetect=n=0.0008:d=2.5", "-an", "-f", "null", "-"])
    fr = re.findall(r"freeze_start: ([\d.]+)", r.stderr)
    add("No frozen video", not fr, "none" if not fr else "freeze at " + ", ".join(f"{float(x):.1f}s" for x in fr))

    words = [w for b in tl["beats"] for w in b["words"]]
    late = [w for w in words if w["end"] > dur + 0.05]
    add("Caption coverage", bool(words) and not late,
        f"{len(words)} words timed, {len(late)} past the end")
    gaps = []
    for b in tl["beats"]:
        if not b["words"]:
            gaps.append(b["id"])
    add("Every beat has narration", not gaps, "ok" if not gaps else "silent: " + ", ".join(gaps), hard=False)

    from make_reel import spoken_form  # compare against what the voice actually says
    script = " ".join(spoken_form(b["say"], {}) for b in tl["beats"])
    asr_detail, asr_ok = "skipped (ASR not installed)", True
    if os.path.exists(ASR_PY):
        r = sh([ASR_PY, os.path.join(ROOT, "factory", "asr_check.py"), "--sentences",
                os.path.join(reel_dir, "timeline.json"), mp4, out])
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
            asr_ok = res["cer"] <= 0.15 and res["worst"] <= 0.35
            asr_detail = (f"sentence-by-sentence Malayalam CER {res['cer']:.0%} (pass <= 15%), worst sentence "
                          f"{res['worst']:.0%} (pass <= 35%); details in asr_transcript.txt")
        except Exception:
            asr_ok, asr_detail = False, "ASR failed: " + (r.stderr or r.stdout)[-300:]
    add("Speech says the script (ASR)", asr_ok, asr_detail)

    sheet = os.path.join(out, "contact_sheet.jpg")
    n = 12
    sh(["ffmpeg", "-y", "-v", "error", "-i", mp4, "-vf",
        f"fps={n / max(dur, 1):.5f},scale=270:480,tile=6x2:padding=8:color=0x0B0F1A", "-frames:v", "1", "-update", "1", sheet])

    passed = all(ok for _, ok, _, hard in rows if hard)
    lines = [f"# Quality report: {'PASS' if passed else 'FAIL'}", "", f"File: `{os.path.basename(mp4)}`", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    for name, ok, detail, hard in rows:
        mark = "PASS" if ok else ("FAIL" if hard else "WARN")
        lines.append(f"| {name} | {mark} | {detail.replace('|', '/')} |")
    srcs = tl.get("sources") or []
    lines += ["", "Contact sheet: `contact_sheet.jpg`"]
    with open(os.path.join(out, "REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for name, ok, detail, hard in rows:
        print(f"      {'PASS' if ok else ('FAIL' if hard else 'WARN'):4}  {name}: {detail}")
    return passed
