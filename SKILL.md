---
name: reel-factory
description: Turn one topic into a finished, quality-checked 1080x1920 Instagram Reel - script in natural Malayalam (or another Indian language), voice, kinetic-text hook, phone-mockup steps, word-by-word captions, music, SFX and an automatic QA report. Use when the user types /reel-factory <topic>, asks for a new reel, says "reel ഉണ്ടാക്കൂ", or wants to change a reel the factory made. On first use it runs setup.
---

# Reel Factory

FACTORY = the folder this SKILL.md is in. Work with absolute paths. Talk to the user in their language; English tool names stay English. Don't show code or errors unless asked.

## 0. First run: setup (only if `FACTORY/profile.json` does not exist)
Needs: Windows/macOS/Linux, Python 3.10-3.12, Node.js 18+, FFmpeg on PATH, Google Chrome. Check each; tell the user exactly what to install if one is missing. Check free disk (need ~3 GB for basic, ~12 GB with voice clone). Never use pip cache on small disks: always `--no-cache-dir`.

1. Interview the user (one question at a time, offer choices): name and Instagram handle; niche and audience; narration language; voice (A: free Microsoft neural voice, B: clone of their own voice - needs an NVIDIA GPU with 2 GB+ and a Hugging Face login they do themselves); colours (accent, background); reel length (30-45 s recommended). Save to `FACTORY/profile.json` using `profile.example.json` as the template.
2. Environments (inside FACTORY):
   - `python -m venv .venv-tts` then `.venv-tts` pip install -r `requirements-tts.txt`
   - `python -m venv .venv-asr` then pip install -r `requirements-asr.txt` (speech check; downloads a Malayalam Whisper model on first run)
   - Voice clone only: `python -m venv .venv-f5`, install torch with CUDA from pytorch.org first (match their GPU driver), then pip install -r `requirements-f5.txt`. The user must accept the licence on https://huggingface.co/ai4bharat/IndicF5 and log in with `hf auth login` themselves (never ask for or paste their token).
   - `cd factory/render && npm install`
   - `.venv-asr` python `factory/make_assets.py` (makes music bed and SFX locally, no licence issues)
3. Voice clone only: ask for a 10-15 s clip of the user speaking energetically (ending on a neutral word). Convert to `voice/ref.wav` (mono 24 kHz, 7-12 s), transcribe with `.venv-asr` python `factory/asr_check.py --transcribe voice/ref.wav`, show the text, let the user correct it, save to `voice/ref.txt`.
4. Make the example reel to prove everything works: `.venv-tts` python `factory/make_reel.py reels/example-chatgpt-resume`. Read `out/REPORT.md`. Fix until PASS.

## 1. Research and script
- One idea per reel, something the viewer can try today.
- Verify every fact, feature, menu name, price or number on the web first. Put sources in `reel.json -> sources`. If you can't verify it, leave it out. Never invent stats or results.
- Natural spoken language, like explaining to a friend. Hook lands in the first 2 seconds. Max 3 steps.
- CTA: save + follow, or a comment keyword ("താഴെ GUIDE എന്ന് comment ചെയ്യൂ"). Don't speak the handle; it shows on screen.
- Show the script beat by beat and wait for the user's OK before voicing.

## 2. Write `FACTORY/reels/NN-slug/reel.json`
Copy the shape of `reels/example-chatgpt-resume/reel.json`.
- top: `slug`, `title`, `topic`, `sources[]`, optional `pronounce{}` (spoken overrides for this reel)
- `beats[]`: `id`, `scene`, `say` (narration as shown on screen), `pause_between_ms` (350-600), `pause_after_ms` (600-900 at big moments), optional `sfx` ("whoosh" / "pop")
  - `hook`: kinetic words; `emphasis[]` words get the accent colour
  - `text`: same style, smaller; optional `kicker` pill, `size`
  - `phone`: `step`, `label`, `app {name, color}`, `screen[]` items: `msg {role user|ai, text}`, `input {text}`, `upload {name}`, `card {title, lines[]}`, `button {label, color}`, `toggle {label}`. Each item: `at` = word in `say` when it appears, optional `delay`, optional `tap_at`.
  - `cta`: `headline`, `say`, `follow_at`, optional `keyword`
- Draw app UIs simply. No real logos, no fake copies of a brand's exact screens.

## 3. Pronunciation (voice clone only)
The clone reads native script only. Every English word in `say` needs a spoken form in `factory/pronounce_ml.json` (suffix forms like `resume-ൽ` get their own entry). Check that no Latin letters remain:
`.venv-tts` python -c "import json,sys;sys.path.insert(0,'factory');import make_reel as m;r=json.load(open('reels/NN-slug/reel.json',encoding='utf-8'));[print(m.spoken_form(s,r)) for b in r['beats'] for s in m.split_sentences(b['say'])]"` (set PYTHONIOENCODING=utf-8 on Windows).

## 4. Preview, then build
- Stills: `make_reel.py reels/NN-slug --stills`. Look at every `out/still_*.jpg`: overflow, overlaps, text shaping, anything under Instagram's right-side buttons (keep content between y 250-1580, x 70-950).
- Full build (run in background, 10-40 min): `make_reel.py reels/NN-slug`. Sentences with speech error over 15% are marked "<-- check": simplify the words or add a pronunciation, rebuild (only changed sentences regenerate).

## 5. Check and deliver
- Read `out/REPORT.md`, look at `out/contact_sheet.jpg`. Never call a reel done without PASS.
- Write `reels/NN-slug/caption.txt` (hook line before "... more", 2-4 short lines, one ask, 3 hashtags, no em dashes). A PASS copies MP4 + caption to `finished/`.
- Tell the user where the file is and what QA said.

## Never
Post, upload, buy, message anyone, print or store tokens/passwords, delete the user's files, or say something works without testing it.

## Known fixes
- `.venv-f5` needs transformers==4.49.0, datasets<3.2, pyarrow<18 (pinned in requirements-f5.txt).
- IndicF5's forward() ignores speed, so `factory/tts_indicf5.py` calls infer_process directly.
- faster-whisper can fail opening files via PyAV; `asr_check.load_16k` decodes with ffmpeg instead.
- 2 GB GPUs work (clone peaks ~1.5 GB, ~40-60 s per sentence take). Close other GPU apps while voicing.
- If the clone adds a sound from the end of the reference clip, re-record the reference ending on a neutral word.
