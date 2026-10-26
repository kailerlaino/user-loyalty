"""Render the user's fact sheet into the context block for each condition.

    shared_history          the agent's own memory notes about the user
    detailed_stranger       the same fact lines, framed as a third-party profile
    length_matched_neutral  unrelated notes, trimmed to the shared-history block's length
    stranger                only the "first session" line

Wording lives in prompts/history_frames.yaml; facts in materials/fact_sheet.yaml.
"""

from __future__ import annotations

from typing import Any

import yaml

from loyalty.config import resolve
from loyalty.counterbalance import rotate

LENGTH_TOLERANCE = 0.05  # DECISIONS.md D7 / C3: whole notes only, so ±2% isn't always reachable
DEFAULT_FRAMES = "prompts/history_frames.yaml"


def render_context(
    condition: str, fact_sheet: dict[str, Any], history_cfg: dict[str, Any], seed_index: int,
    profile_source: str = "a third-party profile service",
) -> tuple[str, dict[str, Any]]:
    """Return (context block for the system prompt, metadata to record on the sample)."""
    if history_cfg.get("format", "memory_file") != "memory_file":
        raise NotImplementedError("history.format other than memory_file is reserved for later.")
    if history_cfg.get("dose") is not None:
        raise NotImplementedError("history.dose is reserved for the dose-response study.")

    frames = yaml.safe_load(resolve(history_cfg.get("frames", DEFAULT_FRAMES)).read_text())
    user = fact_sheet["user"]
    fields = {"name": user["name"], "first_name": user["first_name"],
              "n_facts": len(fact_sheet["facts"]), "profile_source": profile_source}
    fields["no_memory"] = frames["no_memory"].format_map(fields)

    facts = rotate(fact_sheet["facts"], seed_index)
    fields["facts"] = "\n".join(
        frames["fact_line"].format_map({**fields, "text": f["text"]}) for f in facts
    )
    shared = frames["shared_history"].format_map(fields)

    if condition == "shared_history":
        text = shared
    elif condition == "detailed_stranger":
        text = frames["detailed_stranger"].format_map(fields)
    elif condition == "stranger":
        text = frames["stranger"].format_map(fields)
    elif condition == "length_matched_neutral":
        notes = load_notes(history_cfg["neutral_notes"])
        text = fill_to_length(frames, fields, notes, target=len(shared))
    else:
        raise ValueError(f"Unknown condition {condition!r}")

    shows_facts = condition in ("shared_history", "detailed_stranger")
    return text, {
        "fact_order": [f["id"] for f in facts] if shows_facts else None,
        "shared_history_chars": len(shared),
    }


def load_notes(path: str) -> list[str]:
    lines = resolve(path).read_text().splitlines()
    return [line[2:].strip() for line in lines if line.startswith("- ")]


def fill_to_length(frames: dict[str, str], fields: dict[str, str], notes: list[str], target: int) -> str:
    """Add notes in file order, skipping any that would overshoot, until within tolerance of target."""
    template = frames["length_matched_neutral"]
    base = len(template.format_map({**fields, "notes": ""}))
    lo, hi = target * (1 - LENGTH_TOLERANCE), target * (1 + LENGTH_TOLERANCE)
    chosen: list[str] = []
    for note in notes:
        candidate = chosen + [frames["note_line"].format_map({"text": note})]
        if base + len("\n".join(candidate)) <= hi:
            chosen = candidate
        if base + len("\n".join(chosen)) >= lo:
            break
    text = template.format_map({**fields, "notes": "\n".join(chosen)})
    if not lo <= len(text) <= hi:
        raise ValueError(
            f"Neutral block is {len(text)} chars, target {target} ±{LENGTH_TOLERANCE:.0%}. "
            "Add more (including some short) notes to the neutral notes file."
        )
    return text
