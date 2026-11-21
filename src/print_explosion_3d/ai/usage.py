"""Per-call usage log (`usage.jsonl` in the workspace) with a rough cost estimate."""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path

from print_explosion_3d.ai.base import Usage

# USD per million tokens: (input, output, cache read, cache write). Estimates only; unknown models
# log tokens with a null cost.
_PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-sonnet-5": (2.00, 10.00, 0.20, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}


def estimate_cost(usage: Usage) -> float | None:
    prices = _PRICES.get(usage.model)
    if prices is None:
        return None
    inp, out, read, write = prices
    return (
        usage.input_tokens * inp
        + usage.output_tokens * out
        + usage.cache_read_tokens * read
        + usage.cache_write_tokens * write
    ) / 1_000_000


def log_usage(path: Path, usage: Usage, *, label: str = "", project: str = "") -> None:
    """Append one line. Logging must never break a turn, so all I/O errors are swallowed."""
    cost = estimate_cost(usage)
    entry = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "project": project,
        "label": label,
        "model": usage.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "cost_usd": None if cost is None else round(cost, 6),
    }
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
