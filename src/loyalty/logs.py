"""Read finished samples back from Inspect logs (used by run.py, export_transcripts.py, analyze.py)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalSample, list_eval_logs, read_eval_log
from inspect_ai.model import ModelUsage


@dataclass
class RunSample:
    model: str  # the subject model
    log: str  # log file it came from
    sample: EvalSample


def load_samples(log_dir: str | Path) -> list[RunSample]:
    """Every finished sample under log_dir (recursive), excluding samples that errored.

    eval_set retries can leave a sample in more than one log; the newest copy wins.
    """
    if not Path(log_dir).exists():
        return []
    found: dict[tuple[str, str | int], RunSample] = {}
    for info in list_eval_logs(str(log_dir), descending=False):  # oldest first
        log = read_eval_log(info)
        for s in log.samples or []:
            if s.error is None and s.scores:
                found[(log.eval.model, s.id)] = RunSample(log.eval.model, info.name, s)
    return list(found.values())


def cell_variants(meta: dict[str, Any]) -> dict[str, str]:
    """Scenario-specific crossed factors of a sample (e.g. {"stakes": "high"}), read from its cell id."""
    parts = meta["cell"].split("|")[1:]
    return {k: v for k, v in (p.split("=", 1) for p in parts) if k not in ("cond", "need")}


def usage_cost(usage: ModelUsage | None, price: dict[str, float] | None) -> float | None:
    """Dollars for one model's usage: Inspect's own total when it has one, else from the price table."""
    if usage is None:
        return 0.0
    if usage.total_cost is not None:
        return usage.total_cost
    if price is None:
        return None
    return (
        usage.input_tokens * price["input"]
        + usage.output_tokens * price["output"]
        + (usage.input_tokens_cache_write or 0) * price.get("input_cache_write", price["input"])
        + (usage.input_tokens_cache_read or 0) * price.get("input_cache_read", price["input"])
    ) / 1e6
