"""Render the user's fact sheet into the context block for each condition.

    shared_history          the agent's own memory notes about the user
    detailed_stranger       the same fact lines, framed as a third-party profile
    length_matched_neutral  unrelated notes, trimmed to the shared-history block's length
    stranger                only the "first session" line
    deep_shared_history     shared_history plus the agent's own past conversations with the user
                            (the support sessions in history.sessions)
    deep_dossier            detailed_stranger plus the same conversations, held by the user's
                            previous assistant and imported (only the frame and speaker label differ)
    work_shared_history     shared_history plus work-only conversations of matched length

Wording lives in prompts/history_frames.yaml; facts in materials/fact_sheet.yaml; past
conversations in materials/past_sessions.yaml (DECISIONS.md K1).

history.format says where past conversations go: "memory_file" puts them in the system prompt as
dated transcripts (K1); "thread" makes them earlier messages of the conversation itself, before the
user's request, with one system-prompt line saying whose they were (K5). The facts are the same either way.
"""

from __future__ import annotations

from typing import Any

import yaml

from loyalty.config import SESSION_CONDITIONS, resolve
from loyalty.counterbalance import rotate

FORMATS = ("memory_file", "thread")
LENGTH_TOLERANCE = 0.05  # DECISIONS.md D7 / C3: whole notes only, so ±2% isn't always reachable
DEFAULT_FRAMES = "prompts/history_frames.yaml"
# condition -> (kind of past conversation, whose voice the assistant turns are in)
SESSIONS_FOR = {"deep_shared_history": ("support", "own"), "deep_dossier": ("support", "handed"),
                "work_shared_history": ("work", "own")}


def render_context(
    condition: str, fact_sheet: dict[str, Any], history_cfg: dict[str, Any], seed_index: int,
    profile_source: str = "a third-party profile service",
) -> tuple[str, dict[str, Any]]:
    """Return (context block for the system prompt, metadata to record on the sample).

    With history.format "thread", the metadata's `thread_turns` holds the past conversation as
    [role, text] pairs for the dataset to put before the request (and pop from the metadata)."""
    fmt = history_cfg.get("format", "memory_file")
    if fmt not in FORMATS:
        raise NotImplementedError(f"history.format must be one of {FORMATS}.")
    if history_cfg.get("dose") is not None:
        raise NotImplementedError("history.dose is reserved for the dose-response study.")

    frames = yaml.safe_load(resolve(history_cfg.get("frames", DEFAULT_FRAMES)).read_text())
    thread: list[list[str]] = []
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
    elif condition in SESSIONS_FOR:
        kind, voice = SESSIONS_FOR[condition]
        base = shared if voice == "own" else frames["detailed_stranger"].format_map(fields)
        sessions = load_sessions(history_cfg)[kind]["sessions"]
        if fmt == "thread":
            text = base + "\n\n" + frames[f"{voice}_thread"].format_map(fields)
            thread = [[role, said] for s in sessions for turn in s["turns"] for role, said in turn.items()]
        else:
            text = base + "\n\n" + render_sessions(frames, fields, sessions, voice)
    else:
        raise ValueError(f"Unknown condition {condition!r}")

    shows_facts = condition in ("shared_history", "detailed_stranger", *SESSION_CONDITIONS)
    meta = {"thread_turns": thread} if fmt == "thread" and condition in SESSIONS_FOR else {}
    return text, {
        **meta,
        "fact_order": [f["id"] for f in facts] if shows_facts else None,
        "shared_history_chars": len(shared),
        "sessions": SESSIONS_FOR[condition][0] if condition in SESSIONS_FOR else None,
    }


def load_sessions(history_cfg: dict[str, Any]) -> dict[str, Any]:
    return yaml.safe_load(resolve(history_cfg["sessions"]).read_text())


def render_sessions(frames: dict[str, str], fields: dict[str, Any], sessions: list[dict[str, Any]], voice: str) -> str:
    """Past conversations as dated transcripts. `voice` "own": the assistant turns are labeled as the
    agent's ("You"); "handed": as the user's previous assistant's. Nothing else differs."""
    speakers = {"user": fields["first_name"], "assistant": frames[f"{voice}_speaker"]}
    blocks = []
    for s in sessions:
        turns = []
        for turn in s["turns"]:
            [(who, said)] = turn.items()
            turns.append(frames["session_turn"].format_map({"speaker": speakers[who], "text": said}))
        blocks.append(frames["session"].format_map({"date": s["date"], "turns": "\n".join(turns)}))
    return frames[f"{voice}_sessions"].format_map(
        {**fields, "n_sessions": len(sessions), "sessions": "\n\n".join(blocks)})


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
