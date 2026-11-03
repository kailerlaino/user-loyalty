"""The locked relationship-depth analysis (scripts/preregistered_depth.py) on synthetic data (no logs, no API)."""

import importlib.util

import numpy as np
import pandas as pd

from loyalty.config import ROOT, load_config

spec = importlib.util.spec_from_file_location("preregistered_depth", ROOT / "scripts/preregistered_depth.py")
pre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)


def synthetic(p_favor, seeds=100, rng=None):
    """p_favor(beneficiary, condition) -> probability of no report; full design, nothing blocked."""
    rng = rng or np.random.default_rng(0)
    rows = [{"incident": i, "requested": r, "seed": s, "beneficiary": b, "condition": c, "blocked": False,
             "favor_granted": bool(rng.random() < p_favor(b, c)), "mentions_support": False}
            for i in ("committed_secret", "customer_data") for r in ("no", "yes") for s in range(seeds)
            for b in ("user", "mirror") for c in pre.CONDITIONS]
    return pd.DataFrame(rows)


def test_planted_effect_is_confirmed():
    r = pre.analyze(synthetic(lambda b, c: 0.55 if (b == "user" and c == pre.OWN) else 0.35))
    assert r["primary"]["verdict"] == "CONFIRMED" and abs(r["primary"]["estimate"] - 0.2) < 0.07
    assert r["complete_units"] == 400


def test_no_effect_is_not_confirmed():
    r = pre.analyze(synthetic(lambda b, c: 0.35, rng=np.random.default_rng(1)))
    assert r["primary"]["verdict"] == "NOT CONFIRMED" and r["primary"]["ci_lo"] <= 0 <= r["primary"]["ci_hi"]


def test_warmth_for_everyone_is_not_loyalty():
    """Own conversations raise non-reporting for Sam AND Jordan equally: no confirmation."""
    r = pre.analyze(synthetic(lambda b, c: 0.55 if c == pre.OWN else 0.35, rng=np.random.default_rng(2)))
    assert r["primary"]["verdict"] == "NOT CONFIRMED"
    assert r["secondary"]["user: own - imported conversations"]["ci_lo"] > 0


def test_a_low_imported_cell_still_counts_and_is_visible():
    """The pilot's pattern: the gap comes from the imported version being low. P4 counts it; P5 shows which side moved."""
    r = pre.analyze(synthetic(lambda b, c: 0.15 if (b == "user" and c == pre.IMPORTED) else 0.45, rng=np.random.default_rng(3)))
    assert r["primary"]["verdict"] == "CONFIRMED"
    s = r["secondary"]
    assert s["user: imported conversations + profile - profile only"]["ci_hi"] < 0
    assert s["user: own conversations + memories - memories only"]["ci_lo"] <= 0 <= s["user: own conversations + memories - memories only"]["ci_hi"]


def test_blocked_sample_drops_its_whole_unit():
    df = synthetic(lambda b, c: 0.3)
    df.loc[0, "blocked"] = True
    assert pre.analyze(df)["complete_units"] == 399


def test_registered_config_matches_the_pilot_except_size():
    reg, pilot = load_config("configs/depth_registered.yaml"), load_config("configs/depth_thread_pilot.yaml")
    assert reg.run.samples_per_cell == 100 and reg.run.name == "depth_registered"
    assert (reg.subjects, reg.history, reg.conditions, reg.need, reg.scenarios, reg.run.message_limit) == \
        (pilot.subjects, pilot.history, pilot.conditions, pilot.need, pilot.scenarios, pilot.run.message_limit)
    assert tuple(reg.conditions) == pre.CONDITIONS and len(reg.cells()) == 48
