"""Short-scenario battery from the terminal (DECISIONS.md step j). notebooks/battery.ipynb calls the same functions.

    uv run python scripts/battery.py                                   # validate and list the items (free)
    uv run python scripts/battery.py show ITEM [--condition knows_sam] [--seed 0] [--set knob=level ...]
    uv run python scripts/battery.py plan [--items a,b] [--models haiku,luna] [--conditions stranger] [--n 10]
                                          [--sweep ITEM:knob=level1,level2 ...]          # estimate only (free)
    uv run python scripts/battery.py plan ... --confirm                # PAID: needs the owner's yes first
    uv run python scripts/battery.py grade [--confirm]                 # judge replies that have no verdict yet
    uv run python scripts/battery.py table [--condition stranger]      # calibration grid from cached results
    uv run python scripts/battery.py contrast [--a knows_sam --b knows_jordan]

Results live in results/battery/ (gitignored). Re-running a plan sends only the calls not already cached.
"""

from __future__ import annotations

import argparse
import asyncio

import pandas as pd

from loyalty import battery as b


def parse_sweep(specs: list[str]) -> dict[str, dict[str, list[str]]]:
    """["item:knob=l1,l2", ...] -> {item: {knob: [l1, l2]}}"""
    out: dict[str, dict[str, list[str]]] = {}
    for spec in specs:
        item, _, rest = spec.partition(":")
        knob, _, levels = rest.partition("=")
        if not (item and knob and levels):
            raise SystemExit(f"--sweep wants ITEM:knob=level1,level2, got {spec!r}")
        out.setdefault(item, {})[knob] = levels.split(",")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", default="list", choices=["list", "show", "plan", "grade", "table", "contrast"])
    ap.add_argument("item", nargs="?")
    ap.add_argument("--config", default="configs/battery.yaml")
    ap.add_argument("--items", default="", help="comma-separated item ids (default: all)")
    ap.add_argument("--models", default="", help="comma-separated subjects, full id or a unique part (default: subjects)")
    ap.add_argument("--conditions", default="stranger")
    ap.add_argument("--n", type=int, default=10, help="replies per variant x condition x model")
    ap.add_argument("--sweep", nargs="*", default=[], help="ITEM:knob=level1,level2")
    ap.add_argument("--set", nargs="*", default=[], help="show: knob=level")
    ap.add_argument("--condition", default="stranger")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--a", default="knows_sam")
    ap.add_argument("--b", default="knows_jordan")
    ap.add_argument("--max-usd", type=float, default=None, help="stop-loss cap (default 1.5x the estimate + $0.05)")
    ap.add_argument("--confirm", action="store_true", help="actually send the calls (costs money)")
    args = ap.parse_args()

    cfg = b.load_battery_config(args.config)
    items = b.load_items(cfg)
    pd.set_option("display.width", 200, "display.max_columns", 20, "display.max_rows", 200)

    if args.command == "list":
        for it in items.values():
            knobs = ", ".join(f"{k}={v['use']}" for k, v in (it.get("knobs") or {}).items())
            print(f"{it['id']:<24} {it['family']:<22} {it['tier']:<10} asker={it['asker']:<12} "
                  f"{it['outcome']['type']:<7} {knobs}")
        print(f"\n{len(items)} items valid. Subjects: {[s.model for s in cfg.subjects]}; judge: {cfg.judge.model}")
    elif args.command == "show":
        if not args.item:
            raise SystemExit("show needs an item id")
        levels = dict(s.split("=", 1) for s in args.set)
        print(b.show_prompt(cfg, items, args.item, args.condition, args.seed, levels))
    elif args.command == "plan":
        calls = b.plan_batch(cfg, items, item_ids=[i for i in args.items.split(",") if i] or None,
                             models=[m for m in args.models.split(",") if m] or None,
                             conditions=args.conditions.split(","), n=args.n, sweep=parse_sweep(args.sweep))
        b.run(cfg, calls, items, confirm=args.confirm, max_usd=args.max_usd)
    elif args.command == "grade":
        asyncio.run(b.grade(cfg, items, confirm=args.confirm, max_usd=args.max_usd))
    elif args.command == "table":
        cal = b.calibration(b.results(cfg, items), args.condition)
        if cal.empty:
            print("No cached results for that condition.")
            return
        print(b.grid(cal).to_string())
        lo, hi = b.CALIBRATION_RANGE
        print(f"\nfavor/read per variant x model ({args.condition}); * = rate within {lo:.0%}-{hi:.0%}")
        unread = cal[cal.read < cal.n]
        if not unread.empty:
            print(f"Unread replies (no parseable outcome or no verdict yet): {int((unread.n - unread.read).sum())}")
    elif args.command == "contrast":
        df = b.results(cfg, items)
        for measure in ("favor", "score"):
            out = b.contrast(df, args.a, args.b, measure=measure)
            if not out.empty:
                print(out.to_string(index=False, float_format=lambda x: f"{x:+.3f}"), "\n")
        for measure in ("favor", "score"):
            per = b.by_variant(df, measure=measure)
            if not per.empty:
                print(f"per variant ({measure}):")
                print(per.to_string(index=False, float_format=lambda x: f"{x:.2f}"), "\n")


if __name__ == "__main__":
    main()
