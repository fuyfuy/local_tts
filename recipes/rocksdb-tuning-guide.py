"""Download + clean the RocksDB Tuning Guide wiki page (Stage 0 + Stage 2).

A single GitHub wiki page, fetched as Markdown from the raw wiki endpoint (no
HTML parsing needed — raw.githubusercontent.com/wiki serves clean Markdown).
Document-specific logic: the fetch URL, wiki-link cleanup, and heading-level
split. LLM plumbing comes from ``tts.llm``.

Usage (from the repo root):
    python recipes/rocksdb-tuning-guide.py               # download + clean
    python recipes/rocksdb-tuning-guide.py --download-only
    python recipes/rocksdb-tuning-guide.py --clean-only
"""

import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]   # repo root
sys.path.insert(0, str(ROOT))

from tts import llm

NAME = "rocksdb-tuning-guide"
TITLE = "RocksDB Tuning Guide"
RAW_DIR = ROOT / "corpus" / NAME / "raw"
CLEAN_DIR = ROOT / "corpus" / NAME / "clean"
PROMPT = (ROOT / "cleanup_prompt.txt").read_text(encoding="utf-8").strip()

# Extend the default prompt if a tailored one exists.
PROMPT_EXT = ROOT / "prompt_rocksdb-tuning-guide.txt"
if PROMPT_EXT.exists():
    PROMPT = PROMPT + "\n\n" + PROMPT_EXT.read_text(encoding="utf-8").strip()

WIKI_URL = "https://raw.githubusercontent.com/wiki/facebook/rocksdb/RocksDB-Tuning-Guide.md"


# --------------------------------------------------------------------------
# Stage 0: fetch the wiki page as Markdown
# --------------------------------------------------------------------------

def download():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dst = RAW_DIR / "00_tuning-guide.md"
    if dst.exists():
        print(f"skip  {dst.name}  (already downloaded)")
        return
    r = requests.get(WIKI_URL, timeout=600)
    r.raise_for_status()
    dst.write_text(r.text + "\n", encoding="utf-8")
    print(f"wrote {dst.name}  ({len(r.text)} chars)")


# --------------------------------------------------------------------------
# Stage 2
# --------------------------------------------------------------------------

_WIKI_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def _wiki_link(m):
    """[[Page]] -> Page ; [[Page|Label]] -> Label ; [[Section|Page#anchor]] -> Section."""
    target, label = m.group(1).strip(), (m.group(2) or "").strip()
    if label and "#" in label:
        return target            # '[[Parallelism options|... #Parallelism options]]'
    return label or target


def strip_noise(md: str) -> str:
    """Wiki links -> display text; clean up heading and author-note artifacts."""
    md = _WIKI_LINK.sub(_wiki_link, md)
    # '### Heading ###' -> '### Heading'
    md = re.sub(r"^(\s*#{1,6}\s.*?)\s*#+\s*$", r"\1", md, flags=re.M)
    # Unfinished author notes that would verbalize badly.
    md = re.sub(r"(?m)^\s*Total DB size\?+\s*$", "", md)
    md = re.sub(r"\s*Shards\?+\s*", " ", md)
    return md


def split(md: str) -> list[str]:
    """Wiki: sections, subsections, and sub-subsections are '##', '###', '####'.
    Split on all three so each gets its own spoken heading. The intro paragraph
    precedes the first '##' and becomes the opening chunk."""
    md = strip_noise(md)
    return [p.strip() for p in re.split(r"(?m)^(?=#{2,4} )", md) if p.strip()]


def main():
    args = sys.argv[1:]
    do_download = "--clean-only" not in args
    do_clean = "--download-only" not in args

    if do_download:
        download()

    if do_clean:
        CLEAN_DIR.mkdir(exist_ok=True)
        (CLEAN_DIR.parent / "title.txt").write_text(TITLE + "\n", encoding="utf-8")
        for src in sorted(RAW_DIR.glob("*.md")):
            llm.clean_file(src, CLEAN_DIR / (src.stem + ".txt"), split, PROMPT)


if __name__ == "__main__":
    main()
