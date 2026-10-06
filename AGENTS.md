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

## Keep skills up to date — do it proactively, don't wait to be asked

Skills are the operational memory of a project. Whenever we implement
something new, change how a stage works, hit a bug and fix it, add a command
or flag, or learn anything else that would matter to a future agent, update the
relevant skill **immediately and without being prompted**.

For this repo that means `.claude/skills/document-to-audio/SKILL.md` — and
`PREP.md` if the change affects how a new per-document script is generated.

This is a general rule, not specific to this project: in *any* session where a
skill is loaded for the project you're working on, treat that skill as a live
document and keep it current as part of the work itself. The skill should never
be allowed to drift stale behind the code — the moment the code and the skill
disagree, a future agent (or future me) will trust the skill and make mistakes.
