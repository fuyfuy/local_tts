import re
import sys
import time
from pathlib import Path
from threading import Thread

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

# Model to run IN PYTORCH. Swap freely:
#   "Qwen/Qwen2.5-7B-Instruct"      (default, ~15 GB download, ~4.5 GB VRAM @ 4-bit)
#   "Qwen/Qwen3-8B"                 (the HF twin of Ollama's qwen3:8b)
#   "Qwen/Qwen2.5-1.5B-Instruct"    (~3 GB download — use for fast profiling loops)
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

IN  = Path("out")
OUT = Path("clean_torch")   # separate from clean/ so you can diff against Ollama
OUT.mkdir(exist_ok=True)

SYSTEM = Path("cleanup_prompt.txt").read_text(encoding="utf-8").strip()

TEMP           = 0.2
MAX_NEW_TOKENS = 2048
PROFILE        = "--profile" in sys.argv    # enable torch.profiler
LOG_DIR        = Path("prof_logs")

print(f"loading {MODEL_ID} ...", flush=True)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    load_in_4bit=True,                       # bitsandbytes 4-bit, fits 8 GB
    bnb_4bit_compute_dtype=torch.bfloat16,
)
model.eval()


def build_prompt(text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": text},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def clean_chunk(text: str) -> str:
    prompt = build_prompt(text)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    n_in = inputs["input_ids"].shape[1]     # prefill length = prompt tokens

    if PROFILE:
        LOG_DIR.mkdir(exist_ok=True)
        with torch.profiler.profile(
            activities=[torch.profiler.ProfilerActivity.CPU,
                        torch.profiler.ProfilerActivity.CUDA],
            on_trace_ready=torch.profiler.tensorboard_trace_handler(str(LOG_DIR)),
            record_shapes=True,
            profile_memory=True,
            with_stack=True,
        ) as prof:
            t0 = time.time()
            out = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS,
                                 temperature=TEMP, do_sample=True)
        wall = time.time() - t0
        print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=20))
        return tokenizer.decode(out[0][n_in:], skip_special_tokens=True).strip()

    # Normal mode: stream tokens so we can measure time-to-first-token and rate.
    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
    gen_kwargs = dict(**inputs, max_new_tokens=MAX_NEW_TOKENS,
                      temperature=TEMP, do_sample=True, streamer=streamer)
    result = {}
    def _run():
        result["ids"] = model.generate(**gen_kwargs)
    thread = Thread(target=_run)
    thread.start()

    t0 = time.time()
    parts, ttft = [], None
    for tok in streamer:
        if ttft is None:
            ttft = time.time() - t0
        parts.append(tok)
    thread.join()
    wall = time.time() - t0

    n_out = result["ids"].shape[1] - n_in   # decode length = generated tokens
    decode_t = max(wall - ttft, 1e-6)
    print(f"    prefill={n_in} tok | ttft={ttft:.2f}s | "
          f"decode={n_out} tok in {decode_t:.2f}s ({n_out/decode_t:.1f} tok/s)")
    return "".join(parts).strip()


def split_chapter(md: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?m)^(?=## )", md) if p.strip()]


def main():
    files = sorted(IN.glob("*.md"))
    if len(sys.argv) > 1 and sys.argv[1] != "--profile":
        files = [f for f in files if sys.argv[1] in f.stem]

    for src in files:
        dst = OUT / (src.stem + ".txt")
        if dst.exists():
            print(f"skip  {src.name}  (already cleaned)")
            continue
        sections = split_chapter(src.read_text(encoding="utf-8"))
        cleaned = []
        for i, sec in enumerate(sections):
            print(f"  [{src.name}] section {i+1}/{len(sections)} ({len(sec)} chars)", flush=True)
            try:
                cleaned.append(clean_chunk(sec))
            except Exception as e:
                print(f"    !! failed: {e} -- keeping raw section", flush=True)
                cleaned.append(f"[CLEANUP FAILED]\n\n{sec}")
        dst.write_text("\n\n".join(cleaned), encoding="utf-8")
        print(f"wrote {dst.name}  ({len(sections)} sections)")


if __name__ == "__main__":
    main()
