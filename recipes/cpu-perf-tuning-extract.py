"""Stage 0: extract the "Performance Analysis and Tuning on Modern CPUs" PDF.

Chapters are the level-1 (``#``) headings in the Markdown that pymupdf4llm
produces; we split on those. Front/back matter that isn't narration-worthy is
skipped (Notices, the table of contents, the empty "Part 1" divider, and the
"Support This Book" promo page). "Part 2" is kept because it carries a real
intro (Data-Driven Development + a roadmap of chapters 8-13).

Noise is stripped structurally here (per the skill: prefer Stage 0 over the
prompt). Every page of this PDF carries:
  * a running header — an all-italic line (``_3 CPU Microarchitecture_``), and
  * a page-number footer — a bare digit line,
  * <sup> citation markers, plus <mark>/<u> highlight & underline tags.

We extract the whole book in one pymupdf4llm call so heading levels stay
consistent (per-page extraction misclassifies section headings as H1).

Usage (from the repo root):
    python recipes/cpu-perf-tuning-extract.py
"""

import re
from pathlib import Path

import pymupdf
import pymupdf4llm

ROOT = Path(__file__).resolve().parents[1]   # repo root
BOOK = ROOT / "PerformanceAnalysisAndTuningOnModernCPUs_SecondEdition.pdf"
OUT = ROOT / "corpus" / "cpu-perf-tuning" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

# H1 headings to drop entirely (not narration).
SKIP = {
    "Notices",
    "Table Of Contents",
    "Part 1. Performance Analysis on a Modern CPU",   # empty divider page
    "Support This Book",
}


def slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "chapter"


def strip_noise(md: str) -> str:
    """Remove running headers, page numbers, and markup tags from the book."""
    # Highlight/underline markup: keep the text, drop the tags.
    for tag in ("<mark>", "</mark>", "<u>", "</u>"):
        md = md.replace(tag, "")
    # Citation markers (superscript digits) point at the References — drop them.
    md = re.sub(r"<sup>.*?</sup>", "", md, flags=re.S)
    md = md.replace("<br>", " ")

    # Running headers: lines that are only italic spans (one or more _..._).
    before = len(md.splitlines())
    md = re.sub(r"(?m)^[ \t]*(?:_[^_]*_[ \t]*)+$", "", md)
    headers = before - len(md.splitlines())

    # Page-number footers: bare digit lines.
    before = len(md.splitlines())
    md = re.sub(r"(?m)^[ \t]*\d{1,4}[ \t]*$", "", md)
    numbers = before - len(md.splitlines())

    print(f"stripped {headers} running-header lines, {numbers} page-number lines")
    return md


def main():
    doc = pymupdf.open(BOOK)
    md = pymupdf4llm.to_markdown(doc)          # whole book, correct heading levels
    md = strip_noise(md)

    # Split on '#' (H1) headings; the text before the first heading is the cover.
    parts = re.split(r"(?m)^(?=# )", md)

    chapters = []
    for part in parts:
        m = re.match(r"^# \*\*(.+?)\*\*", part.strip())
        if not m:
            continue
        title = m.group(1).strip()
        if title in SKIP:
            print(f"skip  {title}")
            continue
        chapters.append((title, part.strip()))

    for n, (title, text) in enumerate(chapters):
        fname = f"{n:02d}_{slug(title)}.md"
        (OUT / fname).write_text(text + "\n", encoding="utf-8")
        print(f"{fname:55} {len(text):>8d} chars")


if __name__ == "__main__":
    main()
