"""No agent-visible text uses language that invites role-play or signals a test (design doc)."""

import re

from inspect_ai.tool import ToolDef

from loyalty.config import load_config
from loyalty.dataset import build_samples
from loyalty.scenario import load_fact_sheet, load_scenarios
from loyalty.tools import all_tools

BANNED = re.compile(r"\b(bond\w*|relationship\w*|loyal\w*|eval\w*|experiment\w*|test subject)\b", re.IGNORECASE)


def agent_visible_texts():
    for path in ("configs/smoke.yaml", "configs/batch_probe.yaml", "configs/s1_calibration.yaml",
                 "configs/s1_calibration_v2.yaml",
                 "configs/s1_history.yaml", "configs/s2_calibration.yaml"):
        cfg = load_config(path)
        fs = load_fact_sheet(cfg)
        scenarios = load_scenarios(cfg, fs)
        for s in build_samples(cfg, scenarios, fs):
            for msg in s.input:
                yield s.id, msg.content
            for file_path, text in scenarios[s.metadata["scenario"]].initial_files(s.metadata).items():
                yield f"{s.id}:{file_path}", text
            for page, text in scenarios[s.metadata["scenario"]].wiki_pages(s.metadata).items():
                yield f"{s.id}:wiki:{page}", text
    for t in all_tools():
        tdef = ToolDef(t)
        yield tdef.name, tdef.description
        for name, param in tdef.parameters.properties.items():
            yield f"{tdef.name}.{name}", param.description or ""


def test_no_banned_words():
    hits = [(where, m.group(0)) for where, text in agent_visible_texts() for m in BANNED.finditer(text)]
    assert hits == []
