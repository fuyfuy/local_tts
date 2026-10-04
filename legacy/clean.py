import re
import sys
import time
import requests
from pathlib import Path

MODEL = "qwen3.5:9b"
URL   = "http://localhost:11434/api/generate"

IN  = Path("out")     # stage 1: extracted markdown
OUT = Path("clean")   # stage 2: cleaned narration
OUT.mkdir(exist_ok=True)

# The editing instructions live in this file so you can tweak them without
# touching this script.
SYSTEM = Path("cleanup_prompt.txt").read_text(encoding="utf-8").strip()

TEMP    = 0.2
NUM_CTX = 8192
TIMEOUT = 600


def _print_timings(t: dict) -> None:
    """Ollama 0.34+ returns per-request timing in nanoseconds at the top level."""
    if not t:
        return
    prefill_s = t.get("prompt_eval_duration", 0) / 1e9
    decode_s  = t.get("eval_duration", 0) / 1e9
    n_pre = t.get("prompt_eval_count", 0)
    n_dec = t.get("eval_count", 0)
    print(f"    prefill {n_pre} tok in {prefill_s:.2f}s "
          f"({n_pre/prefill_s if prefill_s else 0:.0f} tok/s) | "
          f"decode {n_dec} tok in {decode_s:.2f}s "
          f"({n_dec/decode_s if decode_s else 0:.0f} tok/s)",
          flush=True)


def clean_chunk(text: str, retries: int = 2) -> str:
    """Send one section of markdown to the LLM, get back spoken prose."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(URL, json={
                "model": MODEL,
                "system": SYSTEM,
                "prompt": text,
                "stream": False,
                "think": False,
                "options": {"temperature": TEMP, "num_ctx": NUM_CTX},
            }, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if data.get("done_reason") == "length":
                raise RuntimeError("response truncated (hit context limit)")
            _print_timings(data)
            return data["response"].strip()
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def split_chapter(md: str) -> list[str]:
    """Split a chapter on '## ' and '### ' headings, keeping each with its body."""
    return [p.strip() for p in re.split(r"(?m)^(?=#{2,3} )", md) if p.strip()]


def main():
    files = sorted(IN.glob("*.md"))
    if len(sys.argv) > 1:   # e.g. `python clean.py 06` to clean one chapter
        files = [f for f in files if sys.argv[1] in f.stem]

    for src in files:
        dst = OUT / (src.stem + ".txt")
        if dst.exists():
            print(f"skip  {src.name}  (already cleaned)")
            continue

        sections = split_chapter(src.read_text(encoding="utf-8"))
        cleaned = []
        for i, sec in enumerate(sections):
            print(f"  [{src.name}] section {i+1}/{len(sections)} "
                  f"({len(sec)} chars) ...", flush=True)
            try:
                cleaned.append(clean_chunk(sec))
            except Exception as e:
                print(f"    !! failed: {e} -- keeping raw section", flush=True)
                cleaned.append(f"[CLEANUP FAILED]\n\n{sec}")

        dst.write_text("\n\n".join(cleaned), encoding="utf-8")
        print(f"wrote {dst.name}  ({len(sections)} sections)")


if __name__ == "__main__":
    main()
