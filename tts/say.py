"""Convert one text file to speech with Kokoro (single-file TTS).

Usage:
    python tts/say.py path/to/file.txt
    python tts/say.py path/to/file.txt --voice af_nova --speed 1.1
    python tts/say.py path/to/file.txt --out /tmp/chapter6.wav

Output defaults to a 24 kHz mono .wav next to the input file.
"""

import argparse
from pathlib import Path

import soundfile as sf
from kokoro import KPipeline

SR = 24000  # Kokoro's native sample rate


def main():
    ap = argparse.ArgumentParser(description="Speak a text file with Kokoro.")
    ap.add_argument("path", help="text file to synthesize")
    ap.add_argument("--out", default=None, help="output path (default: <input>.wav)")
    ap.add_argument("--voice", default="af_heart", help="Kokoro voice id")
    ap.add_argument("--speed", type=float, default=1.0, help="speech rate, 0.9-1.1 typical")
    ap.add_argument("--lang", default="a", help="'a'=American English, 'b'=British")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    args = ap.parse_args()

    src = Path(args.path)
    text = src.read_text(encoding="utf-8")
    out = Path(args.out) if args.out else src.with_suffix(".wav")

    pipeline = KPipeline(lang_code=args.lang, device=args.device)
    # split_pattern=r"\n+" cuts on blank-line paragraph breaks for smooth prosody.
    with sf.SoundFile(out, "w", SR, channels=1) as f:
        for _gs, _ps, audio in pipeline(text, voice=args.voice, speed=args.speed,
                                        split_pattern=r"\n+"):
            f.write(audio)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
