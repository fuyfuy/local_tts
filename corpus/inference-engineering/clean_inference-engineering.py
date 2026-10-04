"""Clean the "Inference Engineering" book (Stage 2).

Per PREP.md, the ONLY document-specific logic here is ``split()`` (which heading
levels are section boundaries). All LLM plumbing is imported from ``tts.llm``.

Usage (from text-to-voice/):
    python corpus/inference-engineering/clean_inference-engineering.py         # all
    python corpus/inference-engineering/clean_inference-engineering.py 06      # one chapter
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # text-to-voice/
sys.path.insert(0, str(ROOT))

from tts import llm

NAME = "inference-engineering"
HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw"          # stage 0 output (extracted Markdown)
CLEAN_DIR = HERE / "clean"      # stage 2 output (narration)
PROMPT = (ROOT / "cleanup_prompt.txt").read_text(encoding="utf-8").strip()


def split(md: str) -> list[str]:
    """Book: split on '## ' and '### ' so sub-chapters (5.1, 5.1.3) each get
    their own section and spoken heading."""
    return [p.strip() for p in re.split(r"(?m)^(?=#{2,3} )", md) if p.strip()]


def main():
    files = sorted(RAW_DIR.glob("*.md"))
    if len(sys.argv) > 1:
        files = [f for f in files if sys.argv[1] in f.stem]

    CLEAN_DIR.mkdir(exist_ok=True)
    for src in files:
        llm.clean_file(src, CLEAN_DIR / (src.stem + ".txt"), split, PROMPT)


if __name__ == "__main__":
    main()
