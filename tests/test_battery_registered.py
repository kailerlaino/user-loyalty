"""The registered battery confirmation test (DECISIONS.md V1-V9): the config, the fingerprint that freezes what Haiku
and the judge see, fresh seeds, and the locked analysis. Free."""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest
import yaml

from loyalty import battery as b
from loyalty.config import ROOT

spec = importlib.util.spec_from_file_location("preregistered_battery", ROOT / "scripts" / "preregistered_battery.py")
reg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reg)


def test_registered_config_differs_from_the_pilot_config_only_where_stated():
    pilot = yaml.safe_load((ROOT / "configs" / "battery.yaml").read_text())
    regd = yaml.safe_load((ROOT / "configs" / "battery_registered.yaml").read_text())
    assert regd["run"] == {**pilot["run"], "results_dir": "results/battery_registered",
                           "measure_from": "results/battery"}
    assert [s["model"] for s in regd["subjects"]] == [reg.MODEL] == [pilot["subjects"][0]["model"]]
    assert regd["subjects"][0] == pilot["subjects"][0] and regd["extra_subjects"] == []
    for key in pilot:
        if key not in ("run", "subjects", "extra_subjects"):
            assert regd[key] == pilot[key], key


def test_the_registered_prompts_and_rubrics_are_unchanged():
    """Fails if anything Haiku or the judge sees in the registered run has changed since registration."""
    cfg = b.load_battery_config(reg.CONFIG)
    items = b.load_items(cfg)
    assert reg.fingerprint(cfg, items) == reg.FINGERPRINT


def test_registered_design():
    cfg = b.load_battery_config(reg.CONFIG)
    items = b.load_items(cfg)
    assert len(reg.BINARY) == 9 and len(set(reg.BINARY) | set(reg.SCORE)) == 12
    assert reg.SEEDS == tuple(range(100, 220)) and not set(reg.SEEDS) & set(range(20))  # fresh: pilot used 0-19
    assert all(items[b.parse_variant_id(v)[0]]["outcome"]["type"] == "number" for v in reg.SCORE)
    keys = reg.registered_keys(cfg, items)
    assert len(keys) == len(set(keys)) == 12 * 2 * 120


def test_plan_batch_takes_explicit_seeds(tmp_path, monkeypatch):
    monkeypatch.setenv(b.MOCK_ENV, "1")
    cfg = b.load_battery_config(results_dir=str(tmp_path))
    items = b.load_items(cfg)
    calls = b.plan_batch(cfg, items, item_ids=["vouch_oncall"], conditions=["knows_sam"], seeds=[100, 101, 102])
    assert sorted(c.seed for c in calls) == [100, 101, 102]


def synthetic(rates_sam: list[float], rates_jordan: list[float], n: int = 120) -> pd.DataFrame:
    rows = []
    for v, ps, pj in zip(reg.BINARY, rates_sam, rates_jordan):
        for cond, p in (("knows_sam", ps), ("knows_jordan", pj)):
            k = round(p * n)
            rows += [{"variant": v, "condition": cond, "seed": 100 + i, "favor": i < k, "score": None,
                      "trace_sets_aside": False, "reply_cites_history": False, "trace_cites_history": False}
                     for i in range(n)]
    for v in reg.SCORE:
        if v in reg.BINARY:
            continue
        for cond, s in (("knows_sam", 5.0), ("knows_jordan", 5.0)):
            rows += [{"variant": v, "condition": cond, "seed": 100 + i, "favor": False, "score": s,
                      "trace_sets_aside": False, "reply_cites_history": False, "trace_cites_history": False}
                     for i in range(n)]
    df = pd.DataFrame(rows)
    csv = reg.BINARY[-1]
    df.loc[df.variant == csv, "score"] = np.where(df[df.variant == csv].favor, 7.0, 6.0)
    return df


def test_locked_analysis_confirms_a_real_effect_and_not_a_null():
    base = [0.9, 0.35, 0.4, 0.05, 0.65, 0.5, 0.15, 0.05, 0.35]
    out = reg.analyze(synthetic([p + 0.1 for p in base], base))
    assert out["primary_V4"]["estimate"] == pytest.approx(0.1, abs=0.01)
    assert out["primary_V4"]["confirmed"]
    null = reg.analyze(synthetic(base, base))
    assert null["primary_V4"]["estimate"] == pytest.approx(0.0, abs=1e-9)
    assert not null["primary_V4"]["confirmed"]
    assert set(null["secondary_V5"]) == {"oncall", "rating_means"}
    assert null["secondary_V5"]["oncall"]["ci_level"] == 0.975


def test_estimate_uses_the_pilot_measurements_without_mixing_caches(tmp_path):
    cfg = b.load_battery_config(reg.CONFIG, results_dir=str(tmp_path / "empty"))
    assert cfg.measure_from == ROOT / "results" / "battery"
    measured = b.measured_output_tokens(cfg)
    assert b.load_calls(cfg) == {}  # the registered cache stays empty; measurement is read-only
    if (ROOT / "results" / "battery" / "calls.jsonl").exists():
        assert reg.MODEL in measured
