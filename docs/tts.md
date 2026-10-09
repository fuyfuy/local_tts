# Text-to-Speech (Stage 3)

Input: `clean/*.txt` (stage 2 output). Output: one audio file per chapter in `audio/`.

## Tool: Kokoro

**Kokoro** (~82M params, Apache-licensed weights) is the pragmatic default for
long-form narration: tiny, fast, decent prosody, and it runs comfortably on CPU
(your 8 GB GPU isn't even needed for this stage).

Alternatives, if you later want to experiment:
- **Piper** — even lighter, worse prosody.
- **Qwen3-TTS / Chatterbox / NeuTTS Air** — heavier models, zero-shot voice
  cloning. Only worth it if you want a specific voice; not needed for narration.

## Setup

```bash
.venv/bin/pip install "kokoro>=0.9.4" soundfile
sudo apt-get install -y espeak-ng   # optional but recommended (English fallback)
```

The model weights download automatically on first use.

## Generate

```python
from pathlib import Path
import soundfile as sf
from kokoro import KPipeline

VOICE = "af_heart"
SR    = 24000                    # Kokoro's native sample rate

pipeline = KPipeline(lang_code="a")   # 'a' = American English, 'b' = British

Path("audio").mkdir(exist_ok=True)

for txt in sorted(Path("clean").glob("*.txt")):
    text = txt.read_text(encoding="utf-8")
    out  = Path("audio") / f"{txt.stem}.wav"
    with sf.SoundFile(out, "w", SR, channels=1) as f:
        # split_pattern=r"\n+" splits on our blank-line paragraph breaks,
        # yielding one audio segment per paragraph, appended into one file.
        for gs, ps, audio in pipeline(text, voice=VOICE, speed=1.0,
                                      split_pattern=r"\n+"):
            f.write(audio)
    print(f"wrote {out}")
```

Run: this is `pipeline/synth.py` (a whole corpus) or `pipeline/say.py` (one file);
the snippet above is illustrative of what those scripts do.

## Knobs worth knowing

- **Voice** — `af_heart` is the default; `af_nova`, `am_michael`, `bf_emma`,
  `bm_george` are common others. See Kokoro's `SAMPLES.md` on HuggingFace for the
  full list. Swap `VOICE` and regenerate a single chapter to A/B voices.
- **Speed** — 1.0 default; try 0.9–1.1 for narration pacing.
- **`split_pattern`** — where Kokoro cuts the audio into segments. Our cleaned
  text has paragraphs separated by blank lines, so `r"\n+"` is the right cut.
  Cutting at paragraph (not sentence) boundaries keeps prosody smooth.
- **Sample rate** — Kokoro outputs 24 kHz mono. Keep it; don't resample.

## Pronunciation

Most pronunciation problems are already solved upstream: the cleanup prompt
spells out `e.g.` → "for example", `×` → "times", `5.1.1` → "five point one
point one", etc. If Kokoro still mangles a domain term ("matmul", "LoRA"),
the reliable fix is to spell it out in the *cleaned text* ("matrix multiply",
"low-rank adaptation") rather than fight the engine's grapheme-to-phoneme pass.

## Output format

24 kHz mono WAV per chapter in `audio/`. To compress for a player:

```bash
ffmpeg -i audio/05_chapter-4-software.wav -b:a 64k audio/05_chapter-4-software.mp3
```

Per-chapter files are easier to navigate than one 14-hour file — you can listen
to, regenerate, or re-voice a single chapter without touching the rest.
