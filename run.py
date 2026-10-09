"""Batch-run the whole pipeline for one corpus, PDF/HTML -> compressed audio.

Chains: extract (if the corpus has an extractor) -> clean -> synthesize -> compress.

Usage (from the repo root):
    python run.py rocksdb-tuning-guide                       # download + clean + synth + compress
    python run.py rocksdb-tuning-guide --format opus --bitrate 48k
    python run.py rocksdb-tuning-guide --skip-extract --skip-clean   # synth + compress only
    python run.py rocksdb                                     # extract -> clean -> synth + compress

Every stage is idempotent, so re-running skips work that's already done.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable  # use the same interpreter that's running this script


def run(cmd):
    print(f"\n$ {' '.join(str(c) for c in cmd)}\n", flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def main():
    ap = argparse.ArgumentParser(description="Run the full document-to-audio pipeline.")
    ap.add_argument("name", help="corpus slug, e.g. rocksdb-tuning-guide")
    ap.add_argument("--skip-extract", action="store_true")
    ap.add_argument("--skip-clean", action="store_true")
    ap.add_argument("--skip-synth", action="store_true")
    ap.add_argument("--skip-eval", action="store_true")
    ap.add_argument("--strict-eval", action="store_true")
    ap.add_argument("--format", default="mp3", choices=["mp3", "opus", "ogg", "m4a"])
    ap.add_argument("--bitrate", default=None)
    ap.add_argument("--keep-wav", action="store_true")
    args = ap.parse_args()

    name = args.name
    corpus = ROOT / "corpus" / name
    if not corpus.is_dir():
        raise SystemExit(f"no corpus at {corpus}")

    extractor = ROOT / "recipes" / f"{name}-extract.py"
    cleaner = ROOT / "recipes" / f"{name}.py"

    # Stage 0 — extract (PDF sources have a dedicated extractor; HTML sources
    # download inside their clean script instead).
    if not args.skip_extract and extractor.exists():
        run([PY, extractor])

    # Stage 2 — clean (for the blog this also downloads).
    if not args.skip_clean and cleaner.exists():
        run([PY, cleaner])

    # Stage 2.5 — QA gate (warn by default; --strict-eval aborts on flags).
    if not args.skip_eval:
        cmd = [PY, ROOT / "pipeline" / "eval.py", name] + (["--strict"] if args.strict_eval else [])
        print(f"\n$ {' '.join(map(str, cmd))}\n", flush=True)
        rc = subprocess.run([str(c) for c in cmd]).returncode
        if rc != 0:
            raise SystemExit("QA gate flagged issues — aborting before synth "
                             "(re-run with --skip-eval to override)")

    # Stage 3 — synthesize WAVs, then compress.
    if not args.skip_synth:
        run([PY, ROOT / "pipeline" / "synth.py", corpus])
        convert = [PY, ROOT / "pipeline" / "convert.py", corpus / "audio", "--format", args.format]
        if args.bitrate:
            convert += ["--bitrate", args.bitrate]
        if args.keep_wav:
            convert += ["--keep-wav"]
        run(convert)

    print(f"\nall done for '{name}'")


if __name__ == "__main__":
    main()
