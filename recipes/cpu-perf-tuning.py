"""Clean the "Performance Analysis and Tuning on Modern CPUs" book (Stage 2).

Per PREP.md, the ONLY document-specific logic here is ``split()`` (which heading
levels are section boundaries). All LLM plumbing is imported from ``tts.llm``.

Structure: chapters are ``#``, sections are ``##`` (3.1), sub-sections are
``###`` (3.3.1). We split on ``## `` and ``### `` so each sub-section gets its
own narration block and spoken heading ("three point three point one").

Usage (from the repo root):
    python recipes/cpu-perf-tuning.py            # all chapters
    python recipes/cpu-perf-tuning.py 03         # one chapter
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # repo root
sys.path.insert(0, str(ROOT))

from tts import llm

NAME = "cpu-perf-tuning"
TITLE = "Performance Analysis and Tuning on Modern CPUs"
RAW_DIR = ROOT / "corpus" / NAME / "raw"          # stage 0 output (extracted Markdown)
CLEAN_DIR = ROOT / "corpus" / NAME / "clean"      # stage 2 output (narration)

# Default editing prompt + this book's extension (code-heavy prose, pronunciations).
PROMPT = (ROOT / "cleanup_prompt.txt").read_text(encoding="utf-8").strip()
PROMPT += "\n\n" + (ROOT / "prompt_cpu-perf-tuning.txt").read_text(encoding="utf-8").strip()


def split(md: str) -> list[str]:
    """Book: split on '## ' and '### ' so sections and sub-sections each get
    their own section and spoken heading."""
    return [p.strip() for p in re.split(r"(?m)^(?=#{2,3} )", md) if p.strip()]


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
