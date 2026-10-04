"""Compress WAV audio to a smaller format with ffmpeg.

Our source is mono 24 kHz speech; a lossy codec shrinks it ~10x with no
audible loss. Uses ffmpeg — from PATH, or the pip-installed static build.

Usage:
    python tts/convert.py corpus/inference-engineering/audio            # all *.wav in dir
    python tts/convert.py some.wav --format opus --bitrate 48k
"""

import argparse
import shutil
import subprocess
from pathlib import Path

FORMATS = {
    "mp3":  {"codec": "libmp3lame", "ext": ".mp3"},   # max compatibility
    "opus": {"codec": "libopus",    "ext": ".opus"},  # best quality/size for speech
    "ogg":  {"codec": "libvorbis",  "ext": ".ogg"},
    "m4a":  {"codec": "aac",        "ext": ".m4a"},   # Apple-friendly
}

DEFAULT_BITRATE = {"mp3": "64k", "opus": "48k", "ogg": "64k", "m4a": "64k"}


def _ffmpeg() -> str:
    """Locate ffmpeg: system binary, else the pip-installed static one."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit(
            "ffmpeg not found — run 'sudo apt install ffmpeg' or "
            "'pip install imageio-ffmpeg'."
        )


def convert(src: Path, fmt: str, bitrate: str) -> Path:
    codec = FORMATS[fmt]["codec"]
    dst = src.with_suffix(FORMATS[fmt]["ext"])
    cmd = [_ffmpeg(), "-y", "-loglevel", "error",
           "-i", str(src), "-c:a", codec, "-b:a", bitrate, "-ac", "1", str(dst)]
    subprocess.run(cmd, check=True)
    return dst


def main():
    ap = argparse.ArgumentParser(description="Compress WAV files with ffmpeg.")
    ap.add_argument("path", help="a .wav file or a directory of .wav files")
    ap.add_argument("--format", default="mp3", choices=list(FORMATS))
    ap.add_argument("--bitrate", default=None, help="e.g. 64k, 48k (default per format)")
    ap.add_argument("--keep-wav", action="store_true", help="keep the source .wav")
    args = ap.parse_args()

    fmt = args.format
    bitrate = args.bitrate or DEFAULT_BITRATE[fmt]
    path = Path(args.path)

    wavs = [path] if path.is_file() else sorted(path.glob("*.wav"))
    if not wavs:
        print(f"no .wav files in {path}")
        return

    for wav in wavs:
        dst = convert(wav, fmt, bitrate)
        print(f"wrote {dst}")
        if not args.keep_wav:
            wav.unlink()

    print(f"done ({len(wavs)} files -> {fmt} {bitrate})")


if __name__ == "__main__":
    main()
