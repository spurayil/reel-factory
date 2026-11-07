"""IndicF5 voice clone worker (runs in .venv-f5).
Input: a jobs JSON file: {"ref_audio":..., "ref_text":..., "speed":0.92, "takes":3,
                          "jobs":[{"text":..., "out":"path_without_ext"}]}
Writes <out>_t1.wav ... <out>_tN.wav (24 kHz mono) for every job, skipping takes that already exist.
Usage: python tts_indicf5.py jobs.json
"""
import json, os, sys, time, inspect
import numpy as np
import soundfile as sf
import torch

REPO = "ai4bharat/IndicF5"


def main():
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    from transformers import AutoModel
    t0 = time.time()
    model = AutoModel.from_pretrained(REPO, trust_remote_code=True)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        model = model.to(dev)
    except Exception as e:
        print("could not move to", dev, e, flush=True)
    print(f"model loaded on {dev} in {time.time() - t0:.0f}s", flush=True)
    from f5_tts.infer.utils_infer import infer_process, preprocess_ref_audio_text
    model.ema_model.to(dev); model.vocoder.to(dev)
    ref_audio, ref_text = preprocess_ref_audio_text(cfg["ref_audio"], cfg["ref_text"], show_info=lambda *a, **k: None)
    takes = int(cfg.get("takes", 3))
    for j in cfg["jobs"]:
        for k in range(1, takes + 1):
            out = f"{j['out']}_t{k}.wav"
            if os.path.exists(out):
                continue
            torch.manual_seed(1000 * k + 7)
            np.random.seed(1000 * k + 7)
            t1 = time.time()
            # Call the F5 inference directly so speed / cfg / steps can be set
            # (IndicF5's forward() ignores them).
            audio, _, _ = infer_process(
                ref_audio, ref_text, j["text"], model.ema_model, model.vocoder,
                mel_spec_type="vocos", speed=float(j.get("speed", cfg.get("speed", 1.0))),
                cfg_strength=float(cfg.get("cfg_strength", 2.0)), nfe_step=int(cfg.get("nfe_step", 32)),
                device=dev, show_info=lambda *a, **k: None)
            audio = np.asarray(audio)
            if audio.dtype == np.int16:
                audio = audio.astype(np.float32) / 32768.0
            sf.write(out, audio.astype(np.float32), 24000)
            print(f"  {os.path.basename(out)}  {len(audio) / 24000:.1f}s audio in {time.time() - t1:.0f}s", flush=True)
    if dev == "cuda":
        print(f"peak GPU memory {torch.cuda.max_memory_allocated() / 1e9:.2f} GB", flush=True)


if __name__ == "__main__":
    main()
