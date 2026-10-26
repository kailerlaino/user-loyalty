"""Load a run config (configs/*.yaml) and expand it into cells.

A cell is one combination of crossed factors, e.g.
{scenario: billing_credit, stakes: high, condition: shared_history, need: low}.
"""

from __future__ import annotations

import itertools
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from inspect_ai.model import ModelCost

ROOT =Path(__file__).resolve().parents[2]

CONDITIONS = ("stranger", "length_matched_neutral", "detailed_stranger", "shared_history")
NEED_LEVELS = ("low", "high")


@dataclass
class ModelSpec:
    model: str
    generate: dict[str, Any] = field(default_factory=dict)  # -> inspect GenerateConfig
    model_args: dict[str, Any] = field(default_factory=dict)  # provider-specific passthrough


@dataclass
class RunSettings:
    name: str
    log_dir: str
    samples_per_cell: int
    seed: int = 0
    max_samples: int = 8
    message_limit: int = 40


@dataclass
class ScenarioRef:
    file: str
    variants: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Config:
    path: str
    run: RunSettings
    subjects: list[ModelSpec]
    judge: ModelSpec
    judge_rubric: str
    pricing: dict[str, dict[str, float]]
    history: dict[str, Any]
    conditions: list[str]
    need: list[str]
    scenarios: dict[str, ScenarioRef]

    def model_costs(self) -> dict[str, ModelCost]:
        """Pricing table in Inspect's format; pass as eval(model_cost_config=...) so logs carry total_cost."""
        return {model: ModelCost(**price) for model, price in self.pricing.items()}

    def cells(self) -> list[dict[str, str]]:
        """Every combination of scenario x its variants x condition x need, in a fixed order."""
        out = []
        for name, ref in self.scenarios.items():
            keys = list(ref.variants)
            for levels in itertools.product(*(ref.variants[k] for k in keys)):
                for condition in self.conditions:
                    for need in self.need:
                        out.append({"scenario": name, **dict(zip(keys, levels)),
                                    "condition": condition, "need": need})
        return out


def resolve(path: str) -> Path:
    """Paths in configs are relative to the repo root."""
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def load_config(path: str) -> Config:
    raw = yaml.safe_load(resolve(path).read_text())
    judge_raw = dict(raw["judge"])
    cfg = Config(
        path=str(path),
        run=RunSettings(**raw["run"]),
        subjects=[ModelSpec(**s) for s in raw["subjects"]],
        judge=ModelSpec(**{k: v for k, v in judge_raw.items() if k != "rubric"}),
        judge_rubric=judge_raw.get("rubric", "prompts/judge_rubric.md"),
        pricing=raw.get("pricing", {}),
        history=raw["history"],
        conditions=list(raw["conditions"]),
        need=list(raw["need"]),
        scenarios={k: ScenarioRef(**v) for k, v in raw["scenarios"].items()},
    )
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    unknown = set(cfg.conditions) - set(CONDITIONS)
    if unknown:
        raise ValueError(f"Unknown conditions: {sorted(unknown)}. Known: {CONDITIONS}")
    if set(cfg.need) - set(NEED_LEVELS):
        raise ValueError(f"need levels must be among {NEED_LEVELS}")
    if not cfg.subjects:
        raise ValueError("Config needs at least one subject model.")
    subject_models = {s.model for s in cfg.subjects}
    if cfg.judge.model in subject_models:
        raise ValueError(f"Judge model {cfg.judge.model} must differ from every subject model.")
    for spec in [*cfg.subjects, cfg.judge]:
        if "/" not in spec.model:
            raise ValueError(f"Model {spec.model!r} needs a provider prefix, e.g. anthropic/..., openai/..., openrouter/...")
        if spec.model not in cfg.pricing and not spec.model.startswith("mockllm/"):
            warnings.warn(f"No pricing for {spec.model}: tokens will be reported, cost will be n/a.")
