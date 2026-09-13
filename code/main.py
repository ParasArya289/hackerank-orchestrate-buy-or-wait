"""Entry point for the Buy or Wait? pipeline (AGENTS.md 6.6).

Runs the full pipeline over every request in dataset/requests.csv and
writes dataset/output.csv, overwriting any existing content.

Usage:
    python3 code/main.py
    python3 -m code.main

Requires a local Ollama server running with the qwen2.5vl (vision) and
gemma4 (text interpretation + explanation) models pulled:
    ollama pull qwen2.5vl
    ollama pull gemma4

No secrets are required. OLLAMA_HOST may optionally be set via
environment variable to point at a non-default Ollama host.
"""

from __future__ import annotations

import sys
import time

from code.output.writer import _verify_invariants, run_all_requests, write_output_csv


def main() -> None:
    t0 = time.time()
    total_holder = {"total": None}

    def progress(i: int, total: int, request_id: str, row: dict) -> None:
        total_holder["total"] = total
        if i % 10 == 0 or i == total:
            elapsed = time.time() - t0
            print(f"{i}/{total} done ({request_id}) elapsed={elapsed:.0f}s", flush=True)

    print("Starting full-dataset run over dataset/requests.csv ...", flush=True)
    rows = run_all_requests("dataset", progress_callback=progress)
    write_output_csv(rows, "dataset/output.csv")
    elapsed = time.time() - t0
    print(f"DONE: wrote {len(rows)} rows to dataset/output.csv in {elapsed:.0f}s", flush=True)

    _verify_invariants()


if __name__ == "__main__":
    sys.exit(main())
