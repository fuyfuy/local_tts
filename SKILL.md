# Local TTS Workflow — Agent Skill

Load this whenever you need to operate, extend, or debug the local
document-to-audio pipeline. It is the operational companion to `PREP.md`
(which is the spec you feed a model to *generate* a new `clean_{name}.py`).
This file tells you how to *run* and *maintain* the whole thing.

---

## 1. What this repo does

Turns a long-form technical document (book, blog series, paper, transcript)
into spoken narration, then audio, using only local models (Ollama for the
text rewrite, Kokoro for the voice).

```
original format -> Markdown -> narration text -> audio
  (stage 0)        (stage 1)    (stage 2)        (stage 3)
```

- Stage 0 **Extract** — deterministic: PDF/HTML -> Markdown per chapter/post.
- Stage 1 **Prepare** — a model inspects a sample and writes `clean_{name}.py`.
- Stage 2 **Clean** — the LLM rewrites each Markdown section into spoken prose.
- Stage 3 **Synthesize** — Kokoro turns narration `.txt` into `.wav`.

The LLM's *only* job is Stage 2. Everything else is plumbing.

---

## 2. Repo layout

```
tts_local_workflow/
├── PREP.md                       # spec for the Stage-1 (prepare) model
├── SKILL.md                      # this file
├── cleanup_prompt.txt            # DEFAULT editing prompt (shared fallback)
├── requirements.txt
├── run.py                        # batch: extract -> clean -> synth -> compress
├── prep.py                       # Stage 1 runner (builds PREP.md + sample -> model)
├── eval.py                       # QA checker (flags leftover Markdown, page numbers, etc.)
├── tts/
│   ├── llm.py                    # shared clean_chunk / print_timings / clean_file
│   ├── tts.py                    # Stage 3: whole corpus clean/ -> audio/ (Kokoro)
│   ├── say.py                    # Stage 3: one file -> one .wav (Kokoro)
│   └── convert.py                # Stage 3.5: .wav -> .mp3/.opus/.ogg/.m4a (ffmpeg)
├── corpus/                       # gitignored — local sources/data + per-doc scripts
│   └── {name}/                   #   raw/ clean/ audio/ + clean_{name}.py
└── legacy/                       # superseded flat scripts (clean.py, clean_blog.py, ...)
```

Rules:
- `tts/` is document-agnostic. Never put document-specific logic there.
- `corpus/{name}/clean_{name}.py` is **generated**, and `split()` is the *only*
  document-specific function in it. Everything else comes from `tts.llm`.
- `corpus/` is gitignored entirely — it holds source PDFs and derived text
  whose licensing we don't want to audit per commit. It is local-only and
  regenerable; never `git add` it.

---

## 3. The four stages, in commands

### Stage 0 — Extract

Book (PDF, uses pymupdf4llm):

```bash
.venv/bin/python corpus/inference-engineering/extract_inference-engineering.py
# writes corpus/inference-engineering/raw/00_preface.md, 01_chapter-..., etc.
```

Blog (HTML): download + extract lives inside the clean script —

```bash
.venv/bin/python corpus/cloudflare-ebpf/clean_cloudflare-ebpf.py --download-only
```

### Stage 1 — Prepare (only for a NEW document)

```bash
# print the prompt to paste into a hosted model (Claude/GPT):
.venv/bin/python prep.py path/to/doc.md --name my-book --print

# or run it against the local Ollama model:
.venv/bin/python prep.py path/to/doc.md --name my-book --model qwen3.5:9b
```

The model must decide 5 things (see PREP.md §4): heading levels to split on,
noise to strip, special content present, max chunk size, terminology. It
writes `corpus/{name}/clean_{name}.py` (+ `prompt_{name}.txt` only if needed)
and a short plan. **Review the plan before running.**

### Stage 2 — Clean

```bash
.venv/bin/python corpus/inference-engineering/clean_inference-engineering.py          # all chapters
.venv/bin/python corpus/inference-engineering/clean_inference-engineering.py 06       # one chapter
.venv/bin/python corpus/cloudflare-ebpf/clean_cloudflare-ebpf.py                     # download + clean
.venv/bin/python corpus/cloudflare-ebpf/clean_cloudflare-ebpf.py --clean-only
```

Reads `raw/*.md`, writes `clean/*.txt`. Idempotent (skips existing outputs).

### Stage 3 — Synthesize + compress

```bash
.venv/bin/python tts/tts.py corpus/inference-engineering
# reads corpus/.../clean/*.txt -> corpus/.../audio/*.wav (24 kHz mono)

.venv/bin/python tts/convert.py corpus/inference-engineering/audio              # -> .mp3 64k (deletes wav)
.venv/bin/python tts/convert.py corpus/inference-engineering/audio --format opus --bitrate 48k
```

Compression needs `ffmpeg` (`sudo apt install ffmpeg`). **Opus 48k mono** is
best quality/size for speech; **MP3 64k** is the universal-compatibility
fallback (the default). ~10 h of book ≈ 1.7 GB WAV → ~290 MB MP3 → ~215 MB Opus.

### One command for the whole pipeline

```bash
.venv/bin/python run.py inference-engineering                        # extract -> clean -> wav -> mp3
.venv/bin/python run.py inference-engineering --format opus --bitrate 48k
.venv/bin/python run.py inference-engineering --skip-extract --skip-clean
```

Every stage is idempotent, so re-running only does the missing work.

---

## 4. Hard-won gotchas (READ BEFORE TOUCHING THE LLM CODE)

1. **`"think": False` must be at the TOP LEVEL of the request JSON**, not inside
   `options`. Thinking-capable models (qwen3.5:9b) otherwise burn the context
   window on a hidden reasoning preamble and return **empty** or truncated
   `response`. This was the #1 bug we hit.
2. **`done_reason == "length"` = truncation = an error.** Raise, so the section
   falls back to a `[CLEANUP FAILED]` marker + raw text instead of silently
   dropping content.
3. **Ollama 0.34+ returns timings at the top level**, not under a `"timings"`
   key (which is now `null`). `print_timings()` reads the top-level fields.
4. **Chunk vs `num_ctx`.** The narration output is ~the same size as the input,
   and thinking (if on) roughly doubles the budget. Keep sections small enough
   that prompt + response fit in `num_ctx` (8192 default). ~8k chars/section is
   a safe ceiling.
5. **Split on `## ` AND `### `** (`#{2,3} `), or sub-sections get folded into
   one paragraph and lose their spoken heading ("five point one point three").
6. **Strip footer noise structurally** (at extraction time) when you can —
   running headers, page numbers, bylines, "Share on social media",
   "Subscribe to …", dates. Only handle it in the prompt as a last resort.
7. **Idempotency + retry with backoff** are non-negotiable. Keep `raw/`
   immutable so re-cleaning is always possible.

---

## 5. Adding a new document (the full recipe)

1. Put a sample of the source where the model can see it (a `.md`/`.html`/`.txt`).
2. Run Stage 1:
   `python prep.py sample.md --name my-doc --print` → paste into Claude, or
   `python prep.py sample.md --name my-doc` → local Ollama.
3. Review the plan + the generated `corpus/my-doc/clean_my-doc.py`. Check the
   split regex and the noise-stripping match your document's actual structure.
4. If the doc needs extraction, add `extract_my-doc.py` (or a `--download-only`
   mode, as in the blog script) that writes Markdown into `corpus/my-doc/raw/`.
5. Run `python corpus/my-doc/clean_my-doc.py` and eyeball one output section.
6. Run `python eval.py` (or a tailored check) to catch leftover Markdown/page
   numbers/dangling lines.
7. Synthesize + compress: `python run.py my-doc` (or `python tts/tts.py corpus/my-doc` for WAV only).

---

## 6. Running TTS on a single file

Install once:

```bash
.venv/bin/pip install "kokoro>=0.9.4" soundfile
```

Then, one file — use `tts/say.py`:

```bash
.venv/bin/python tts/say.py corpus/inference-engineering/clean/06_chapter-5-techniques.txt
.venv/bin/python tts/say.py some.txt --voice af_nova --speed 1.1 --out /tmp/x.wav
```

Writes a 24 kHz mono `.wav` next to the input (`--out` overrides). Knobs:
`--voice` (`af_heart`, `af_nova`, `am_michael`, `bf_emma`, `bm_george`),
`--speed` (0.9–1.1), `--lang` (`a`=American, `b`=British). Internally it is just
`KPipeline(lang_code=...)` fed with `split_pattern=r"\n+"` (cut on paragraph breaks).

---

## 7. Model selection

Two separate runners — don't conflate them: **Ollama** runs LLMs (text→text,
plus vision and embeddings) over HTTP at `:11434`; **Kokoro** is a pip-installed
PyTorch library (text→audio) with no server. There is no TTS model in
`ollama list` — audio generation never goes through Ollama.

- **Stage 2 (rewrite) LLM** — local `qwen3.5:9b` (or any Ollama model). A
  capable small model is fine; faithfulness matters (numbers/terms must
  survive). Disable thinking (`think:False`).
- **Stage 3 (voice)** — **Kokoro** (~82M params, Apache-2.0) is the pragmatic
  default: tiny, fast on CPU, decent prosody, 24 kHz, many voices. Piper is
  lighter but worse; Qwen3-TTS / Chatterbox / NeuTTS are heavier zero-shot
  voice-cloners — only for a specific cloned voice.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Section is empty / blank in `clean/*.txt` | thinking model filled context before answering | `"think": False` (top level) |
| Section ends mid-sentence, rest missing | hit `num_ctx` limit (`done_reason:"length"`) | smaller chunks / split on `###` / raise on `length` |
| Sub-chapters folded into one paragraph | split only on `## ` | split on `#{2,3} ` |
| No timing lines printed | Ollama 0.34+ moved timings to top level | read top-level fields, not `data["timings"]` |
| `skip ... (already cleaned)` but want redo | output exists | delete the `clean/*.txt` and re-run |
| Kokoro mispronounces a term ("matmul", "LoRA") | grapheme-to-phoneme guessed wrong | spell it out in the cleaned text ("matrix multiply", "low-rank adaptation") |
| `python prep.py` truncates | prompt too big for local model | `--first`/`--middle` smaller, or use a hosted model |

---

## 9. Cost reference (cloud model for Stage 2)

For the 259-page book: ~62k tokens source + ~87k system-prompt overhead =
~150k input, ~62k output. Frontier model (Claude Sonnet/GPT-4o) ≈ **$1–1.50**;
budget model (mini/Haiku) ≈ **$0.10–0.50**. Output dominates (billed ~5× input).
Prompt caching trims the repeated system prompt. Avoid reasoning models — 3–10×
the cost, no benefit for this mechanical rewrite. TTS is free/local.
