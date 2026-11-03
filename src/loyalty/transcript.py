"""Plain-text rendering of a sample's messages, shared by the judge and the transcript exporter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from inspect_ai.model import (
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageTool,
    ChatMessageUser,
    ContentReasoning,
    ContentText,
)


def reasoning_kind(block: ContentReasoning) -> str:
    """'full' (raw chain of thought), 'summary' (provider summary), or 'hidden' (nothing readable)."""
    if not block.redacted and block.reasoning:
        return "full"
    return "summary" if block.summary else "hidden"


def reasoning_text(block: ContentReasoning) -> str:
    return block.reasoning if reasoning_kind(block) == "full" else (block.summary or "")


def sample_reasoning_kind(messages: list[ChatMessage]) -> str:
    """Best reasoning visibility seen in the sample: full > summary > hidden > none."""
    kinds = {
        reasoning_kind(c)
        for m in messages if isinstance(m, ChatMessageAssistant) and not isinstance(m.content, str)
        for c in m.content if isinstance(c, ContentReasoning)
    }
    for kind in ("full", "summary", "hidden"):
        if kind in kinds:
            return kind
    return "none"


def final_assistant_index(messages: list[ChatMessage]) -> int | None:
    """The last assistant message is what the user reads."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], ChatMessageAssistant):
            return i
    return None


def final_message(messages: list[ChatMessage]) -> str:
    """The text of the last assistant message (what the user reads), without reasoning; "" if none."""
    i = final_assistant_index(messages)
    return "" if i is None else "\n".join(_text_parts(messages[i].content))


def _text_parts(content: str | list[Any]) -> list[str]:
    if isinstance(content, str):
        return [content] if content else []
    return [c.text for c in content if isinstance(c, ContentText) and c.text]


@dataclass
class Block:
    """One labeled piece of a transcript, e.g. kind="tool_call", label="TOOL CALL: read_file"."""

    kind: str  # system | user | reasoning | assistant | final | tool_call | tool_result
    label: str
    text: str


def transcript_blocks(messages: list[ChatMessage], redact: dict[str, str] | None = None) -> list[Block]:
    """Messages as labeled blocks, in order.

    `redact` maps exact substrings of the system prompt to replacements (the judge
    uses it to hide the condition-specific context block so it labels behavior
    blind to condition).
    """
    final_idx = final_assistant_index(messages)
    out: list[Block] = []
    for i, m in enumerate(messages):
        if isinstance(m, ChatMessageSystem):
            text = m.text
            for old, new in (redact or {}).items():
                text = text.replace(old, new)
            out.append(Block("system", "SYSTEM PROMPT", text))
        elif isinstance(m, ChatMessageUser):
            out.append(Block("user", "USER MESSAGE", m.text))
        elif isinstance(m, ChatMessageAssistant):
            if not isinstance(m.content, str):
                for c in m.content:
                    if isinstance(c, ContentReasoning):
                        kind = reasoning_kind(c)
                        out.append(Block("reasoning", f"ASSISTANT REASONING ({kind})",
                                         reasoning_text(c) or "(not visible)"))
            text = "\n".join(_text_parts(m.content))
            if text:
                final = i == final_idx
                out.append(Block("final" if final else "assistant",
                                 "ASSISTANT FINAL MESSAGE TO USER" if final else "ASSISTANT", text))
            for call in m.tool_calls or []:
                out.append(Block("tool_call", f"TOOL CALL: {call.function}",
                                 json.dumps(call.arguments, indent=2)))
        elif isinstance(m, ChatMessageTool):
            status = f" ERROR: {m.error.message}" if m.error else ""
            out.append(Block("tool_result", f"TOOL RESULT: {m.function}{status}", m.text))
    return out


def render_transcript(messages: list[ChatMessage], redact: dict[str, str] | None = None) -> str:
    """Plain text with [LABEL] lines; this is what the judge reads."""
    return "\n\n".join(f"[{b.label}]\n{b.text}" for b in transcript_blocks(messages, redact))
