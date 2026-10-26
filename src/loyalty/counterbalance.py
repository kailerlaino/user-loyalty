"""Counterbalancing helpers (DECISIONS.md D8)."""

from __future__ import annotations

from typing import Any


def rotate(items: list[Any], k: int) -> list[Any]:
    """Cyclic Latin-square rotation: each item visits each position once per len(items) seeds."""
    if not items:
        return []
    k %= len(items)
    return items[k:] + items[:k]
