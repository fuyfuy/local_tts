---
name: document-to-audio
description: Turn any long-form document (book, blog series, paper, transcript) into spoken narration and audio files. Use this skill to (1) understand the repo's components, (2) run the pipeline on an existing document, or (3) bootstrap a new document with a bespoke cleanup script via the clean→eval→adjust loop. Local models by default (Ollama for the rewrite, Kokoro for the voice); cloud models supported.
---

# Document → Audio Pipeline

Turns a long-form document into spoken narration, then audio. Two models do
the heavy lifting, and both are swappable:

- **Rewrite (text → text)** — a local Ollama model by default (`qwen3.5:9b`),
  or any cloud model. Rewrites extracted Markdown into prose that reads well aloud.
- **Voice (text → audio)** — **Kokoro** by default (tiny, local, Apache-2.0),
  or any other TTS engine (Piper, Qwen3-TTS, Chatterbox, …).

Everything else in the repo is deterministic plumbing around those two models.
This skill is the entrypoint for operating the repo and for delegating a new
document to an agent.

---

## 1. Component map

| Path | Role | Per-document? |
|------|------|---------------|
| `run.py` | batch entry point: extract → clean → eval → synth → compress | no |
| `pipeline/prep.py` | Stage 1: feed a sample + `PREP.md` to a model to *generate* a cleanup script | no |
| `pipeline/eval.py` | QA gate: flags leftover Markdown, page numbers, dangling lines, word-count drift | no |
| `prompts/cleanup_prompt.txt` | default editing prompt shared by all cleanup scripts | no |
| `PREP.md` | the spec handed to the model that writes a new cleanup script | no |
| `recipes/{name}.py` | the bespoke cleanup script (Stage 2) — the **only** per-document code | **yes** |
| `recipes/{name}-extract.py` | optional: PDF/HTML → Markdown (Stage 0) | **yes** |
| `pipeline/clean.py` | Stage 2: shared LLM plumbing (`clean_chunk`, URL→speech, truncation guard, timings) | no |
| `pipeline/synth.py` | Stage 3: `clean/*.txt` → `audio/*.wav` (Kokoro) + a per-book file named after the document title | no |
| `pipeline/say.py` | Stage 3: one file → one `.wav` (Kokoro) | no |
| `pipeline/convert.py` | Stage 3.5: `.wav` → `.mp3`/`.opus`/`.ogg`/`.m4a` (ffmpeg) | no |
| `corpus/{name}/` | gitignored data: `raw/` (Markdown), `clean/` (narration), `audio/` | data |

Rules:

- `pipeline/` is document-agnostic — never put document-specific logic there.
- `recipes/{name}.py` is **generated**, never hand-written from scratch;
  `split()` is the *only* document-specific function. Everything else is
  imported from `pipeline.clean`.
- `corpus/` is fully gitignored — third-party sources and derived audio whose
  licensing we don't want to audit per commit. Never `git add` it.

---

## 2. Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt    # requests, pymupdf, kokoro, soundfile, imageio-ffmpeg

# rewrite model — Ollama running locally with a model pulled:
ollama pull qwen3.5:9b                        # or any other Ollama model

# compression: system ffmpeg, or the pip-installed static build (already in requirements)
sudo apt install ffmpeg                       # optional — imageio-ffmpeg is the fallback
```

Two independent models — don't conflate them:

- **Rewrite LLM** runs over Ollama's HTTP API at `:11434` (default), or a cloud
  endpoint (see §9).
- **TTS (Kokoro)** is a pip-installed PyTorch library — no server, and it never
  goes through Ollama. There is no TTS model in `ollama list`; audio generation
  never touches Ollama.

---

## 3. The pipeline

```
source -> Markdown -> narration -> audio
 stage 0   stage 2      stage 2    stage 3
(extract)  (clean)      (eval)     (synth + compress)
```

- **Stage 0 — Extract**: deterministic PDF/HTML → one Markdown file per chapter/post.
- **Stage 2 — Clean**: the LLM rewrites each Markdown section into spoken prose.
- **Stage 2.5 — Eval**: `pipeline/eval.py` sanity-checks the narration against the source.
- **Stage 3 — Synthesize**: Kokoro turns narration `.txt` into `.wav`, then ffmpeg compresses.
  `pipeline/synth.py` also concatenates every chapter's WAV (sorted order) into a single
  per-book file alongside the per-chapter files, so `pipeline/convert.py` produces one
  whole-document audio file per book. The file is named after the document — the
  title from `corpus/<name>/title.txt` (written by the recipe's `TITLE` constant),
  falling back to the corpus folder name — so each book's audio is identifiable
  instead of every book landing on the same `all_in_one`.

The LLM's *only* job is Stage 2 (clean). Stages 0, 2.5, and 3 are deterministic.

---

## 4. Running an existing document

```bash
.venv/bin/python run.py rocksdb-tuning-guide                          # download->clean->eval->synth->mp3
.venv/bin/python run.py rocksdb-tuning-guide --format opus --bitrate 48k
.venv/bin/python run.py rocksdb-tuning-guide --skip-extract --skip-clean   # synth + compress only
```

Flags: `--skip-extract`, `--skip-clean`, `--skip-synth`, `--skip-eval`,
`--strict-eval` (abort on any eval flag), `--format`, `--bitrate`, `--keep-wav`.

Every stage is idempotent, so re-running only does the missing work.

Single file (no corpus): `.venv/bin/python pipeline/say.py some.txt --voice af_nova --speed 1.1 --out /tmp/x.wav`

---

## 5. Adding a NEW document — the clean/eval loop (the main event)

For each new document you produce a **bespoke cleanup script** and refine it
until the eval gate passes. This loop is the heart of the pipeline.

**Licensing first.** Only convert sources you have the right to make a derivative
work from. Safe: Creative Commons (CC BY / CC BY-SA / CC0), Apache-2.0 project
documentation, your own writing. Not OK without explicit permission:
all-rights-reserved books/papers and anything marked "no portion may be
reproduced". Two books were dropped from the repo for exactly this reason.

1. **Get the source into `corpus/{name}/raw/`** as Markdown, one file per chapter/post.
   - PDF: write a `recipes/{name}-extract.py` using `pymupdf4llm` (see
     `recipes/rocksdb-extract.py`, which strips running headers, page:column
     markers, citation markers, and the REFERENCES bibliography structurally).
   - Extract the **whole book in one `pymupdf4llm` call**, then split chapters
     on the `#` headings. `pymupdf4llm` infers heading levels from font sizes,
     so per-page or per-chapter calls misclassify section headings (`##`) as `#`
     when a page has no larger heading to compare against.
   - HTML/blog: fetch + extract inside the cleanup script's `--download-only`
     mode (see `recipes/cloudflare-ebpf.py`).
   - GitHub wiki: fetch `https://raw.githubusercontent.com/wiki/<owner>/<repo>/<Page>.md`
     — it serves clean Markdown, so no HTML parsing (see
     `recipes/rocksdb-tuning-guide.py`, which lists 16 pages with a numeric
     filename prefix that sets the all-in-one reading order).

2. **Write the cleanup script `recipes/{name}.py`**, either way:
   - run Stage 1: `.venv/bin/python pipeline/prep.py sample.md --name my-doc --print`
     → paste the output into your agent/model, which writes the script from
     `PREP.md`'s contract; or
   - write it by hand: copy a reference script (§6) and change `split()`. The
     only document-specific decision is **which heading levels are section
     boundaries** (plus any document-specific noise to strip).

3. **Run the clean/eval loop until it converges:**

   ```bash
   .venv/bin/python recipes/my-doc.py          # clean raw/*.md -> clean/*.txt
   .venv/bin/python pipeline/eval.py my-doc             # QA gate
   ```

   - If eval flags anything (leftover Markdown, dangling line, word-count
     drift), **adjust `split()` or the prompt** and re-clean only the affected
     file — delete its `clean/*.txt` first, or pass the chapter needle.
   - Repeat until `0 check(s) flagged`.

4. **Synthesize + compress:**

   ```bash
   .venv/bin/python run.py my-doc --skip-extract --skip-clean --format opus
   ```

---

## 6. Reference cleanup scripts

Several documents have already gone through the loop — use them as templates:

| Script | Source | `split()` decision |
|--------|--------|--------------------|
| `recipes/cloudflare-ebpf.py` | blog series (HTML) | download + extract `<article>`, strip footer noise; split on `## ` and `### ` |
| `recipes/rocksdb.py` | 32-page ACM paper (PDF) | split on `## ` (no `###`); `rocksdb-extract.py` strips ACM running headers, `26:3` page:col markers, citation markers, REFERENCES |
| `recipes/rocksdb-tuning-guide.py` | GitHub wiki (16 pages, multi-page collection) | fetch raw Markdown from the wiki endpoint (no HTML parsing); numeric prefix sets reading order; split on `#{1,4} `; strips wiki links, images, bylines; `prompts/rocksdb-tuning-guide.txt` verbalizes code/config as prose |

---

## 7. What `pipeline/eval.py` checks (and its blind spots)

Per `clean/*.txt` file it flags:

| check | catches |
|-------|---------|
| `md_residue` | leftover `#`, `**`, backticks, tables, links, URLs |
| `orphan_numbers` | a line that is just a page number |
| `dangling_lines` | a line with no terminal punctuation (truncation) |
| `repeated_lines` | a running header not stripped (a line appearing ≥3×) |
| `word_ratio` | content lost or invented vs the raw source (band 0.85–1.20) |

`IGNORE_FILES` (in `pipeline/eval.py`) skips files like `recommended-reading`, where
URLs and loose formatting are legitimate content (bibliographies, etc.).

Known blind spots, observed on real runs:

- **Page numbers folded into prose.** A running header like `**212** Inference
  Glossary` sometimes gets verbalized as "Now: section two hundred sixteen."
  `orphan_numbers` only catches a number on its **own line** — once the model
  folds it into prose, it slips through. If this matters, add a check for
  "section <number>" artifacts, or tighten the prompt.
- **URLs.** The model verbalizes URLs non-deterministically, so `clean_chunk`
  now applies a deterministic backstop — `verbalize_urls()` in `pipeline/clean.py`
  rewrites any literal `https://…` left in a response to "domain dot com slash
  …" before the TTS sees it. It verbalizes URL punctuation (`.` `/` `-` `_` `#`
  `?` `=` `&`) and drops a bare `https`/`http` scheme word the model sometimes
  leaves behind. Make sure it preserves the trailing sentence punctuation (a URL
  at line-end must keep its closing period).
- **`md_residue` `#` false-positive on "C#".** The check matches any `#`, so
  the C# language (and F#) trips it. Not a real problem — ignore the flag.
- **`word_ratio` on terse content.** Glossaries, reference tables, and
  procedural appendices legitimately expand (terms/commands → prose) or
  condense (bibliographies) far outside the 0.85–1.20 band. Put those files in
  `IGNORE_FILES` rather than chasing the ratio.
- **`dangling_lines` on list intros.** A sentence ending in "namely:" (or a
  colon) before a bulleted list reads fine but is flagged. Cosmetic — ignore.

---

## 8. Hard-won gotchas (read before touching the LLM code)

1. **`"think": False` at the TOP LEVEL of the request JSON**, not inside
   `options`. Thinking-capable models (qwen3.5:9b) otherwise burn the context
   window on a hidden reasoning preamble and return **empty** or truncated
   responses. This was the #1 bug we hit.
2. **`done_reason == "length"` = truncation = an error.** Raise, so the section
   falls back to a `[CLEANUP FAILED]` marker + raw text instead of silently
   dropping content.
3. **Ollama 0.34+ returns timings at the top level**, not under a `"timings"`
   key (which is now `null`). `print_timings()` reads the top-level fields.
4. **Chunk vs `num_ctx`.** Narration output is ~the same size as the input, and
   thinking (if on) roughly doubles the budget. Keep sections ≤ ~8k chars so
   prompt + response fit in `num_ctx` (8192 default).
5. **Split on `## ` AND `### `** (`#{2,3} `), or sub-sections fold into one
   paragraph and lose their spoken heading ("five point one point three").
6. **Strip footer noise structurally at extraction time** when you can — running
   headers, page numbers, bylines, "Subscribe to …", dates. Only handle it in
   the prompt as a last resort.
7. **Idempotency + retry with backoff** are non-negotiable. Keep `raw/`
   immutable so re-cleaning is always possible.
8. **`pymupdf4llm` heading levels need whole-book context.** It sizes a heading
   against the other text on the same page, so per-page (or per-chapter)
   extraction misclassifies section headings (`##`) as `#`. Extract the whole
   document in one call, then split chapters on `#`.
9. **Code-heavy books need a prompt extension.** The default prompt's "read
   code line-by-line" makes some models dump raw code (dangling lines) or keep
   backticks around identifiers. For a code-heavy book, add a `prompts/{name}.txt`
   that says: describe each listing in prose, never reproduce code verbatim,
   never emit backticks.
10. **Never trust the model to drop page numbers/headers — strip them
    deterministically in `split()`.** When a running header/footer survives to
    Stage 2 (e.g. `Models **41**`, `4.4 NVIDIA Dynamo **111**`), the LLM will
    *narrate its own reasoning* about it ("the number forty-one ... should be
    omitted") instead of silently omitting it, and a footer carrying the *next*
    section's title gets verbalized as a duplicate heading. Strip these with
    regexes before the model sees them. If a chapter number lives only in a
    stripped `CHAPTER N` line, capture it and bake it back into the chapter-title
    heading, or the model latches onto "section 3.4" / "Figure 0.1" in the body
    and drops the opening sentences. Prefer this over a prompt instruction.
11. **Bare headings and unnumbered headings make the model invent content.**
    A heading with no body text (e.g. `## Possibilities of Performance
    Bottlenecks.` immediately followed by `### System Metrics`) gets a whole
    hallucinated paragraph; a document whose headings carry no numbers gets
    "section five point one"/"section two" invented at random. Add a prompt rule:
    "these headings are NOT numbered — never invent or speak a section number; if
    a heading has no body, just state it and move on." (`prompts/rocksdb-tuning-guide.txt`
    does both.)

---

## 9. Model selection

### Rewrite LLM (Stage 2)

- **Local (default)** — `qwen3.5:9b` via Ollama. Set `MODEL` in `pipeline/clean.py`
  (or per-recipe). Faithfulness matters (numbers/terms must survive); disable
  thinking (`"think": False`).
- **Cloud** — the LLM call lives in one place, `pipeline/clean.py` (`clean_chunk`), so
  switching to an OpenAI-compatible endpoint (Claude/GPT) means editing that
  single HTTP call. A frontier model gives the most faithful rewrite; a budget
  model is fine for this mechanical job. Avoid reasoning models — 3–10× the
  cost, no benefit.

### Voice (Stage 3)

- **Kokoro** (default) — ~82M params, Apache-2.0, fast on CPU, 24 kHz, many voices.
- Alternatives — Piper (lighter, worse); Qwen3-TTS / Chatterbox / NeuTTS
  (heavier zero-shot voice cloners — only for a specific cloned voice).

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Section empty/blank in `clean/*.txt` | thinking model filled context | `"think": False` (top level) |
| Section ends mid-sentence | hit `num_ctx` (`done_reason:"length"`) | smaller chunks / split on `###` / raise on `length` |
| Sub-chapters folded into one paragraph | split only on `## ` | split on `#{2,3} ` |
| No timing lines printed | Ollama 0.34+ moved timings top-level | read top-level fields, not `data["timings"]` |
| `skip ... (already cleaned)` but want redo | output exists | delete the `clean/*.txt` and re-run |
| Kokoro mispronounces a term ("matmul", "LoRA") | grapheme-to-phoneme guessed wrong | spell it out in the cleaned text |
| `pipeline/prep.py` truncates | prompt too big for local model | smaller sample, or a hosted model |
| `pipeline/synth.py` waits ~7 min before synthesizing | waiting for Ollama to flush its VRAM cache before committing to the GPU | let it wait; it falls back to CPU if VRAM is tight |

---

## 11. Cost reference (cloud model for Stage 2)

For the 259-page book: ~62k tokens source + ~87k system-prompt overhead =
~150k input, ~62k output. Frontier model (Claude Sonnet/GPT-4o) ≈ **$1–1.50**;
budget model (mini/Haiku) ≈ **$0.10–0.50**. Output dominates (billed ~5× input).
Prompt caching trims the repeated system prompt. TTS is free/local.

---

## 12. Push to GitHub after substantial changes

Treat the remote as the source of truth. After any **substantial change** — new
feature, bug fix, new document recipe, updated skill/`PREP.md`/`AGENTS.md`,
renamed or removed files — commit and push to GitHub. Do this as part of the
work, without being asked.

```bash
git add -A
git commit -m "<what changed and why>"
git push
```

Notes:

- `corpus/` is gitignored — `git add -A` won't stage it, so data (PDFs, raw
  text, audio) never leaves the machine. Nothing special to skip.
- Trivial in-progress edits (a typo, a half-written change) don't each need a
  push — but once the change is working and coherent, push it. Don't leave a
  working state uncommitted and unpushed.
