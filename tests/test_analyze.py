"""Analysis math on synthetic rows (no logs, no API)."""

import importlib.util

import numpy as np
import pandas as pd
import pytest

from loyalty.config import ROOT

spec = importlib.util.spec_from_file_location("analyze", ROOT / "scripts/analyze.py")
analyze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze)


def synthetic(comply):
    """comply(condition, need) -> 0/1, same for every seed and stakes level."""
    rows = []
    for stakes in ("low", "high"):
        for condition in ("stranger", "length_matched_neutral", "detailed_stranger", "shared_history"):
            for need in ("low", "high"):
                for seed in range(5):
                    y = bool(comply(condition, need))
                    rows.append({"model": "m", "sample_id": f"{stakes}{condition}{need}{seed}",
                                 "scenario": "billing_credit", "stakes": stakes, "condition": condition,
                                 "need": need, "seed": seed, "judged": True, "api_blocked": False, "consistent": True,
                                 **{o: False for o in analyze.OUTCOMES}, "comply": y, "cost": 0.1, "messages": 20})
    return pd.DataFrame(rows)


def find(con, outcome, contrast, stratum="all"):
    r = con[(con.outcome == outcome) & (con.contrast == contrast) & (con.stratum == stratum)]
    return r.iloc[0]


def test_wilson():
    lo, hi = analyze.wilson(0, 10)
    assert lo == 0 and hi == pytest.approx(0.2775, abs=1e-3)
    lo, hi = analyze.wilson(10, 10)
    assert hi == 1 and lo == pytest.approx(0.7225, abs=1e-3)


def test_paired_contrast_and_interaction():
    # history helps only under high need
    df = synthetic(lambda c, n: c == "shared_history" and n == "high")
    con = analyze.contrasts(df, ["stakes"], np.random.default_rng(0))
    main = find(con, "comply", "shared_history - detailed_stranger")
    assert main.pairs == 20 and main["diff"] == 0.5
    high = find(con, "comply", "shared_history - detailed_stranger", "stakes=high need=high")
    assert high["diff"] == 1 and high.ci_lo == 1 and high.ci_hi == 1
    did = find(con, "comply", "(SH - DS | high need) - (SH - DS | low need)")
    assert did.pairs == 10 and did["diff"] == 1


def test_no_effect_gives_zero():
    con = analyze.contrasts(synthetic(lambda c, n: n == "high"), ["stakes"], np.random.default_rng(0))
    assert (con[con.outcome == "comply"]["diff"] == 0).all()


def test_cell_table_counts():
    df = synthetic(lambda c, n: c == "shared_history")
    table = analyze.cell_table(df, ["condition"])
    row = table[table.condition == "shared_history"].iloc[0]
    assert row.n == 20 and row.comply.startswith("20/20")
