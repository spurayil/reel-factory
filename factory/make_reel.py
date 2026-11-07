"""Reel Factory: reel.json -> voice -> timeline -> frames -> mixed MP4 -> quality check.

Usage:  .venv-tts/Scripts/python factory/make_reel.py reels/<slug>            (full build)
        .venv-tts/Scripts/python factory/make_reel.py reels/<slug> --stills   (preview stills only)
        .venv-tts/Scripts/python factory/make_reel.py reels/<slug> --voice-only
"""
import asyncio, json, os, re, shutil, subprocess, sys, wave, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTORY = os.path.join(ROOT, "factory")
SR = 48000
FPS = 30


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(map(str, cmd))[:300]}\n{r.stderr[-2000:]}")
    return r


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def split_sentences(text):
    parts = re.split(r"(?<=[.?!।])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------- voice
async def tts_edge(text, voice, rate, mp3_path):
    import edge_tts
    words = []
    c = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(mp3_path, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"text": ch["text"], "start": ch["offset"] / 1e7,
                              "end": (ch["offset"] + ch["duration"]) / 1e7})
    return words


def to_wav(src, dst):
    run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", dst])


def wav_frames(path):
    with wave.open(path, "rb") as w:
        return w.readframes(w.getnframes()), w.getnframes() / SR


def spoken_form(text, reel):
    """Screen text -> what the Malayalam voice clone should say (English words in Malayalam script)."""
    table = dict(load(os.path.join(FACTORY, "pronounce_ml.json")))
    table.pop("_note", None)
    table.update(reel.get("pronounce") or {})
    for k in sorted(table, key=len, reverse=True):
        text = re.sub(r"(?<![A-Za-z])" + re.escape(k) + r"(?![A-Za-z])", table[k], text, flags=re.I)
    return text.replace("-", "")


def clone_sentences(vdir, items, profile):
    """items: list of (base_path, spoken_text). Generates takes with IndicF5, keeps the best by ASR."""
    v = profile["voice"]
    todo = [(b, s) for b, s in items
            if not (os.path.exists(b + ".wav") and os.path.exists(b + ".json") and load(b + ".json").get("spoken") == s)]
    if not todo:
        return
    for b, _ in todo:  # text changed -> old takes are stale
        for f in os.listdir(vdir):
            if f.startswith(os.path.basename(b) + "_t"):
                os.remove(os.path.join(vdir, f))
    jobs = {"ref_audio": os.path.join(ROOT, v.get("ref_audio", "voice/ref.wav")),
            "ref_text": open(os.path.join(ROOT, v.get("ref_text", "voice/ref.txt")), encoding="utf-8").read().strip(),
            "speed": v.get("speed", 1.12), "cfg_strength": v.get("cfg_strength", 2.6), "nfe_step": v.get("nfe_step", 32),
            "takes": v.get("takes", 2), "jobs": [{"text": s, "out": b} for b, s in todo]}
    jpath = os.path.join(vdir, "jobs.json")
    save(jpath, jobs)
    py = lambda venv: os.path.join(ROOT, venv, "Scripts", "python.exe")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    print(f"      cloning {len(todo)} sentences x {jobs['takes']} takes (about {len(todo) * jobs['takes'] * 50 // 60} min)")
    r = subprocess.run([py(".venv-f5"), os.path.join(FACTORY, "tts_indicf5.py"), jpath], env=env, text=True,
                       encoding="utf-8", errors="replace", capture_output=True)
    for line in r.stdout.splitlines():
        if "_t" in line or "loaded" in line or "peak" in line:
            print("     ", line.strip())
    if r.returncode != 0:
        raise RuntimeError("voice clone failed:\n" + r.stderr[-1500:])
    print("      choosing the clearest take of each sentence (speech recognition)")
    spath = os.path.join(vdir, "scores.json")
    r = subprocess.run([py(".venv-asr"), os.path.join(FACTORY, "asr_check.py"), "--score", jpath, spath], env=env,
                       text=True, encoding="utf-8", errors="replace", capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("take scoring failed:\n" + r.stderr[-1500:])
    for res in load(spath):
        best = res["best"]
        # trim leading/trailing silence, 48 kHz mono
        run(["ffmpeg", "-y", "-v", "error", "-i", best["path"], "-af",
             "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
             "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse",
             "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", res["out"] + ".wav"])
        save(res["out"] + ".json", {"spoken": res["text"], "words": [], "cer": best["cer"], "heard": best["heard"],
                                    "take": os.path.basename(best["path"])})
        flag = "  <-- check" if best["cer"] > 0.15 else ""
        print(f"      {os.path.basename(res['out'])}: {best['cer']:.0%} error{flag}")


def make_voice(reel_dir, reel, profile):
    """One clip per sentence, then assemble with designed pauses. Returns timeline beats."""
    vdir = os.path.join(reel_dir, "audio", "sentences")
    os.makedirs(vdir, exist_ok=True)
    v = profile["voice"]
    clone = v.get("engine") == "indicf5"
    if clone:
        items = []
        for bi, beat in enumerate(reel["beats"]):
            for si, s in enumerate(split_sentences(beat["say"])):
                items.append((os.path.join(vdir, f"{bi:02d}_{si:02d}"), spoken_form(s, reel)))
        clone_sentences(vdir, items, profile)
    lead = 0.30
    t = lead
    pcm = bytearray(b"\x00\x00" * int(lead * SR))
    beats_out = []
    for bi, beat in enumerate(reel["beats"]):
        sents = split_sentences(beat["say"])
        b = dict(beat)
        b["start"] = 0.0 if bi == 0 else round(t - 0.12, 3)
        b["words"] = []
        b["sentences"] = []
        for si, s in enumerate(sents):
            spoken = s
            for k, rep in (reel.get("pronounce") or {}).items():
                spoken = spoken.replace(k, rep)
            base = os.path.join(vdir, f"{bi:02d}_{si:02d}")
            cache = base + ".json"
            if clone:
                words = []
            elif os.path.exists(cache) and load(cache).get("spoken") == spoken and os.path.exists(base + ".wav"):
                words = load(cache)["words"]
            else:
                words = asyncio.run(tts_edge(spoken, v["name"], v.get("rate", "+0%"), base + ".mp3"))
                to_wav(base + ".mp3", base + ".wav")
                save(cache, {"spoken": spoken, "words": words})
            data, dur = wav_frames(base + ".wav")
            pcm += data
            shown = s.split()
            # Display words: use the written text, mapped onto spoken timings
            if clone:
                ws = spread_by_speech(shown, t, t + dur, reel)
            else:
                ws = [{"text": w["text"], "start": round(t + w["start"], 3), "end": round(t + w["end"], 3)} for w in words]
                ws = map_display_words(shown, ws)
            b["words"] += ws
            b["sentences"].append({"text": s, "start": round(t, 3), "end": round(t + dur, 3)})
            t += dur
            last_sent = si == len(sents) - 1
            pause = (beat.get("pause_after_ms", 500) if last_sent else beat.get("pause_between_ms", 400)) / 1000
            pcm += b"\x00\x00" * int(pause * SR)
            t += pause
        beats_out.append(b)
    tail = 0.9
    pcm += b"\x00\x00" * int(tail * SR)
    t += tail
    for i, b in enumerate(beats_out):
        b["end"] = beats_out[i + 1]["start"] if i + 1 < len(beats_out) else round(t, 3)
    voice_path = os.path.join(reel_dir, "audio", "voice.wav")
    with wave.open(voice_path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(pcm))
    return beats_out, round(len(pcm) / 2 / SR, 3), voice_path


def norm(s):
    return re.sub(r"[^\w]", "", s.lower())


def spread_by_speech(shown, t0, t1, reel):
    """Clone gives no word timings: share the clip time by each word's spoken length (+ comma pauses)."""
    weights = []
    for w in shown:
        n = len(re.sub(r"[^ഀ-ൿ]", "", spoken_form(w, reel))) or len(w)
        weights.append(n + 2 + (4 if re.search(r"[,:;]$", w) else 0))
    total = sum(weights)
    out, acc = [], 0
    for w, k in zip(shown, weights):
        s = t0 + (t1 - t0) * acc / total
        acc += k
        out.append({"text": w, "start": round(s, 3), "end": round(t0 + (t1 - t0) * acc / total, 3)})
    return out


def map_display_words(shown, spoken):
    """Edge returns its own tokens; keep the written words but give each one a time.
    If counts match, zip. Otherwise spread written words across the spoken span by length."""
    if len(shown) == len(spoken):
        return [{"text": a, "start": b["start"], "end": b["end"]} for a, b in zip(shown, spoken)]
    if not spoken:
        return []
    t0, t1 = spoken[0]["start"], spoken[-1]["end"]
    total = sum(len(x) + 2 for x in shown)
    out, acc = [], 0
    for x in shown:
        s = t0 + (t1 - t0) * acc / total
        acc += len(x) + 2
        e = t0 + (t1 - t0) * acc / total
        out.append({"text": x, "start": round(s, 3), "end": round(e, 3)})
    return out


def resolve_anchor(beat, anchor, default):
    """Anchor = a word (or part of one) in this beat's narration -> its start time."""
    if anchor is None:
        return default
    if isinstance(anchor, (int, float)):
        return beat["start"] + float(anchor)
    a = norm(anchor)
    for w in beat["words"]:
        if a and a in norm(w["text"]):
            return w["start"]
    print(f"  ! anchor '{anchor}' not found in beat {beat['id']}, using default")
    return default


def build_timeline(reel_dir, reel, profile, beats, duration):
    for b in beats:
        base = b["start"] + 0.35
        for i, item in enumerate(b.get("screen", [])):
            item["t"] = round(resolve_anchor(b, item.get("at"), base + 0.45 * i) + item.get("delay", 0), 3)
            if "tap_at" in item:
                item["tap_t"] = round(resolve_anchor(b, item["tap_at"], item["t"] + 0.6), 3)
        if b["scene"] == "cta":
            b["follow_t"] = round(resolve_anchor(b, b.get("follow_at"), b["start"] + 0.9), 3)
            b["keyword_t"] = round(resolve_anchor(b, b.get("keyword_at"), b["start"] + 1.4), 3)
    tl = {"fps": FPS, "width": 1080, "height": 1920, "duration": duration,
          "title": reel.get("title", ""), "profile": profile, "beats": beats}
    save(os.path.join(reel_dir, "timeline.json"), tl)
    return tl


# ---------------------------------------------------------------- render + mix
def render(reel_dir, out_mp4, stills=None):
    cmd = ["node", os.path.join(FACTORY, "render", "render.js"), os.path.join(reel_dir, "timeline.json"), out_mp4]
    if stills:
        cmd += ["--stills", ",".join(f"{s:.2f}" for s in stills)]
    r = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("renderer failed")


def mix(reel_dir, video, voice, out_mp4, profile):
    """Voice (+ optional music bed and SFX in Stage B) -> two-pass loudnorm to -14 LUFS, TP -1.5."""
    audio_dir = os.path.join(reel_dir, "audio")
    premix = os.path.join(audio_dir, "premix.wav")
    sys.path.insert(0, FACTORY)
    import audio_mix
    audio_mix.build_premix(reel_dir, voice, premix)
    r = run(["ffmpeg", "-hide_banner", "-i", premix, "-af",
             "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    meas = json.loads(m.group(0))
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
          f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true")
    final_wav = os.path.join(audio_dir, "final.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", premix, "-af", ln + ",alimiter=limit=0.82:level=false", "-ar", str(SR), final_wav])
    run(["ffmpeg", "-y", "-v", "error", "-i", video, "-i", final_wav, "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-shortest",
         "-movflags", "+faststart", out_mp4])


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)
    reel_dir = os.path.abspath(args[0])
    reel = load(os.path.join(reel_dir, "reel.json"))
    profile = load(os.path.join(ROOT, "profile.json"))
    out_dir = os.path.join(reel_dir, "out")
    os.makedirs(out_dir, exist_ok=True)

    print("[1/5] voice: one clip per sentence")
    beats, duration, voice = make_voice(reel_dir, reel, profile)
    tl = build_timeline(reel_dir, reel, profile, beats, duration)
    print(f"      duration {duration:.1f}s, {len(beats)} beats")
    if "--voice-only" in args:
        return

    if "--stills" in args:
        ts = []
        for b in beats:
            ts.append(min(b["end"] - 0.2, b["start"] + (b["end"] - b["start"]) * 0.75))
        print("[2/5] preview stills")
        render(reel_dir, os.path.join(out_dir, "still.jpg"), stills=ts)
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    video = os.path.join(out_dir, "video_only.mp4")
    print("[2/5] rendering frames (headless Chrome -> H.264)")
    render(reel_dir, video)
    final = os.path.join(out_dir, f"{reel.get('slug', os.path.basename(reel_dir))}_{stamp}.mp4")
    print("[3/5] mixing audio to -14 LUFS")
    mix(reel_dir, video, voice, final, profile)
    print("[4/5] quality check")
    import qa
    ok = qa.check(reel_dir, final, tl)
    if ok:
        dest = os.path.join(ROOT, "finished", os.path.basename(final))
        shutil.copy2(final, dest)
        cap = os.path.join(reel_dir, "caption.txt")
        if os.path.exists(cap):
            shutil.copy2(cap, dest.replace(".mp4", "_caption.txt"))
        print(f"[5/5] PASS -> {dest}")
    else:
        print("[5/5] FAIL -> see REPORT.md in", out_dir)
        sys.exit(2)


if __name__ == "__main__":
    main()
