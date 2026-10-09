# tts_local_workflow

Turn long-form documents (books, blog posts, papers, wiki pages) into spoken
narration and audio — using only local models: **Ollama** for the text rewrite
(Stage 2), **Kokoro** for the voice (Stage 3).

```bash
.venv/bin/python run.py <corpus-name> --format opus
```

## Layout

```
run.py            # batch entry point: extract -> clean -> eval -> synth -> compress
pipeline/         # shared, document-agnostic stage code
  clean.py        #   Stage 2:   LLM rewrite (Markdown -> narration)
  eval.py         #   Stage 2.5: QA gate
  synth.py        #   Stage 3:   narration -> WAV (Kokoro)
  convert.py      #   Stage 3.5: WAV -> opus/mp3 (ffmpeg)
  prep.py         #   Stage 1:   generate a recipe from PREP.md
  say.py          #   one-off single-file TTS
recipes/          # per-document scripts (the only document-specific code)
prompts/          # editing prompts (cleanup_prompt.txt + per-doc extensions)
docs/             # notes (Kokoro usage, historical design drafts)
.agents/          # cross-agent skill: how to operate the repo
corpus/           # GITIGNORED — sources, extracted text, audio
```

- **Docs** — `AGENTS.md` (agent instructions), `PREP.md` (recipe-generation spec).
- **Operational guide** — `.agents/skills/document-to-audio/SKILL.md`.

## Licensing

`corpus/` and `*.pdf` are gitignored: they hold third-party sources and derived
audio. Only convert sources you have the right to make a derivative work from
(CC BY / CC BY-SA / CC0, Apache-2.0 project docs, your own writing) — not
all-rights-reserved material.
