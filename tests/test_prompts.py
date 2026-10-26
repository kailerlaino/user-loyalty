"""No agent-visible text uses language that invites role-play or signals a test (design doc)."""

import re

from inspect_ai.tool import ToolDef

from loyalty.config import load_config
from loyalty.dataset import build_samples
from loyalty.scenario import load_fact_sheet, load_scenarios
from loyalty.tools import all_tools

BANNED = re.compile(r"\b(bond\w*|relationship\w*|loyal\w*|eval\w*|experiment\w*|test subject)\b", re.IGNORECASE)


def agent_visible_texts():
    cfg = load_config("configs/smoke.yaml")
    fs = load_fact_sheet(cfg)
    for s in build_samples(cfg, load_scenarios(cfg, fs), fs):
        for msg in s.input:
            yield s.id, msg.content
    for t in all_tools():
        tdef = ToolDef(t)
        yield tdef.name, tdef.description
        for name, param in tdef.parameters.properties.items():
            yield f"{tdef.name}.{name}", param.description or ""


def test_no_banned_words():
    hits = [(where, m.group(0)) for where, text in agent_visible_texts() for m in BANNED.finditer(text)]
    assert hits == []
