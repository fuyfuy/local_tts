import re
import sys
from collections import Counter
from pathlib import Path

CLEAN = Path("corpus/inference-engineering/clean")   # stage 2 output (cleaned narration)
IN    = Path("corpus/inference-engineering/raw")     # stage 1 output (raw markdown)


def markdown_residue(t):
    """Counts of leftover Markdown syntax that should have been stripped."""
    patterns = [r"#", r"\*\*", r"`", r"^\s*\|", r"\]\(", r"http"]
    return {p: len(re.findall(p, t, re.M)) for p in patterns}


def orphan_numbers(t):
    """Lines that are just a number — leaked page numbers."""
    return [ln for ln in t.splitlines()
            if re.fullmatch(r"\s*\d{1,4}\s*", ln)]


def dangling_lines(t):
    """Non-empty lines that don't end in terminal punctuation."""
    return [ln.strip() for ln in t.splitlines()
            if ln.strip() and not ln.strip().endswith((".", "?", "!"))]


def repeated_lines(t, thr=3):
    """Long lines that repeat — running headers not stripped."""
    lines = [ln.strip() for ln in t.splitlines() if len(ln.strip()) > 15]
    return [(l, c) for l, c in Counter(lines).items() if c >= thr]


def ok(key, value):
    """True if the check passes for a clean file."""
    limits = {
        "md_residue":     lambda d: sum(d.values()) == 0,
        "orphan_numbers": lambda n: n == 0,
        "dangling_lines": lambda n: n == 0,
        "repeated_lines": lambda n: n == 0,
        "length_ratio":   lambda r: 0.5 <= r <= 1.3,
    }
    return limits[key](value)


def fmt(value):
    """Compact display: dicts show only the non-zero patterns."""
    if isinstance(value, dict):
        hits = {k: n for k, n in value.items() if n}
        return "0" if not hits else str(hits)
    return str(value)


def main():
    files = sorted(CLEAN.glob("*.txt"))
    if not files:
        print(f"no cleaned files in {CLEAN}/ — run clean.py first")
        return
    if len(sys.argv) > 1:   # e.g. `python eval.py 06` to check one chapter
        files = [f for f in files if sys.argv[1] in f.stem]

    total = 0
    for f in files:
        t = f.read_text(encoding="utf-8")
        src = IN / (f.stem + ".md")
        if not src.exists():
            print(f"\n=== {f.name} ===  (no source .md to compare)")
            continue

        ratio = len(t) / max(len(src.read_text(encoding="utf-8")), 1)
        report = {
            "md_residue":     markdown_residue(t),
            "orphan_numbers": len(orphan_numbers(t)),
            "dangling_lines": len(dangling_lines(t)),
            "repeated_lines": len(repeated_lines(t)),
            "length_ratio":   round(ratio, 2),
        }
        flags = sum(not ok(k, v) for k, v in report.items())
        total += flags

        print(f"\n=== {f.name} ===  ({flags} check(s) flagged)")
        for k, v in report.items():
            mark = "ok" if ok(k, v) else "  <-- CHECK"
            print(f"  {k:16} {fmt(v):35} {mark}")

    print(f"\n--- {total} check(s) flagged across {len(files)} file(s) ---")


if __name__ == "__main__":
    main()
