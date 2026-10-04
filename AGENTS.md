# AGENTS.md

This repository implements a **local document-to-audio pipeline**: it turns a
long-form document (book, blog series, paper) into spoken narration, then audio,
using only local models — Ollama for the text rewrite, Kokoro for the voice.

- **Operational guide** (how to run / debug / extend): the skill at
  `.claude/skills/document-to-audio/SKILL.md`.
- **Spec for generating a new per-document script**: `PREP.md`.
- **Quick start**: `python run.py <corpus-name>` chains extract → clean →
  synthesize → compress. Data lives in gitignored `corpus/`; per-document
  scripts live in tracked `recipes/`.

When touching the LLM code, follow the hard-won rules from the skill — notably
`"think": False` at the top level of Ollama requests, and treating
`done_reason == "length"` as truncation rather than a valid result.
