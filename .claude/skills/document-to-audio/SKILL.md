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
| `run.py` | batch: extract → clean → eval → synth → compress | no |
| `prep.py` | Stage 1: feed a sample + `PREP.md` to a model to *generate* a cleanup script | no |
| `eval.py` | QA gate: flags leftover Markdown, page numbers, dangling lines, word-count drift | no |
| `cleanup_prompt.txt` | default editing prompt shared by all cleanup scripts | no |
| `PREP.md` | the spec handed to the model that writes a new cleanup script | no |
| `recipes/{name}.py` | the bespoke cleanup script (Stage 2) — the **only** per-document code | **yes** |
| `recipes/{name}-extract.py` | optional: PDF/HTML → Markdown (Stage 0) | **yes** |
| `tts/llm.py` | shared LLM plumbing (`clean_chunk`, truncation guard, timings) | no |
| `tts/tts.py` | Stage 3: `clean/*.txt` → `audio/*.wav` (Kokoro) | no |
| `tts/say.py` | Stage 3: one file → one `.wav` (Kokoro) | no |
| `tts/convert.py` | Stage 3.5: `.wav` → `.mp3`/`.opus`/`.ogg`/`.m4a` (ffmpeg) | no |
| `corpus/{name}/` | gitignored data: `raw/` (Markdown), `clean/` (narration), `audio/` | data |

Rules:

- `tts/` is document-agnostic — never put document-specific logic there.
- `recipes/{name}.py` is **generated**, never hand-written from scratch;
  `split()` is the *only* document-specific function. Everything else is
  imported from `tts.llm`.
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
- **Stage 2.5 — Eval**: `eval.py` sanity-checks the narration against the source.
- **Stage 3 — Synthesize**: Kokoro turns narration `.txt` into `.wav`, then ffmpeg compresses.

The LLM's *only* job is Stage 2 (clean). Stages 0, 2.5, and 3 are deterministic.

---

## 4. Running an existing document

```bash
.venv/bin/python run.py inference-engineering                          # extract->clean->eval->synth->mp3
.venv/bin/python run.py inference-engineering --format opus --bitrate 48k
.venv/bin/python run.py inference-engineering --skip-extract --skip-clean   # synth + compress only
```

Flags: `--skip-extract`, `--skip-clean`, `--skip-synth`, `--skip-eval`,
`--strict-eval` (abort on any eval flag), `--format`, `--bitrate`, `--keep-wav`.

Every stage is idempotent, so re-running only does the missing work.

Single file (no corpus): `.venv/bin/python tts/say.py some.txt --voice af_nova --speed 1.1 --out /tmp/x.wav`

---

## 5. Adding a NEW document — the clean/eval loop (the main event)

For each new document you produce a **bespoke cleanup script** and refine it
until the eval gate passes. This loop is the heart of the pipeline.

1. **Get the source into `corpus/{name}/raw/`** as Markdown, one file per chapter/post.
   - PDF: write a `recipes/{name}-extract.py` using `pymupdf4llm` (see
     `recipes/inference-engineering-extract.py`).
   - HTML/blog: fetch + extract inside the cleanup script's `--download-only`
     mode (see `recipes/cloudflare-ebpf.py`).

2. **Write the cleanup script `recipes/{name}.py`**, either way:
   - run Stage 1: `.venv/bin/python prep.py sample.md --name my-doc --print`
     → paste the output into your agent/model, which writes the script from
     `PREP.md`'s contract; or
   - write it by hand: copy a reference script (§6) and change `split()`. The
     only document-specific decision is **which heading levels are section
     boundaries** (plus any document-specific noise to strip).

3. **Run the clean/eval loop until it converges:**

   ```bash
   .venv/bin/python recipes/my-doc.py          # clean raw/*.md -> clean/*.txt
   .venv/bin/python eval.py my-doc             # QA gate
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

Two documents have already gone through the loop — use them as templates:

| Script | Source | `split()` decision |
|--------|--------|--------------------|
| `recipes/inference-engineering.py` | 259-page book (PDF) | split on `## ` **and** `### ` (`#{2,3} `) so `5.1`, `5.1.3` each get a spoken heading |
| `recipes/inference-engineering-extract.py` | same book | PDF → Markdown per chapter (`pymupdf4llm`) |
| `recipes/cloudflare-ebpf.py` | blog series (HTML) | download + extract `<article>`, strip footer noise; split on `## ` and `### ` |

---

## 7. What `eval.py` checks (and its blind spots)

Per `clean/*.txt` file it flags:

| check | catches |
|-------|---------|
| `md_residue` | leftover `#`, `**`, backticks, tables, links, URLs |
| `orphan_numbers` | a line that is just a page number |
| `dangling_lines` | a line with no terminal punctuation (truncation) |
| `repeated_lines` | a running header not stripped (a line appearing ≥3×) |
| `word_ratio` | content lost or invented vs the raw source (band 0.85–1.20) |

`IGNORE_FILES` (in `eval.py`) skips files like `recommended-reading`, where
URLs and loose formatting are legitimate content (bibliographies, etc.).

Known blind spots, observed on real runs:

- **Page numbers folded into prose.** A running header like `**212** Inference
  Glossary` sometimes gets verbalized as "Now: section two hundred sixteen."
  `orphan_numbers` only catches a number on its **own line** — once the model
  folds it into prose, it slips through. If this matters, add a check for
  "section <number>" artifacts, or tighten the prompt.
- **URLs.** The model verbalizes URLs non-deterministically (some chunks say
  "arxiv dot org slash abs slash …", others keep the literal `https://…`).
  The prompt asks for the spoken form, but a deterministic post-clean
  URL→speech transform is the *robust* fix if this matters (e.g. a bibliography).

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

---

## 9. Model selection

### Rewrite LLM (Stage 2)

- **Local (default)** — `qwen3.5:9b` via Ollama. Set `MODEL` in `tts/llm.py`
  (or per-recipe). Faithfulness matters (numbers/terms must survive); disable
  thinking (`"think": False`).
- **Cloud** — the LLM call lives in one place, `tts/llm.py` (`clean_chunk`), so
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
| `prep.py` truncates | prompt too big for local model | smaller sample, or a hosted model |
| `tts.py` waits ~7 min before synthesizing | waiting for Ollama to flush its VRAM cache before committing to the GPU | let it wait; it falls back to CPU if VRAM is tight |

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
