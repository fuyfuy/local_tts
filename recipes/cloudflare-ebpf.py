"""Download + clean the Cloudflare eBPF blog series (Stage 0 + Stage 2).

Document-specific logic: the list of posts, the HTML -> Markdown extractor
(Stage 0), and the heading-level split (Stage 2). LLM plumbing comes from
``tts.llm``.

Usage (from the repo root):
    python recipes/cloudflare-ebpf.py               # download + clean
    python recipes/cloudflare-ebpf.py --download-only
    python recipes/cloudflare-ebpf.py --clean-only
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]   # repo root
sys.path.insert(0, str(ROOT))

from tts import llm

NAME = "cloudflare-ebpf"
RAW_DIR = ROOT / "corpus" / NAME / "raw"          # stage 0 output (extracted Markdown)
CLEAN_DIR = ROOT / "corpus" / NAME / "clean"      # stage 2 output (narration)
PROMPT = (ROOT / "cleanup_prompt.txt").read_text(encoding="utf-8").strip()

POSTS = [
    "https://ebpf.io/blog/cloudflare-replatforming-1/",
    "https://ebpf.io/blog/cloudflare-replatforming-2/",
    "https://ebpf.io/blog/cloudflare-replatforming-3/",
]

# Headings whose text means "end of the real article" (site footer noise).
FOOTER_HEADINGS = {"share on social media:", "subscribe to bi-weekly echo news"}


# --------------------------------------------------------------------------
# Stage 0: HTML -> Markdown (stdlib only, no dependencies)
# --------------------------------------------------------------------------

class ArticleToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.buf = []
        self.skip = 0        # inside a tag we ignore
        self.pre = 0         # inside <pre>
        self.stop = False    # reached the footer

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
    m = re.search(r"<article[^>]*>.*?</article>", page_html, re.S)
    article = m.group(0) if m else page_html
    parser = ArticleToMarkdown()
    parser.feed(article)
    lines = [ln.rstrip() for ln in parser.parts if ln.strip()]
    return "\n".join(lines).strip()


def slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def download_post(url: str) -> None:
    RAW_DIR.mkdir(exist_ok=True)
    dst = RAW_DIR / (slug_from_url(url) + ".md")
    if dst.exists():
        print(f"skip  {url}  (already downloaded)")
        return
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    md = html_to_markdown(r.text)
    dst.write_text(md + "\n", encoding="utf-8")
    print(f"wrote {dst.name}  ({len(md)} chars)")


# --------------------------------------------------------------------------
# Stage 2
# --------------------------------------------------------------------------

def split(md: str) -> list[str]:
    """Blog: split on '## ' and '### ' headings."""
    return [p.strip() for p in re.split(r"(?m)^(?=#{2,3} )", md) if p.strip()]


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
        CLEAN_DIR.mkdir(exist_ok=True)
        files = sorted(RAW_DIR.glob("*.md"))
        if needle is not None:
            files = [f for f in files if needle in f.stem]
        for src in files:
            llm.clean_file(src, CLEAN_DIR / (src.stem + ".txt"), split, PROMPT)


if __name__ == "__main__":
    main()
