# Reel Factory: a Claude skill that makes Malayalam Instagram Reels

ഒരു topic കൊടുത്താൽ മതി. Script, voice, animation, captions, music, quality check, എല്ലാം Claude ചെയ്യും. Edit ചെയ്യേണ്ട കാര്യമില്ല.

Give it one topic. Claude writes the script, makes the voice, animates a kinetic-text hook and phone-mockup steps, adds word-by-word captions and music, then checks the video (resolution, loudness, black frames, speech vs script) before handing you a 1080x1920 MP4.

📘 **മലയാളം step-by-step guide (PDF):** https://spurayil.github.io/zebu-ai-freebies/reel-factory-guide.pdf

## What you need
- **Claude Code** (desktop app or terminal)
- Python 3.10-3.12, Node.js 18+, FFmpeg, Google Chrome
- About 3 GB free disk (12 GB if you want to clone your own voice)
- Optional, for your own voice: an NVIDIA GPU with 2 GB+ and a free Hugging Face account

## Install (2 minutes)
1. Download this repo (green **Code** button → **Download ZIP**) and unzip it.
2. Rename the folder to `reel-factory` and move it to:
   - Windows: `C:\Users\<you>\.claude\skills\reel-factory`
   - Mac/Linux: `~/.claude/skills/reel-factory`
3. Open Claude Code and type:
   ```
   /reel-factory setup
   ```
   Claude asks you a few questions (name, niche, language, voice, colours) and installs the rest.
4. Make a reel:
   ```
   /reel-factory ChatGPT vechu resume ATS-friendly aakkam
   ```

Claude.ai app users: zip this folder and upload it under **Settings → Capabilities → Skills**. Note that rendering video needs Claude Code on your own computer.

## What's inside
- `SKILL.md`: the instructions Claude follows
- `factory/`: voice, renderer (HTML → headless Chrome → FFmpeg), audio mix, QA
- `reels/example-chatgpt-resume/`: an example reel plan
- `teleprompter/index.html`: a teleprompter for recording yourself on camera

## Credits and licences
- Code: MIT (see LICENSE)
- Fonts: Anek Malayalam and Space Grotesk, SIL Open Font License (files in `factory/render/fonts`)
- Voice clone: [ai4bharat/IndicF5](https://huggingface.co/ai4bharat/IndicF5) (accept its licence on Hugging Face). Free voice: Microsoft Edge neural TTS via `edge-tts`.
- Speech check: [kurianbenoy/vegam-whisper-medium-ml](https://huggingface.co/kurianbenoy/vegam-whisper-medium-ml)

Only clone your own voice, or a voice you have permission to use.

Made by [@zebu.ai](https://www.instagram.com/zebu.ai). AI tips in Malayalam.
