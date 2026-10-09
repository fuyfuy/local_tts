"""Stage 1 (Prepare) runner.

Builds a prompt from PREP.md + a sample of a new document, and asks a model
(local Ollama by default) to produce ``recipes/{name}.py`` (+ ``prompt_{name}.txt``
if needed) plus a short plan.

Usage (from the repo root):
    python pipeline/prep.py path/to/doc.md --name my-book            # call local model
    python pipeline/prep.py path/to/doc.md --name my-book --print    # just print the prompt
    python pipeline/prep.py path/to/doc.html --name my-blog --model qwen3:8b
"""

import argparse
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PREP = (ROOT / "PREP.md").read_text(encoding="utf-8")

MODEL = "qwen3.5:9b"
URL = "http://localhost:11434/api/generate"


def sample_text(path: Path, first: int, middle: int) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) <= first + middle:
        return text
    mid = len(lines) // 2
    head = "\n".join(lines[:first])
    body = "\n".join(lines[mid:mid + middle])
    omitted = len(lines) - first - middle
    return f"{head}\n\n... [ {omitted} lines omitted ] ...\n\n{body}"


def build_prompt(name: str, sample: str) -> str:
    return f"""Here is the pipeline playbook:

<BEGIN PREP>
{PREP}
<END PREP>

Here is a sample of my document:

<BEGIN SAMPLE>
{sample}
<END SAMPLE>

Run Stage 1 (Prepare). Inspect the structure and tell me:
1. which heading levels are section boundaries,
2. what noise to strip and where,
3. which special content appears (code/tables/equations/figures),
4. the max chunk size you'd target,
5. whether a tailored prompt is needed and what it should say.

Then give a 5-10 line plan first, and write recipes/{name}.py as a single
```python code block```. Import helpers with `from pipeline import clean` and make
`split()` the only document-specific logic. Write prompt_{name}.txt only if the
default prompt needs extending.
"""


def extract_code_block(text: str) -> str | None:
    m = re.search(r"```python\s*\n(.*?)```", text, re.S)
    return m.group(1) if m else None


def call_llm(prompt: str, model: str) -> str:
    r = requests.post(URL, json={
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,   # never let the prep model burn its context on reasoning
        "options": {"num_ctx": 32768, "temperature": 0.2},
    }, timeout=1200)
    r.raise_for_status()
    data = r.json()
    if data.get("done_reason") == "length":
        print("WARNING: response truncated (hit context limit)", file=sys.stderr)
    return data["response"]


def main():
    ap = argparse.ArgumentParser(description="Run Stage 1 (Prepare) on a document sample.")
    ap.add_argument("sample", help="path to a document sample (.md/.html/.txt)")
    ap.add_argument("--name", required=True, help="slug, e.g. my-book")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--first", type=int, default=200, help="lines from the top")
    ap.add_argument("--middle", type=int, default=200, help="lines from the middle")
    ap.add_argument("--print", action="store_true",
                    help="print the prompt instead of calling the model")
    args = ap.parse_args()

    sample = sample_text(Path(args.sample), args.first, args.middle)
    prompt = build_prompt(args.name, sample)

    if args.print:
        print(prompt)
        return

    print(f"calling {args.model} ...", file=sys.stderr, flush=True)
    response = call_llm(prompt, model=args.model)
    print(response)

    code = extract_code_block(response)
    if code:
        dst = ROOT / "recipes" / f"{args.name}.py"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(code + "\n", encoding="utf-8")
        print(f"\n[saved] {dst}", file=sys.stderr)
    else:
        print("\n[no ```python block found; save manually]", file=sys.stderr)


if __name__ == "__main__":
    main()
