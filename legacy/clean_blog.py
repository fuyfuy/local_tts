"""Download ebpf.io blog posts and clean them for TTS narration.

Mirrors the book pipeline (tts-extr.py -> clean.py) but for HTML blog posts:

  stage 1 (download): fetch each URL, pull the <article> body out of the HTML,
                      convert it to Markdown, and save it to blog_out/.
  stage 2 (clean):    split each article on '## ' headings and send each section
                      to Ollama (same cleanup_prompt.txt as the book), writing
                      spoken prose to blog_clean/.

Usage:
    python clean_blog.py                 # download + clean every URL in POSTS
    python clean_blog.py 2               # download + clean only posts matching "2"
    python clean_blog.py --download-only # only fetch + extract (no LLM calls)
    python clean_blog.py --clean-only    # only clean already-downloaded files
"""

import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import requests

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

POSTS = [
    "https://ebpf.io/blog/cloudflare-replatforming-1/",
    "https://ebpf.io/blog/cloudflare-replatforming-2/",
    "https://ebpf.io/blog/cloudflare-replatforming-3/",
]

MODEL = "qwen3.5:9b"
URL   = "http://localhost:11434/api/generate"

IN  = Path("blog_out")    # stage 1: extracted article markdown
OUT = Path("blog_clean")  # stage 2: cleaned narration

# Reuse the book's editing instructions. They're generic ("raw Markdown ->
# narration"), so they work for blog posts too. Swap this path if you want a
# blog-specific variant.
SYSTEM = Path("cleanup_prompt.txt").read_text(encoding="utf-8").strip()

TEMP    = 0.2
NUM_CTX = 8192
TIMEOUT = 600

# Headings whose text means "end of the real article" (site footer noise).
FOOTER_HEADINGS = {"share on social media:", "subscribe to bi-weekly echo news"}


# --------------------------------------------------------------------------
# Stage 1: HTML -> Markdown
# --------------------------------------------------------------------------

class ArticleToMarkdown(HTMLParser):
    """Extract the readable text of an ebpf.io blog post as Markdown.

    Uses only the stdlib so there are no dependencies. Keeps structure that
    matters for narration (headings, paragraphs, lists, code fences) and
    drops nav/footer noise.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []     # finished blocks (list[str])
        self.buf = []       # inline text accumulating in the current block
        self.skip = 0       # >0 => inside a tag we ignore (script/style/svg/time)
        self.pre = 0        # inside <pre> (code block)
        self.stop = False   # reached the footer

    def _flush(self):
        text = "".join(self.buf).strip()
        self.buf = []
        return text

    def handle_starttag(self, tag, attrs):
        if self.stop:
            return
        if tag in ("script", "style", "svg", "noscript", "time"):
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "pre":
            self.pre += 1
            self.parts.append("```")
        elif tag == "li":
            self.buf = ["- "]
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.buf = ["#" * int(tag[1]) + " "]
        elif tag == "blockquote":
            self.buf = ["> "]
        elif tag == "p":
            self.buf = []
        elif tag == "br":
            self.buf.append("\n")
        elif tag == "code" and not self.pre:
            self.buf.append("`")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg", "noscript", "time"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or self.stop:
            return
        if tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.parts.append("```")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = self._flush()
            norm = re.sub(r"\s+", " ", text).strip("#-* ").lower()
            if norm in FOOTER_HEADINGS:
                self.stop = True
                return
            if text:
                self.parts.append(text)
        elif tag in ("p", "blockquote", "li"):
            text = self._flush()
            if text:
                self.parts.append(text)
        elif tag == "code" and not self.pre:
            self.buf.append("`")

    def handle_data(self, data):
        if not self.skip and not self.stop:
            self.buf.append(data)


def html_to_markdown(page_html: str) -> str:
    """Pull the <article> body out of a full page and return Markdown text."""
    m = re.search(r"<article[^>]*>.*?</article>", page_html, re.S)
    article = m.group(0) if m else page_html
    parser = ArticleToMarkdown()
    parser.feed(article)
    lines = [ln.rstrip() for ln in parser.parts if ln.strip()]
    return "\n".join(lines).strip()


def slug_from_url(url: str) -> str:
    """https://ebpf.io/blog/cloudflare-replatforming-1/ -> cloudflare-replatforming-1"""
    return url.rstrip("/").split("/")[-1]


def download_post(url: str) -> Path:
    """Fetch one post, extract it, save Markdown. Returns the output path."""
    IN.mkdir(exist_ok=True)
    dst = IN / (slug_from_url(url) + ".md")
    if dst.exists():
        print(f"skip  {url}  (already downloaded)")
        return dst

    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    md = html_to_markdown(r.text)
    dst.write_text(md + "\n", encoding="utf-8")
    print(f"wrote {dst.name}  ({len(md)} chars)")
    return dst


# --------------------------------------------------------------------------
# Stage 2: clean -> narration (same shape as clean.py)
# --------------------------------------------------------------------------

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
    """Send one section of Markdown to the LLM, get back spoken prose."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(URL, json={
                "model": MODEL,
                "system": SYSTEM,
                "prompt": text,
                "stream": False,
                "think": False,   # disable the model's reasoning phase
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


def split_article(md: str) -> list[str]:
    """Split an article on '## ' and '### ' headings, keeping each with its body."""
    return [p.strip() for p in re.split(r"(?m)^(?=#{2,3} )", md) if p.strip()]


def clean_file(src: Path) -> None:
    """Clean one downloaded Markdown file into narration text."""
    OUT.mkdir(exist_ok=True)
    dst = OUT / (src.stem + ".txt")
    if dst.exists():
        print(f"skip  {src.name}  (already cleaned)")
        return

    sections = split_article(src.read_text(encoding="utf-8"))
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


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    do_download = "--clean-only" not in args
    do_clean = "--download-only" not in args
    needle = next((a for a in args if not a.startswith("--")), None)

    if do_download:
        posts = POSTS if needle is None else [p for p in POSTS if needle in p]
        for url in posts:
            download_post(url)

    if do_clean:
        files = sorted(IN.glob("*.md"))
        if needle is not None:
            files = [f for f in files if needle in f.stem]
        for src in files:
            clean_file(src)


if __name__ == "__main__":
    main()
