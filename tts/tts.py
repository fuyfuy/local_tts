"""Stage 3: narration ``.txt`` -> audio, using Kokoro.

Usage:
    python tts/tts.py corpus/inference-engineering   # clean/*.txt -> audio/*.wav
    python tts/tts.py --device cpu                   # force CPU
    python tts/tts.py --device auto                  # default: GPU if free, else CPU

Requires:
    pip install "kokoro>=0.9.4" soundfile
"""

import argparse
import json
import time
import urllib.request
from pathlib import Path

import soundfile as sf
import torch
from kokoro import KPipeline

VOICE = "af_heart"
SR = 24000

# Basename of the optional per-book file: every chapter's WAV concatenated into
# one file (chapter order), stored alongside the per-chapter files.
BOOK_FILE = "all_in_one"

# Ollama keeps a model resident in VRAM for OLLAMA_KEEP_ALIVE (default 5m)
# after its last request. We wait that long plus a 2m safety buffer before
# deciding the GPU is genuinely busy and falling back to CPU.
OLLAMA_KEEP_ALIVE_S = 5 * 60
OLLAMA_FLUSH_WAIT_S = OLLAMA_KEEP_ALIVE_S + 2 * 60
MIN_FREE_VRAM_BYTES = 1.5 * 2**30   # Kokoro needs ~1 GB of headroom


def _ollama_busy() -> bool:
    """True while Ollama has any model resident in VRAM."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=2) as r:
            return bool(json.load(r).get("models"))
    except Exception:
        return False   # can't reach Ollama — assume the GPU is free


def resolve_device(want: str) -> str:
    """Map ``--device`` to a concrete value.

    ``auto`` (the default) prefers the GPU but only commits to it once Ollama
    has flushed its VRAM cache (bounded wait) and enough memory is actually
    free. Otherwise it falls back to CPU.
    """
    if want in ("cpu", "cuda"):
        return want
    if not torch.cuda.is_available():
        return "cpu"

    deadline = time.time() + OLLAMA_FLUSH_WAIT_S
    while time.time() < deadline and _ollama_busy():
        print(f"    waiting for Ollama to release the GPU "
              f"({OLLAMA_FLUSH_WAIT_S // 60}m budget) ...", flush=True)
        time.sleep(10)

    free = torch.cuda.mem_get_info()[0]
    return "cuda" if free >= MIN_FREE_VRAM_BYTES else "cpu"


def synth_corpus(corpus: Path, device: str = "auto") -> None:
    clean_dir = corpus / "clean"
    audio_dir = corpus / "audio"
    audio_dir.mkdir(exist_ok=True)

    device = resolve_device(device)
    try:
        pipeline = KPipeline(lang_code="a", device=device)
    except torch.cuda.OutOfMemoryError:
        print("    CUDA OOM building pipeline — falling back to CPU", flush=True)
        device, pipeline = "cpu", KPipeline(lang_code="a", device="cpu")
    print(f"synth device: {device}", flush=True)

    files = sorted(clean_dir.glob("*.txt"))
    if not files:
        print(f"no .txt files in {clean_dir} — run clean_{corpus.name}.py first")
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
        print(f"wrote {out}", flush=True)

    # Concatenate every chapter (sorted order) into one per-book file alongside
    # the per-chapter WAVs. convert.py then compresses it like any other WAV.
    chapter_wavs = [w for w in sorted(audio_dir.glob("*.wav"))
                    if w.stem != BOOK_FILE]
    if len(chapter_wavs) > 1:
        book_wav = audio_dir / f"{BOOK_FILE}.wav"
        concat_wavs(chapter_wavs, book_wav)
        print(f"wrote {book_wav}  ({len(chapter_wavs)} chapters)", flush=True)


def concat_wavs(sources: list[Path], dst: Path) -> None:
    """Concatenate mono WAVs (same sample rate/channels) into a single WAV."""
    if not sources:
        return
    with sf.SoundFile(sources[0]) as first:
        sr = first.samplerate
        ch = first.channels
        subtype = first.subtype
    with sf.SoundFile(dst, "w", sr, ch, subtype=subtype) as out:
        for src in sources:
            with sf.SoundFile(src) as f:
                out.write(f.read())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Synthesize a corpus's clean/*.txt to WAV.")
    ap.add_argument("corpus", nargs="?", default=".", help="path to the corpus dir")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    args = ap.parse_args()
    synth_corpus(Path(args.corpus), device=args.device)
