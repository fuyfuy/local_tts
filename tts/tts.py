"""Stage 3: narration ``.txt`` -> audio, using Kokoro.

Usage:
    python tts/tts.py corpus/inference-engineering   # clean/*.txt -> audio/*.wav
    python tts/tts.py                                # current dir's clean/ -> audio/

Requires:
    pip install "kokoro>=0.9.4" soundfile
"""

import sys
from pathlib import Path

import soundfile as sf
from kokoro import KPipeline

VOICE = "af_heart"   # see Kokoro's SAMPLES.md for the full voice list
SR = 24000           # Kokoro's native sample rate (24 kHz mono)


def synth_corpus(corpus: Path) -> None:
    clean_dir = corpus / "clean"
    audio_dir = corpus / "audio"
    audio_dir.mkdir(exist_ok=True)

    pipeline = KPipeline(lang_code="a")   # 'a' = American English, 'b' = British

    files = sorted(clean_dir.glob("*.txt"))
    if not files:
        print(f"no .txt files in {clean_dir} -- run clean_{corpus.name}.py first")
        return

    for txt in files:
        out = audio_dir / f"{txt.stem}.wav"
        if out.exists():
            print(f"skip  {out.name}  (already synthesized)")
            continue

        text = txt.read_text(encoding="utf-8")
        # split_pattern=r"\n+" cuts on our blank-line paragraph breaks, giving
        # one audio segment per paragraph, appended into a single file.
        with sf.SoundFile(out, "w", SR, channels=1) as f:
            for _gs, _ps, audio in pipeline(text, voice=VOICE, speed=1.0,
                                            split_pattern=r"\n+"):
                f.write(audio)
        print(f"wrote {out}")


if __name__ == "__main__":
    corpus = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    synth_corpus(corpus)
