"""Generates evaluation/usage_report.md from a real OllamaClient usage_log
(AGENTS.md 6.5 / SUB-02).

Usage (after a full-dataset run has populated a client's usage_log in the
same Python process, e.g. inside code/main.py or a custom runner script):

    from code.evaluation.usage_report_gen import write_usage_report
    from code.llm.client import get_default_client

    write_usage_report(get_default_client().usage_log, num_requests=250)

This produces code/evaluation/usage_report.md summarizing model
providers/names, call counts per call_type, input/output tokens (sum +
per-call-type breakdown), total and average tokens per request, and an
explicit $0 cost estimate (local unauthenticated Ollama -- no billed API
calls, no API keys involved).

Can also be run standalone against a JSON dump of usage records (each
record: {"model": ..., "call_type": ..., "prompt_tokens": ...,
"completion_tokens": ..., "duration_seconds": ...}):

    python3 -m code.evaluation.usage_report_gen --json path/to/usage_log.json \
        --num-requests 250 --out code/evaluation/usage_report.md
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class _Record:
    model: str
    call_type: str
    prompt_tokens: int
    completion_tokens: int
    duration_seconds: float


def _records_from_usage_log(usage_log) -> list[_Record]:
    return [
        _Record(
            model=r.model,
            call_type=r.call_type,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            duration_seconds=r.duration_seconds,
        )
        for r in usage_log
    ]


def _records_from_json(path: str) -> list[_Record]:
    with open(path) as f:
        data = json.load(f)
    return [
        _Record(
            model=d["model"],
            call_type=d["call_type"],
            prompt_tokens=int(d["prompt_tokens"]),
            completion_tokens=int(d["completion_tokens"]),
            duration_seconds=float(d.get("duration_seconds", 0.0)),
        )
        for d in data
    ]


def build_report_markdown(
    records: list[_Record],
    num_requests: int,
    representative: bool = False,
    note: str | None = None,
) -> str:
    """Build the usage_report.md content as a string."""
    total_calls = len(records)
    total_prompt_tokens = sum(r.prompt_tokens for r in records)
    total_completion_tokens = sum(r.completion_tokens for r in records)
    total_tokens = total_prompt_tokens + total_completion_tokens

    by_model: dict[str, list[_Record]] = defaultdict(list)
    by_call_type: dict[str, list[_Record]] = defaultdict(list)
    for r in records:
        by_model[r.model].append(r)
        by_call_type[r.call_type].append(r)

    lines: list[str] = []
    lines.append("# Usage Report")
    lines.append("")
    lines.append(
        "Token usage and cost accounting for the full-dataset run of the Buy or "
        "Wait? pipeline (AGENTS.md 6.5, problem_statement.md \"Token Usage and Cost "
        "Analysis\")."
    )
    lines.append("")

    if representative:
        lines.append("> **NOTE: These are representative/partial numbers**, not the final ")
        lines.append("> full 250-request run. " + (note or ""))
        lines.append("")

    lines.append("## Model Providers and Names")
    lines.append("")
    lines.append("All models run **locally via Ollama** (unauthenticated local daemon, no API keys, no cloud provider).")
    lines.append("")
    lines.append("| Model | Provider | Purpose |")
    lines.append("|---|---|---|")
    lines.append("| `qwen2.5vl` | Ollama (local) | Vision extraction of blank-`amount` financial events from linked images (`vision_extract`) |")
    lines.append("| `gemma4` | Ollama (local) | Ambiguous free-text message classification (`text_interpret`) and grounded `decision_explanation` generation (`explain`) |")
    lines.append("")

    lines.append("## Request Volume")
    lines.append("")
    lines.append(f"- Requests in `dataset/requests.csv` covered by this run: **{num_requests}**")
    lines.append(f"- Total model calls logged: **{total_calls}**")
    lines.append("")

    lines.append("## Model Calls by Call Type")
    lines.append("")
    lines.append("| call_type | model(s) | calls | prompt tokens | completion tokens | total tokens |")
    lines.append("|---|---|---|---|---|---|")
    for call_type in sorted(by_call_type):
        recs = by_call_type[call_type]
        models = sorted({r.model for r in recs})
        p = sum(r.prompt_tokens for r in recs)
        c = sum(r.completion_tokens for r in recs)
        lines.append(f"| {call_type} | {', '.join(models)} | {len(recs)} | {p} | {c} | {p + c} |")
    lines.append(f"| **Total** | | **{total_calls}** | **{total_prompt_tokens}** | **{total_completion_tokens}** | **{total_tokens}** |")
    lines.append("")

    lines.append("## Model Calls by Model (Per-Model Totals)")
    lines.append("")
    lines.append("| model | calls | prompt tokens | completion tokens | total tokens |")
    lines.append("|---|---|---|---|---|")
    for model in sorted(by_model):
        recs = by_model[model]
        p = sum(r.prompt_tokens for r in recs)
        c = sum(r.completion_tokens for r in recs)
        lines.append(f"| {model} | {len(recs)} | {p} | {c} | {p + c} |")
    lines.append(f"| **Total** | **{total_calls}** | **{total_prompt_tokens}** | **{total_completion_tokens}** | **{total_tokens}** |")
    lines.append("")

    avg_tokens_per_request = total_tokens / num_requests if num_requests else 0.0
    avg_calls_per_request = total_calls / num_requests if num_requests else 0.0

    lines.append("## Overall Totals")
    lines.append("")
    lines.append(f"- Total input (prompt) tokens: **{total_prompt_tokens}**")
    lines.append(f"- Total output (completion) tokens: **{total_completion_tokens}**")
    lines.append(f"- Total tokens (input + output): **{total_tokens}**")
    lines.append(f"- Average model calls per request: **{avg_calls_per_request:.2f}**")
    lines.append(f"- Average total tokens per request: **{avg_tokens_per_request:.1f}**")
    lines.append("")

    lines.append("## Cost Estimate")
    lines.append("")
    lines.append(
        "All model calls are served by a **local, unauthenticated Ollama daemon** "
        "(`qwen2.5vl`, `gemma4`) — there is no cloud API billing and no per-token "
        "cost. Estimated total cost: **$0.00**. Estimated per-request cost: **$0.00**. "
        "Token volume is reported above for transparency even though no monetary "
        "cost is incurred."
    )
    lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Token counts are read directly from Ollama's `/api/generate` response "
        "fields `prompt_eval_count` (input tokens) and `eval_count` (output "
        "tokens) for every call, logged in-process by `code.llm.client.OllamaClient."
        "usage_log` (a shared singleton across `code/llm/vision.py`, "
        "`code/llm/interpret.py`, and `code/llm/explain.py`). Deterministic "
        "(temperature=0.0) calls are memoized in-process; a cache hit still "
        "records a usage_log entry (duration_seconds=0.0) so call counts reflect "
        "true logical call volume, not just wall-clock-billed calls."
    )
    lines.append("")

    return "\n".join(lines)


def write_usage_report(
    usage_log,
    num_requests: int,
    out_path: str = "code/evaluation/usage_report.md",
    representative: bool = False,
    note: str | None = None,
) -> str:
    records = _records_from_usage_log(usage_log)
    content = build_report_markdown(records, num_requests, representative=representative, note=note)
    with open(out_path, "w") as f:
        f.write(content)
    return content


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, help="Path to a JSON dump of usage records")
    parser.add_argument("--num-requests", type=int, required=True)
    parser.add_argument("--out", default="code/evaluation/usage_report.md")
    parser.add_argument("--representative", action="store_true")
    parser.add_argument("--note", default=None)
    args = parser.parse_args()

    records = _records_from_json(args.json)
    content = build_report_markdown(
        records, args.num_requests, representative=args.representative, note=args.note
    )
    with open(args.out, "w") as f:
        f.write(content)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    _main()
