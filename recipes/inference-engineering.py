"""Clean the "Inference Engineering" book (Stage 2).

Per PREP.md, the ONLY document-specific logic here is ``split()`` (which heading
levels are section boundaries). All LLM plumbing is imported from ``tts.llm``.

Usage (from the repo root):
    python recipes/inference-engineering.py        # all chapters
    python recipes/inference-engineering.py 06     # one chapter
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # repo root
sys.path.insert(0, str(ROOT))

from tts import llm

NAME = "inference-engineering"
TITLE = "Inference Engineering"
RAW_DIR = ROOT / "corpus" / NAME / "raw"          # stage 0 output (extracted Markdown)
CLEAN_DIR = ROOT / "corpus" / NAME / "clean"      # stage 2 output (narration)
PROMPT = (ROOT / "cleanup_prompt.txt").read_text(encoding="utf-8").strip()

# Running headers/footers pymupdf4llm lifted out of this PDF. Every one carries
# the page number in bold. Strip them here, deterministically — if the LLM sees
# them it narrates its own reasoning about them ("the number forty-one ... should
# be omitted") instead of silently dropping them.
PAGE_HEADER    = re.compile(r"^\*\*\d+\*\*\s+.*$")    # "**42** Chapter 2: Models"
PAGE_FOOTER    = re.compile(r"^.*\s\*\*\d+\*\*\s*$")  # "Models **41**", "4.4 NVIDIA Dynamo **111**"
CHAPTER_OPENER = re.compile(r"^CHAPTER\s+(\d+)\s*$")    # "CHAPTER 2"


def strip_page_artifacts(md: str) -> str:
    """Drop running headers/footers and page numbers before the LLM sees them.

    The chapter number only exists in the stripped "CHAPTER N" line, but the
    chapter's real heading ("## **Models**") needs it to be verbalized correctly.
    Without it the model guesses — it latches onto "section 3.4" / "Figure 0.1"
    in the body and drops the opening sentences. So capture N and bake it into
    the chapter-title heading (the first "## **...**" with no numeric prefix).
    """
    chapter_num = None
    out = []
    for line in md.splitlines():
        m = CHAPTER_OPENER.match(line)
        if m:
            chapter_num = int(m.group(1))
            continue
        if PAGE_HEADER.match(line) or PAGE_FOOTER.match(line):
            continue
        out.append(line)
    md = "\n".join(out)
    if chapter_num is not None:
        md = re.sub(
            r"(?m)^## \*\*([^*]+?)\*\*",
            lambda m: f"## **Chapter {chapter_num}: {m.group(1).strip()}**",
            md, count=1)
    return md


def split(md: str) -> list[str]:
    """Book: split on '## ' and '### ' so sub-chapters (5.1, 5.1.3) each get
    their own section and spoken heading.

    Chapters open with a preamble ("CHAPTER N", "# Title", "Title **NN**") that
    duplicates the "## **Title**" heading right after it. Drop that preamble when
    real section headings follow; the preface and appendices have no "## "
    headings, so their leading text is real content and must be kept."""
    md = strip_page_artifacts(md)
    parts = [p.strip() for p in re.split(r"(?m)^(?=#{2,3} )", md) if p.strip()]
    if len(parts) > 1 and not parts[0].startswith(("## ", "### ")):
        parts = parts[1:]
    return parts


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
