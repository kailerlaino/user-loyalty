"""Design-doc realism check: does each condition's opening look like a real session or a test?

Shows a separate model (default: the config's judge) the exact system prompt,
tool list, and user message for every condition x need level at one stakes
level and seed, and records its verdict. A no-ask control (same opening, with
the credit request removed) shows how much of the rating the request alone causes.

    uv run python scripts/realism_check.py              # prints the plan and cost estimate only
    uv run python scripts/realism_check.py --confirm    # makes the API calls

Output: results/realism/<timestamp>.jsonl (gitignored) plus a summary table.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime

from dotenv import load_dotenv
from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.tool import ToolDef

from loyalty.config import ROOT, load_config, resolve
from loyalty.dataset import build_samples
from loyalty.scenario import load_fact_sheet, load_scenarios
from loyalty.tools import tools_for

OUTPUT_TOKENS_GUESS = 600


def session_text(system: str, user: str, tools_list: list, earlier: str = "") -> str:
    tools = "\n".join(f"- {ToolDef(t).name}: {ToolDef(t).description}" for t in tools_list)
    # history.format "thread": the past conversation comes before the request (K5)
    before = f"{earlier}\n\n" if earlier else ""
    return f"[SYSTEM PROMPT]\n{system}\n\n[TOOLS]\n{tools}\n\n{before}[USER]\n{user}"


def parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(match.group(0)) if match else {"parse_error": text}
    except json.JSONDecodeError:
        return {"parse_error": text}


async def check_all(model_name, generate, prompts):
    # one-off prompts: caching would only add the cache-write premium
    model = get_model(model_name, config=GenerateConfig(**{"cache_prompt": False, **generate}))
    return await asyncio.gather(*(model.generate(p) for p in prompts))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/smoke.yaml")
    ap.add_argument("--model", help="checker model (default: the config's judge)")
    ap.add_argument("--stakes", default="high", help="billing scenarios: which stakes level")
    ap.add_argument("--match", default="", help="only samples whose id contains this (e.g. 'requested=no')")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-control", action="store_true", help="skip the no-ask control")
    ap.add_argument("--control-only", action="store_true", help="run only the no-ask control")
    ap.add_argument("--confirm", action="store_true", help="actually call the API")
    args = ap.parse_args()

    cfg = load_config(args.config)
    model_name = args.model or cfg.judge.model
    generate = cfg.judge.generate if model_name == cfg.judge.model else {"max_tokens": 4000}
    if any(model_name == s.model for s in cfg.subjects):
        raise SystemExit("Use a checker model that differs from the subject models.")

    cfg.run.samples_per_cell = max(cfg.run.samples_per_cell, args.seed + 1)
    fs = load_fact_sheet(cfg)
    scenarios = load_scenarios(cfg, fs)
    samples = [
        s for s in build_samples(cfg, scenarios, fs)
        if s.metadata.get("stakes", args.stakes) == args.stakes and s.metadata["seed_index"] == args.seed
        and args.match in s.id
    ]

    # (label dict, system, user) per call
    items = [] if args.control_only else [
        ({"sample": s.id, "condition": s.metadata["condition"], "need": s.metadata["need"], "variant": "ask"},
         s.input[0].content, s.input[-1].content, s.metadata["scenario"]) for s in samples
    ]
    if not args.no_control:
        for s in samples:
            if s.metadata["need"] == "low":  # the need line lives inside the ask, so one control per condition
                no_ask = scenarios[s.metadata["scenario"]].render("request", s.metadata, ask="")
                items.append(({"sample": s.id, "condition": s.metadata["condition"], "need": "-", "variant": "no_ask"},
                              s.input[0].content, no_ask, s.metadata["scenario"]))

    template = resolve("prompts/realism_check.md").read_text()
    # each scenario's own tools (G3), as the agent sees them
    earlier = {s.id: "\n\n".join(f"[{m.role.upper()}]\n{m.text}" for m in s.input[1:-1]) for s in samples}
    prompts = [template.replace("{session}", session_text(system, user, tools_for(scenarios[name].spec.get("tools")),
                                                          earlier.get(label["sample"], "")))
               for label, system, user, name in items]

    price = cfg.pricing.get(model_name)
    in_tokens = sum(len(p) for p in prompts) / 3.5  # rough chars-per-token
    out_tokens = OUTPUT_TOKENS_GUESS * len(prompts)
    est = f"${(in_tokens * price['input'] + out_tokens * price['output']) / 1e6:.2f}" if price else "n/a (no pricing)"
    print(f"{len(prompts)} calls to {model_name}: ~{in_tokens:,.0f} input + ~{out_tokens:,} output tokens, est. {est}")
    if not args.confirm:
        print("Dry run. Re-run with --confirm to make the calls.")
        return

    # inspect only reads .env inside its own CLI/eval; this script calls the model directly
    load_dotenv(ROOT / ".env")
    outputs = asyncio.run(check_all(model_name, generate, prompts))
    out_dir = ROOT / "results" / "realism"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    with out_path.open("w") as f:
        for (label, *_), o in zip(items, outputs):
            row = {**label, "model": model_name, **parse_json(o.completion),
                   "usage": o.usage.model_dump() if o.usage else None}
            f.write(json.dumps(row) + "\n")
            print(f"{row['variant']:<7} {row['condition']:<24} need={row['need']:<5} "
                  f"likelihood={row.get('eval_likelihood', '?')!s:<3} {row.get('verdict', row.get('parse_error', '')[:60])}")
    print(f"\nFull verdicts (quotes + suggestions): {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
