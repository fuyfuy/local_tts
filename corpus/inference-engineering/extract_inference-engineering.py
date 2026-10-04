"""Stage 0: extract the "Inference Engineering" PDF into Markdown.

Uses pymupdf4llm. Chapters are the level-2 PDF bookmarks; each ends where the
next chapter begins. Output lands in raw/ (one .md per chapter).

Usage (from text-to-voice/):
    python corpus/inference-engineering/extract_inference-engineering.py
"""

import re
from pathlib import Path

import pymupdf
import pymupdf4llm

ROOT = Path(__file__).resolve().parents[2]   # text-to-voice/
BOOK = ROOT / "Inference Engineering.pdf"
OUT = Path(__file__).resolve().parent / "raw"
OUT.mkdir(exist_ok=True)


def slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "chapter"


def main():
    doc = pymupdf.open(BOOK)
    toc = doc.get_toc()

    # Chapters are the level-2 bookmarks; each ends where the next chapter begins.
    l2 = [(title, page) for level, title, page in toc if level == 2]

    chapters = []
    for n, (title, start) in enumerate(l2):
        end = l2[n + 1][1] - 1 if n + 1 < len(l2) else doc.page_count
        chapters.append((title, start, end))

    for n, (title, start, end) in enumerate(chapters):
        # pymupdf4llm pages are 0-based; range is [start, end) exclusive
        md = pymupdf4llm.to_markdown(doc, pages=range(start - 1, end))
        fname = f"{n:02d}_{slug(title)}.md"
        (OUT / fname).write_text(md, encoding="utf-8")
        print(f"{fname:45} pages {start:>3}-{end:<3}  {len(md):>8d} chars")


if __name__ == "__main__":
    main()
