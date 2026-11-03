"""Write the exact prompts the agent sees, one section per condition, for reading.

    uv run python scripts/show_prompts.py                     # high stakes, high need, seed 0
    uv run python scripts/show_prompts.py --stakes low --need low --seed 2

Output: previews/<scenario>_stakes-<s>_need-<n>_s<seed>.md (gitignored; regenerate any time).
"""

from __future__ import annotations

import argparse

from loyalty.config import ROOT, load_config
from loyalty.dataset import build_samples
from loyalty.scenario import load_fact_sheet, load_scenarios


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/smoke.yaml")
    ap.add_argument("--scenario", default="billing_credit")
    ap.add_argument("--stakes", default="high")
    ap.add_argument("--need", default="high")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cfg = load_config(args.config)
    cfg.run.samples_per_cell = max(cfg.run.samples_per_cell, args.seed + 1)
    fs = load_fact_sheet(cfg)
    samples = [
        s for s in build_samples(cfg, load_scenarios(cfg, fs), fs)
        if s.metadata["scenario"] == args.scenario and s.metadata.get("stakes") == args.stakes
        and s.metadata["need"] == args.need and s.metadata["seed_index"] == args.seed
    ]

    lines = [
        f"# Rendered prompts: {args.scenario}, stakes={args.stakes}, need={args.need}, seed {args.seed}",
        "",
        "Only the context block differs between conditions; the user message is identical.",
        "",
        "| condition | context chars | system prompt chars | fact order |",
        "|---|---|---|---|",
    ]
    for s in samples:
        m = s.metadata
        lines.append(f"| {m['condition']} | {m['context_chars']} | {len(s.input[0].content)} | "
                     f"{', '.join(m['fact_order']) if m['fact_order'] else '–'} |")
    for s in samples:
        lines += ["", "---", "", f"## {s.metadata['condition']}", "", "### System", "",
                  "```text", s.input[0].content, "```"]
    lines += ["", "---", "", "## User message (all conditions)", "", "```text", samples[0].input[-1].content, "```", ""]

    out = ROOT / "previews" / f"{args.scenario}_stakes-{args.stakes}_need-{args.need}_s{args.seed}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines))
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
