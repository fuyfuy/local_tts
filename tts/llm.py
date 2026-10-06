"""Shared Stage 2 plumbing: Markdown sections -> spoken narration.

Every generated ``recipes/{name}.py`` imports these helpers and supplies its own
``split()`` function. This module owns the parts that must be identical
everywhere, including the hard-won fixes:

  * ``"think": False`` at the TOP LEVEL of the request (not inside ``options``).
    Thinking-capable models otherwise burn the context window on a hidden
    reasoning preamble and return empty or truncated responses.
  * ``done_reason == "length"`` is treated as an error, so a truncated section
    falls back to a ``[CLEANUP FAILED]`` marker instead of silently dropping
    text.
  * Ollama 0.34+ returns timing fields at the top level of the response.
"""

import time

import requests

MODEL = "qwen3.5:9b"
URL = "http://localhost:11434/api/generate"

# Safety net: split any section larger than this into paragraph-sized chunks so
# it never blows the context window. Flat documents (no sub-headings) otherwise
# produce one huge section that fails to clean.
MAX_SECTION_CHARS = 8000


def print_timings(t: dict) -> None:
    """Print per-request timing; Ollama 0.34+ puts fields at the top level."""
    if not t:
        return
    prefill_s = t.get("prompt_eval_duration", 0) / 1e9
    decode_s = t.get("eval_duration", 0) / 1e9
    n_pre = t.get("prompt_eval_count", 0)
    n_dec = t.get("eval_count", 0)
    print(f"    prefill {n_pre} tok in {prefill_s:.2f}s "
          f"({n_pre/prefill_s if prefill_s else 0:.0f} tok/s) | "
          f"decode {n_dec} tok in {decode_s:.2f}s "
          f"({n_dec/decode_s if decode_s else 0:.0f} tok/s)",
          flush=True)


def clean_chunk(text, system, *, model=MODEL, url=URL, temp=0.2, num_ctx=8192,
                timeout=600, retries=2):
    """Send one Markdown section to the LLM, return spoken prose."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, json={
                "model": model,
                "system": system,
                "prompt": text,
                "stream": False,
                "think": False,   # top level, NOT inside options
                "options": {"temperature": temp, "num_ctx": num_ctx},
            }, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            if data.get("done_reason") == "length":
                raise RuntimeError("response truncated (hit context limit)")
            print_timings(data)
            return data["response"].strip()
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def _chunk(section: str, max_chars: int = MAX_SECTION_CHARS) -> list[str]:
    """Split an oversized section into sub-chunks at paragraph boundaries."""
    if len(section) <= max_chars:
        return [section]
    paras = section.split("\n\n")
    chunks, cur, cur_len = [], [], 0
    for p in paras:
        if cur and cur_len + len(p) + 2 > max_chars:
            chunks.append("\n\n".join(cur))
            cur, cur_len = [], 0
        cur.append(p)
        cur_len += len(p) + 2
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def clean_file(src, dst, split_fn, system, *, model=MODEL, url=URL, temp=0.2,
               num_ctx=8192, timeout=600):
    """Read ``src`` Markdown, split with ``split_fn``, clean, write ``dst``."""
    if dst.exists():
        print(f"skip  {src.name}  (already cleaned)")
        return

    sections = split_fn(src.read_text(encoding="utf-8"))
    sections = [c for sec in sections for c in _chunk(sec)]
    cleaned = []
    for i, sec in enumerate(sections):
        print(f"  [{src.name}] section {i+1}/{len(sections)} "
              f"({len(sec)} chars) ...", flush=True)
        try:
            cleaned.append(clean_chunk(sec, system, model=model, url=url,
                                       temp=temp, num_ctx=num_ctx,
                                       timeout=timeout))
        except Exception as e:
            print(f"    !! failed: {e} -- keeping raw section", flush=True)
            cleaned.append(f"[CLEANUP FAILED]\n\n{sec}")

    dst.write_text("\n\n".join(cleaned), encoding="utf-8")
    print(f"wrote {dst.name}  ({len(sections)} sections)")
