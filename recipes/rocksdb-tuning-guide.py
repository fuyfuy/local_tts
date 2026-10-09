"""Download + clean the RocksDB wiki pages (Stage 0 + Stage 2).

A collection of GitHub wiki pages, fetched as Markdown from the raw wiki
endpoint (no HTML parsing needed — raw.githubusercontent.com/wiki serves clean
Markdown). Document-specific logic: the page list (with a numeric prefix that
sets the all-in-one reading order), wiki-link/image/byline cleanup, and the
heading-level split. LLM plumbing comes from ``tts.llm``.

Usage (from the repo root):
    python recipes/rocksdb-tuning-guide.py               # download + clean all
    python recipes/rocksdb-tuning-guide.py --download-only
    python recipes/rocksdb-tuning-guide.py --clean-only
    python recipes/rocksdb-tuning-guide.py 02            # only files matching "02"
"""

import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]   # repo root
sys.path.insert(0, str(ROOT))

from tts import llm

NAME = "rocksdb-tuning-guide"
TITLE = "RocksDB Wiki"
RAW_DIR = ROOT / "corpus" / NAME / "raw"
CLEAN_DIR = ROOT / "corpus" / NAME / "clean"
PROMPT = (ROOT / "cleanup_prompt.txt").read_text(encoding="utf-8").strip()

# Extend the default prompt if a tailored one exists.
PROMPT_EXT = ROOT / "prompt_rocksdb-tuning-guide.txt"
if PROMPT_EXT.exists():
    PROMPT = PROMPT + "\n\n" + PROMPT_EXT.read_text(encoding="utf-8").strip()

# (slug, wiki page). The numeric prefix sets the reading order of the
# concatenated all-in-one audio (sorted by filename).
PAGES = [
    ("00_rocksdb-overview", "RocksDB-Overview"),
    ("01_rocksdb-tuning-guide", "RocksDB-Tuning-Guide"),
    ("02_memtable", "MemTable"),
    ("03_block-cache", "Block-Cache"),
    ("04_write-buffer-manager", "Write-Buffer-Manager"),
    ("05_compaction", "Compaction"),
    ("06_universal-compaction", "Universal-Compaction"),
    ("07_io", "IO"),
    ("08_iterator", "Iterator"),
    ("09_prefix-seek", "Prefix-Seek"),
    ("10_column-families", "Column-Families"),
    ("11_transactions", "Transactions"),
    ("12_snapshot", "Snapshot"),
    ("13_read-only-and-secondary-instances", "Read-only-and-Secondary-instances"),
    ("14_delete-a-range-of-keys", "Delete-A-Range-Of-Keys"),
    ("15_memory-usage-in-rocksdb", "Memory-usage-in-RocksDB"),
]

WIKI_BASE = "https://raw.githubusercontent.com/wiki/facebook/rocksdb"


# --------------------------------------------------------------------------
# Stage 0: fetch each wiki page as Markdown
# --------------------------------------------------------------------------

def download():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for slug, page in PAGES:
        dst = RAW_DIR / f"{slug}.md"
        if dst.exists():
            print(f"skip  {dst.name}  (already downloaded)")
            continue
        r = requests.get(f"{WIKI_BASE}/{page}.md", timeout=600)
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
    """Wiki links -> display text; drop images and bylines; clean heading artifacts."""
    md = _WIKI_LINK.sub(_wiki_link, md)
    # Malformed wiki link missing a closing bracket, e.g. '[[Direct IO] mode'.
    md = re.sub(r"\[\[([^\]\n|]+)\](?!\])", r"\1", md)
    # Drop images (diagrams with no spoken caption).
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)
    # '### Heading ###' -> '### Heading'
    md = re.sub(r"^(\s*#{1,6}\s.*?)\s*#+\s*$", r"\1", md, flags=re.M)
    # Drop byline headings ('##### Author: ...').
    md = re.sub(r"(?m)^\s*#{1,6}\s*Author:.*$", "", md)
    return md


def split(md: str) -> list[str]:
    """Wiki pages: sections/subsections are '#'..'####' headings. Split on all of
    them so each gets its own spoken heading; a flat page (no headings) becomes a
    single chunk."""
    md = strip_noise(md)
    return [p.strip() for p in re.split(r"(?m)^(?=#{1,4} )", md) if p.strip()]


def main():
    args = sys.argv[1:]
    do_download = "--clean-only" not in args
    do_clean = "--download-only" not in args
    needle = next((a for a in args if not a.startswith("--")), None)

    if do_download:
        download()

    if do_clean:
        CLEAN_DIR.mkdir(exist_ok=True)
        (CLEAN_DIR.parent / "title.txt").write_text(TITLE + "\n", encoding="utf-8")
        files = sorted(RAW_DIR.glob("*.md"))
        if needle is not None:
            files = [f for f in files if needle in f.stem]
        for src in files:
            llm.clean_file(src, CLEAN_DIR / (src.stem + ".txt"), split, PROMPT)


if __name__ == "__main__":
    main()
