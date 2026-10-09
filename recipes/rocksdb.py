"""Clean the RocksDB paper (Stage 2).

A paper: the only document-specific decision is that sections and subsections
are both ``##`` headings (there are no ``###`` headings), so we split on ``## ``
alone. The title + abstract precede the first section and form the opening chunk.

Usage (from the repo root):
    python recipes/rocksdb.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # repo root
sys.path.insert(0, str(ROOT))

from tts import llm

NAME = "rocksdb"
TITLE = "RocksDB: Evolution of Development Priorities"
RAW_DIR = ROOT / "corpus" / NAME / "raw"
CLEAN_DIR = ROOT / "corpus" / NAME / "clean"
PROMPT = (ROOT / "cleanup_prompt.txt").read_text(encoding="utf-8").strip()


def split(md: str) -> list[str]:
    """Paper: sections and subsections are both ``##``; split on ``## `` so each
    gets its own spoken heading. The title + abstract precede the first section."""
    return [p.strip() for p in re.split(r"(?m)^(?=## )", md) if p.strip()]


def main():
    files = sorted(RAW_DIR.glob("*.md"))
    if len(sys.argv) > 1:
        files = [f for f in files if sys.argv[1] in f.stem]

    CLEAN_DIR.mkdir(exist_ok=True)
    (CLEAN_DIR.parent / "title.txt").write_text(TITLE + "\n", encoding="utf-8")
    for src in files:
        llm.clean_file(src, CLEAN_DIR / (src.stem + ".txt"), split, PROMPT)


if __name__ == "__main__":
    main()
