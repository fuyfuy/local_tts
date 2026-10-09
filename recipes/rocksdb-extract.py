"""Stage 0: extract the RocksDB paper PDF into Markdown.

A single 32-page ACM paper (no TOC bookmarks), so we extract the whole document
in one ``pymupdf4llm`` call and split on the ``##`` section headings. ACM papers
carry a lot of page furniture that must be stripped structurally, per the
skill's "prefer Stage 0 over the prompt" rule:

  * running headers/footers ("ACM Transactions on Storage ...", "S. Dong et al.",
    "RocksDB: Evolution ...", "26:3" page:column markers, "**26**" page numbers)
  * title-page metadata (authors, CCS concepts, keywords, ACM reference format,
    copyright, license, authors' addresses)
  * inline citation markers ("[19, 94]", "[39]") and superscript footnote markers
  * ``<br>`` inside table cells

The REFERENCES bibliography is dropped (not narration). The title + abstract are
kept so the audio opens with the paper title and its abstract.

Usage (from the repo root):
    python recipes/rocksdb-extract.py
"""

import re
from pathlib import Path

import pymupdf4llm

ROOT = Path(__file__).resolve().parents[1]   # repo root
PDF = ROOT / "rocksdb.pdf"
OUT = ROOT / "corpus" / "rocksdb" / "raw"
OUT.mkdir(parents=True, exist_ok=True)


def strip_noise(md: str) -> str:
    """Remove page furniture, citation markers, and metadata from the paper."""
    # Inline markup.
    md = md.replace("<br>", " ")
    md = re.sub(r"<sup>.*?</sup>", "", md, flags=re.S)       # footnote markers
    md = re.sub(r"\[\d+(?:\s*,\s*\d+)*\]", "", md)            # [19, 94] citations

    # Drop the bibliography and everything after it.
    m = re.search(r"(?m)^## \*\*REFERENCES\*\*", md)
    if m:
        md = md[:m.start()]

    kept = []
    for line in md.splitlines():
        s = line.strip()
        if not s:
            kept.append(line)
            continue
        if re.fullmatch(r"\*\*\d+\*\*", s):                  # **26**
            continue
        if re.fullmatch(r"\d+:\d+", s):                      # 26:3
            continue
        if s.startswith("ACM Transactions on Storage"):       # running header
            continue
        if re.fullmatch(r"S\. Dong et al\.", s):             # running header
            continue
        if re.fullmatch(r"RocksDB: Evolution of Development Priorities", s):
            continue                                         # running title
        if s.startswith("© "):                               # copyright line
            continue
        if s.startswith("This work is licensed"):            # license line
            continue
        if s.startswith("Authors"):               # author addresses
            continue
        if s.startswith("SIYING DONG,"):                     # title-page authors
            continue
        if s.startswith("CCS Concepts:"):                    # CCS categories
            continue
        if s.startswith("Additional Key Words"):             # keywords
            continue
        if s.startswith("### **ACM Reference format:**"):    # ACM ref heading
            continue
        if "https://doi.org/10.1145/3483840" in s:           # ACM reference line
            continue
        kept.append(line)

    return "\n".join(kept)


def main():
    md = pymupdf4llm.to_markdown(PDF)
    md = strip_noise(md)
    dst = OUT / "00_rocksdb.md"
    dst.write_text(md + "\n", encoding="utf-8")
    print(f"wrote {dst}  ({len(md)} chars)")


if __name__ == "__main__":
    main()
