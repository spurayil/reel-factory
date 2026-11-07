"""Transcribe the reel narration with a Malayalam Whisper model and compare it with the script.
Prints one JSON line: {"cer": .., "threshold": .., "text": ..}
English words are spoken but Whisper writes them in Malayalam script, so the score compares
Malayalam characters only, after removing Latin text from both sides."""
import json, os, re, sys, subprocess, tempfile

MODELS = ["kurianbenoy/vegam-whisper-medium-ml", "small"]
THRESHOLD = 0.30


def ml_only(s):
    s = re.sub(r"[A-Za-z0-9]+", " ", s)
    s = re.sub(r"[^ഀ-ൿ\s]", " ", s)
    return re.sub(r"\s+", "", s)


def load_16k(path):
    """Decode with ffmpeg to 16 kHz mono float32 (avoids PyAV version issues)."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def main():
    if sys.argv[1] == "--sentences":
        # Check the FINAL mixed audio sentence by sentence (long-file Whisper decoding skips chunks).
        from faster_whisper import WhisperModel
        import jiwer
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from make_reel import spoken_form
        tl = json.load(open(sys.argv[2], encoding="utf-8"))
        mp4, out = sys.argv[3], sys.argv[4]
        model = WhisperModel(MODELS[0], device="cpu", compute_type="int8")
        audio = load_16k(mp4)
        rows, tot_err, tot_len = [], 0.0, 0
        for b in tl["beats"]:
            for s in b.get("sentences", []):
                a = audio[max(0, int((s["start"] - 0.1) * 16000)): int((s["end"] + 0.15) * 16000)]
                segs, _ = model.transcribe(a, language="ml", beam_size=5)
                heard = " ".join(x.text.strip() for x in segs)
                ref = ml_only(spoken_form(s["text"], {}))
                cer = jiwer.cer(ref, ml_only(heard)) if ref else 0.0
                tot_err += cer * len(ref); tot_len += len(ref)
                rows.append({"text": s["text"], "heard": heard, "cer": round(cer, 3)})
        cer = tot_err / max(tot_len, 1)
        worst = max(rows, key=lambda r: r["cer"]) if rows else {"cer": 0}
        with open(os.path.join(out, "asr_transcript.txt"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(f"[{r['cer']:.0%}] SCRIPT: {r['text']}\n       HEARD:  {r['heard']}\n")
            f.write(f"\nOverall CER (Malayalam chars): {cer:.3f}\n")
        print(json.dumps({"cer": cer, "threshold": THRESHOLD, "worst": worst["cer"],
                          "text": " / ".join(r["heard"] for r in rows)}, ensure_ascii=False))
        return
    if sys.argv[1] == "--score":
        # Score every take of every job against its spoken text; pick the lowest error.
        from faster_whisper import WhisperModel
        import jiwer, glob
        cfg = json.load(open(sys.argv[2], encoding="utf-8"))
        model = WhisperModel(MODELS[0], device="cpu", compute_type="int8")
        result = []
        for j in cfg["jobs"]:
            ref = ml_only(j["text"])
            scored = []
            for path in sorted(glob.glob(j["out"] + "_t*.wav")):
                segs, _ = model.transcribe(load_16k(path), language="ml", beam_size=5)
                heard = " ".join(s.text.strip() for s in segs)
                cer = jiwer.cer(ref, ml_only(heard)) if ref else 0.0
                scored.append({"path": path, "cer": round(cer, 3), "heard": heard})
            scored.sort(key=lambda x: x["cer"])
            result.append({"out": j["out"], "text": j["text"], "best": scored[0] if scored else None, "takes": scored})
            print(f"  {os.path.basename(j['out'])}: best CER {scored[0]['cer']:.0%}" if scored else "  none", file=sys.stderr, flush=True)
        json.dump(result, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return
    if sys.argv[1] == "--transcribe":
        from faster_whisper import WhisperModel
        model = WhisperModel(MODELS[0], device="cpu", compute_type="int8")
        segs, _ = model.transcribe(load_16k(sys.argv[2]), language="ml", beam_size=5)
        print(" ".join(s.text.strip() for s in segs))
        return
    mp4, script, out = sys.argv[1], sys.argv[2], sys.argv[3]
    from faster_whisper import WhisperModel
    import jiwer
    wav = os.path.join(tempfile.gettempdir(), "reel_asr.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", mp4, "-ac", "1", "-ar", "16000", wav], check=True)
    last = None
    for m in MODELS:
        try:
            model = WhisperModel(m, device="cpu", compute_type="int8")
            break
        except Exception as e:  # model not downloadable -> try next
            last = e
    else:
        raise last
    segs, _ = model.transcribe(load_16k(wav), language="ml", beam_size=5, vad_filter=True)
    text = " ".join(s.text.strip() for s in segs)
    ref, hyp = ml_only(script), ml_only(text)
    cer = jiwer.cer(ref, hyp) if ref else 0.0
    with open(os.path.join(out, "asr_transcript.txt"), "w", encoding="utf-8") as f:
        f.write(f"MODEL: {m}\nSCRIPT:\n{script}\n\nHEARD:\n{text}\n\nCER (Malayalam chars): {cer:.3f}\n")
    print(json.dumps({"cer": cer, "threshold": THRESHOLD, "text": text, "model": m}, ensure_ascii=False))


if __name__ == "__main__":
    main()
