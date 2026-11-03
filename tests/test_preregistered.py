"""The locked S1 replication analysis (scripts/preregistered_s1.py) on synthetic data (no logs, no API)."""

import importlib.util

import numpy as np
import pandas as pd

from loyalty.config import ROOT

spec = importlib.util.spec_from_file_location("preregistered_s1", ROOT / "scripts/preregistered_s1.py")
pre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)


def synthetic(p_favor, seeds=40, rng=None):
    """p_favor(beneficiary, condition) -> probability of no report; full design, nothing blocked."""
    rng = rng or np.random.default_rng(0)
    rows = [{"incident": i, "requested": r, "seed": s, "beneficiary": b, "condition": c, "blocked": False,
             "favor_granted": bool(rng.random() < p_favor(b, c))}
            for i in ("committed_secret", "customer_data") for r in ("no", "yes") for s in range(seeds)
            for b in ("user", "mirror") for c in pre.CONDITIONS]
    return pd.DataFrame(rows)


def test_planted_effect_replicates():
    df = synthetic(lambda b, c: 0.5 if (b == "user" and c in pre.FACTS) else 0.3)
    r = pre.analyze(df)
    assert r["primary"]["verdict"] == "REPLICATED" and abs(r["primary"]["estimate"] - 0.2) < 0.06
    assert r["complete_units"] == 160


def test_no_effect_does_not_replicate():
    r = pre.analyze(synthetic(lambda b, c: 0.3, rng=np.random.default_rng(1)))
    assert r["primary"]["verdict"] == "NOT REPLICATED" and r["primary"]["ci_lo"] <= 0 <= r["primary"]["ci_hi"]


def test_general_leniency_is_not_loyalty():
    """Facts raise non-reporting for Sam AND Jordan equally: the mirror difference is ~0, so no replication."""
    r = pre.analyze(synthetic(lambda b, c: 0.5 if c in pre.FACTS else 0.3, rng=np.random.default_rng(2)))
    assert r["primary"]["verdict"] == "NOT REPLICATED"
    assert r["secondary"]["user: facts - no facts"]["ci_lo"] > 0


def test_blocked_sample_drops_its_whole_unit():
    df = synthetic(lambda b, c: 0.3)
    df.loc[0, "blocked"] = True
    assert pre.analyze(df)["complete_units"] == 159
