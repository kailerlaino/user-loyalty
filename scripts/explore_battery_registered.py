"""EXPLORATORY cuts of the registered battery run (DECISIONS.md V7 and the results entry). Not part of the
registered analysis, which is scripts/preregistered_battery.py; nothing here decides a claim.

    uv run python scripts/explore_battery_registered.py

- D split by tier (violation / ambiguous) and by asker (Sam / a principal or third party), items fixed.
- D without the on-call item.
- Per item: how many traces say the history is being set aside, by condition, and the favor rate with and without
  that in knows_sam (within item, so the item mix can't drive it).
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd

from loyalty import battery as b
from loyalty.config import ROOT

spec = importlib.util.spec_from_file_location("reg", ROOT / "scripts" / "preregistered_battery.py")
reg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reg)


def main() -> None:
    cfg = b.load_battery_config(reg.CONFIG)
    items = b.load_items(cfg)
    reg.check(cfg, items)
    df = reg.load(cfg, items)
    rng = np.random.default_rng(reg.RNG_SEED + 1)
    meta = {v: items[b.parse_variant_id(v)[0]] for v in reg.BINARY}

    def subset(pred) -> tuple[str, ...]:
        return tuple(v for v in reg.BINARY if pred(meta[v]))

    cuts = {
        "all 9 (the registered D)": reg.BINARY,
        "tier = violation": subset(lambda i: i["tier"] == "violation"),
        "tier = ambiguous": subset(lambda i: i["tier"] == "ambiguous"),
        "asker = sam": subset(lambda i: i["asker"] == "sam"),
        "asker = principal or third party": subset(lambda i: i["asker"] != "sam"),
        "without vouch_oncall": tuple(v for v in reg.BINARY if v != reg.ONCALL),
    }
    print("D = knows_sam - knows_jordan, items fixed, 95% bootstrap (EXPLORATORY)")
    for name, vids in cuts.items():
        r = reg.items_fixed(df, vids, "favor", 0.95, rng)
        print(f"  {name:<36} {r['estimate']:+.3f} ({r['ci_lo']:+.3f} to {r['ci_hi']:+.3f})  items={len(vids)}")

    print("\nTraces that say the history is set aside (SET_ASIDE), per item, and knows_sam favor with / without:")
    rows = []
    for v in reg.BINARY:
        d = df[(df.variant == v) & df.favor.notna()]
        s, j = d[d.condition == "knows_sam"], d[d.condition == "knows_jordan"]
        with_, without = s[s.trace_sets_aside], s[~s.trace_sets_aside]
        rate = lambda x: f"{x.favor.eq(True).mean():.2f} (n={len(x)})" if len(x) else "-"
        rows.append({"variant": v.split("|")[0], "set_aside_sam": int(s.trace_sets_aside.sum()),
                     "set_aside_jordan": int(j.trace_sets_aside.sum()),
                     "sam_favor_if_set_aside": rate(with_), "sam_favor_otherwise": rate(without),
                     "jordan_favor": f"{j.favor.eq(True).mean():.2f}"})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
