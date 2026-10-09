"""The document-to-audio pipeline: shared, document-agnostic stage code.

Modules are named after the pipeline stages they implement:

- ``prep.py``    — Stage 1:   generate a recipe from a sample + PREP.md
- ``clean.py``   — Stage 2:   LLM rewrite of Markdown into spoken narration
- ``eval.py``    — Stage 2.5: QA gate (Markdown residue, word-count drift, …)
- ``synth.py``   — Stage 3:   narration text → WAV (Kokoro)
- ``convert.py`` — Stage 3.5: WAV → compressed audio (ffmpeg)
- ``say.py``     — one-off:   a single text file → a single WAV

Per-document logic lives in ``recipes/{name}.py``, which imports ``clean`` from
here. Nothing in this package is document-specific.
"""
