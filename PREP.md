# Document-to-Audio Pipeline — Playbook (PREP)

This file is the specification you hand to a model (a local one via Ollama, or a
hosted one) to **bootstrap the pipeline for a new document**. It describes the
whole process, the target folder layout, the rules that every generated script
must obey, and the contract the generated code must satisfy.

Nothing in here is per-document. The per-document decisions (heading levels,
noise to strip, chunk size, terminology) are made **per document** in Stage 1
below, by the model, from a sample of the document.

---

## 1. Goal

Take a long-form technical document — a book, a blog series, a paper, a
transcript — and turn it into spoken narration:

```
original format  ->  Markdown  ->  narration text  ->  audio
                    (stage 0)     (stage 2)          (stage 3)
```

The LLM's only job is **Stage 2**: rewrite Markdown into text that reads well
when spoken by a TTS engine. Everything else is deterministic plumbing.

---

## 2. The four stages

| Stage | Name      | Input                     | Output                        | Who does it       |
|-------|-----------|---------------------------|-------------------------------|-------------------|
| 0     | Extract   | PDF / HTML / docx         | clean Markdown, one file per chapter/post | deterministic script |
| 1     | Prepare   | Markdown sample + this doc| `recipes/{name}.py`, `prompt_{name}.txt`, a plan | **a model** |
| 2     | Clean     | Markdown sections         | narration `.txt` per chapter/post | LLM (`recipes/{name}.py`) |
| 3     | Synthesize| narration `.txt`          | `.wav`/`.mp3`                 | TTS helper |

Stage 0 and Stage 3 are format-specific plumbing. Stages 1–2 are where the
document-specific intelligence lives, and Stage 1 is what this playbook is for.

---

## 3. Target folder layout

```
tts_local_workflow/
├── .claude/skills/document-to-audio/SKILL.md   # the agent skill (how to operate the repo)
├── PREP.md                    # this playbook (fed to the prep model)
├── cleanup_prompt.txt         # DEFAULT editing prompt (fallback for all docs)
├── recipes/                   # per-document scripts — TRACKED, uploaded
│   └── {name}.py              #   the tailored clean script (stage 1 output)
├── tts/                       # shared, document-agnostic helpers
│   ├── llm.py                 #   clean_chunk(), print_timings(), truncation guard
│   └── tts.py                 #   narration text -> audio
└── corpus/                    # GITIGNORED — local data only
    └── {name}/                # one folder per document/source
        ├── raw/               # stage 0 output: extracted Markdown (.md)
        ├── clean/             # stage 2 output: narration (.txt)
        └── audio/             # stage 3 output: final audio
```

Rules:

- `{name}` is a short slug: `inference-engineering`, `cloudflare-ebpf`,
  `attention-is-all-you-need`.
- `recipes/{name}.py` is **generated**, never hand-written from scratch. It
  imports the shared helpers from `tts/` and only encodes the decisions that
  are specific to this document. It is committed; `corpus/` (data) is not.
- `prompt_{name}.txt` is optional. Omit it when the default
  `cleanup_prompt.txt` is adequate; create it only to add document-specific
  terminology or pronunciation rules.
- `raw/` is treated as immutable source. Cleaning is idempotent and cheap to
  re-run, so you can always regenerate `clean/` and `audio/` without touching
  Stage 0.

---

## 4. Stage 1 (Prepare) — what the model must do

**Inputs:** this playbook + a representative sample of the document (ideally
the first 200 lines plus one "middle" chapter/post, so the model sees both the
front-matter noise and the body structure).

**Outputs:**

1. `recipes/{name}.py` — the tailored script.
2. `prompt_{name}.txt` — only if the default prompt needs extending.
3. A short **plan** (5–10 lines) explaining the decisions, so a human can
   review before anything runs.

**The model must decide and document these five things:**

1. **Section hierarchy.** Which heading levels are "sections" (own LLM call,
   own spoken heading) vs. just inline structure? Common cases:
   - Book: `## ` **and** `### ` (so `5.1`, `5.1.3` each get their own narration
     block). Splitting only on `## ` folds `###` sub-sections into one paragraph
     and loses the "five point one point three" heading.
   - Blog post: `## ` and `### `.
   - Flat article (no headings): split on paragraph groups or hard char budget.
   - The `# ` title is almost never a split boundary by itself — it usually
     rides along with the intro as section 1.

2. **Noise to strip.** Running headers/footers, standalone page numbers,
   bylines ("By Cloudflare Engineering"), "Share on social media",
   "Subscribe to …", citation markers (`[1]`, `(2024)`, superscripts),
   hyphenation artifacts, navigation. Prefer filtering at **extraction time**
   (Stage 0); only handle in the prompt when it can't be done structurally.

3. **Special content.** Code blocks (should be read line-by-line), tables
   (summarize the takeaway, not cell-by-cell), equations (render in words),
   figure captions (keep only if informative). These rules already live in the
   default prompt — the model just needs to note which kinds actually appear
   so the prompt can be trimmed or extended.

4. **Chunk sizing.** Pick the split level(s) so no section exceeds ~2,000
   tokens of *input* (≈ 8,000 chars of English). The model's narration output
   is roughly input-sized, so input + output must stay well under `num_ctx`
   (default 8192). When a single heading's body is still too big, split it by
   paragraph budget or sub-divide further.

5. **Terminology / pronunciation.** Acronyms to keep as-is (GPU, CPU, RAM),
   ambiguous ones to spell out, symbols to verbalize (`->` → "leads to",
   `×` → "times"), and how section numbers are spoken ("five point one point
   three"). Goes into `prompt_{name}.txt` as an extension of the default
   prompt.

---

## 5. Hard-won rules (non-negotiable, bake into every generated script)

These are real failures we hit. A model that doesn't know them will reproduce
them.

1. **`"think": False`, at the top level of the request body** — *not* inside
   `options`. Ollama models with a "thinking" capability (e.g. `qwen3.5:9b`)
   burn most of the context on a hidden reasoning preamble. With `num_ctx`
   small, the model hits the context limit while still "thinking" and returns
   an **empty `response`** (the narration silently disappears) or a truncated
   one. Disabling thinking is the single most important fix.

2. **Treat `done_reason == "length"` as an error.** Ollama signals truncation
   this way. Raise, so the section falls back to a `[CLEANUP FAILED]` marker
   with the raw text instead of silently dropping content. Never write a
   truncated section as if it were complete.

3. **Timings are top-level in Ollama 0.34+.** `prompt_eval_duration`,
   `eval_duration`, `eval_count` etc. are fields of the response, not nested
   under a `"timings"` key (which is now `null`). Read them from the response
   dict directly.

4. **Chunk size vs `num_ctx`.** The response is ~the same size as the input,
   and thinking (if enabled) roughly doubles the budget. Keep input sections
   small enough that prompt + response comfortably fit in `num_ctx` (8192 by
   default). 8,000 chars per section is a safe ceiling; smaller is fine.

5. **Idempotency.** Skip any output file that already exists. This makes
   re-runs and retries cheap, and lets you regenerate one chapter without
   redoing the whole document.

6. **Retry with backoff.** Wrap the request in a short retry loop (2–3 tries,
   exponential sleep). Model servers hiccup.

7. **Keep `raw/` immutable.** Never mutate Stage 0 output; re-cleaning must
   always be possible from source.

8. **One shared `clean_chunk`.** Don't copy-paste the LLM plumbing into every
   generated script — import it from `tts/llm.py`. The generated script only
   encodes the document-specific `split()` and paths.

---

## 6. Contract: what `recipes/{name}.py` must expose

```python
NAME     = "{name}"                          # slug, matches the folder
RAW_DIR  = Path("corpus/{name}/raw")         # stage 0 input
CLEAN_DIR= Path("corpus/{name}/clean")       # stage 2 output
PROMPT   = "prompt_{name}.txt" or default    # editing instructions
MODEL    = "qwen3.5:9b"
URL      = "http://localhost:11434/api/generate"
TEMP     = 0.2
NUM_CTX  = 8192
TIMEOUT  = 600

def split(md: str) -> list[str]: ...         # document-specific (the ONLY tailored logic)
def main(): ...                              # CLI: [needle] [--clean-only] [--download-only]
```

`split()` is the one function that changes per document. It implements decision
#1 and #4 from Section 4. Everything else is imported from `tts/llm.py`.

CLI conventions (consistent across all generated scripts):

```
python recipes/{name}.py               # full run
python recipes/{name}.py 06            # only files matching "06"
python recipes/{name}.py --clean-only  # skip extraction (if the script extracts)
python recipes/{name}.py --download-only
```

---

## 7. Shared helpers (`tts/`)

**`tts/llm.py`** — the document-agnostic LLM plumbing:

```python
def clean_chunk(text, system, model=..., url=..., temp=..., num_ctx=...,
                timeout=...) -> str:
    # posts to /api/generate with "think": False at top level,
    # raises on done_reason == "length",
    # returns response.strip()
```

**`tts/tts.py`** — narration `.txt` → audio files (the Stage 3 helper).

**`cleanup_prompt.txt`** — the default editing prompt. It already encodes the
"remove Markdown noise / verbalize headings / read code line-by-line /
summarize tables / render equations in words" rules, and the standard
pronunciation hints. Per-document `prompt_{name}.txt` files **extend** it, they
don't replace it.

---

## 8. How to run the prep step

Paste this whole document plus a sample of the document into the model, then
ask it to run Stage 1:

```
Here is the pipeline playbook:

<BEGIN PREP.md> ... <END PREP.md>

Here is a sample of my document (first 200 lines and one middle chapter):

<BEGIN SAMPLE> ... <END SAMPLE>

Run Stage 1 (Prepare). Inspect the structure and tell me:
1. which heading levels are section boundaries,
2. what noise to strip and where,
3. which special content appears (code/tables/equations/figures),
4. the max chunk size you'd target,
5. whether a tailored prompt is needed and what it should say.

Then write `recipes/{name}.py` and (if needed) `prompt_{name}.txt`,
and give me a 5-10 line plan before I run anything.
```

The plan-first behavior matters: the model should **explain before it writes**,
so the human can catch mistakes (wrong heading level, missed footer noise) for
the cost of reading a few lines, not a full re-run.

---

## 9. Worked example (reference)

Two documents have already gone through this pipeline; use them as reference
implementations.

**A. Book — "Inference Engineering" (PDF).**
- Stage 0: PDF → Markdown per chapter (`06_chapter-5-techniques.md`).
- Structure: `##` sections with `###` sub-sections (`5.1`, `5.1.3`).
- Decision: split on **`## ` and `### `** (`#{2,3} `), so sub-chapters get
  their own spoken heading. Before this, sub-chapters were folded into one
  paragraph and `5.1.3` lost its heading.
- Noise: running headers (`CHAPTER 5`), page numbers (`Techniques **119**`).

**B. Blog — Cloudflare eBPF replatforming (HTML, ebpf.io).**
- Stage 0: fetch HTML → extract `<article>` → Markdown, stripping footer
  headings ("Share on social media", "Subscribe to eCHO News") and the date.
- Structure: `#` title + `##` sections + `###` subsections (part 3 only).
- Decision: split on `## ` and `### `; noise stripped structurally at
  extraction time.
- Same default prompt reused unchanged (the default prompt is generic enough).

Both hit the same class of bug — an empty/truncated section from the thinking
model — which is why rules #1–#3 in Section 5 exist.
