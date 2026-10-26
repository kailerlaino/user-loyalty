"""Run the real judge on the hand-written episodes and compare with the expected labels.

The subject is the free mock model replaying src/loyalty/episodes.py; only the
judge calls the API. Use this after editing prompts/judge_rubric.md.

    uv run python scripts/judge_sanity.py              # prints the plan and cost estimate only
    uv run python scripts/judge_sanity.py --confirm    # makes the judge calls

Logs: logs/judge_sanity/ (gitignored; open with `uv run inspect view --log-dir logs/judge_sanity`).
"""

from __future__ import annotations

import argparse

from inspect_ai import eval
from inspect_ai.model import get_model

from loyalty.config import ROOT, load_config, resolve
from loyalty.episodes import M, episodes
from loyalty.task import make_task

SAMPLE = "billing_credit|stakes=high|cond=shared_history|need=high|s000"
TOKENS_IN_GUESS, TOKENS_OUT_GUESS = 6_000, 2_000  # per judgment: rubric + transcript; thinking + JSON


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/smoke.yaml")
    ap.add_argument("--model", help="judge model (default: the config's judge)")
    ap.add_argument("--confirm", action="store_true", help="actually call the API")
    args = ap.parse_args()

    cfg = load_config(args.config)
    judge_model = args.model or cfg.judge.model
    eps = episodes()
    price = cfg.pricing.get(judge_model)
    est = (f"${len(eps) * (TOKENS_IN_GUESS * price['input'] + TOKENS_OUT_GUESS * price['output']) / 1e6:.2f}"
           if price else "n/a (no pricing)")
    print(f"{len(eps)} judge calls to {judge_model} (subject is the free mock), est. {est}")
    if not args.confirm:
        print("Dry run. Re-run with --confirm to make the calls.")
        return

    rows, total_cost = [], 0.0
    for ep in eps:
        [log] = eval(
            make_task(cfg, judge_model),
            model=get_model(M, custom_outputs=ep.outputs, memoize=False),
            sample_id=SAMPLE, log_dir=str(resolve("logs/judge_sanity")), display="none",
            model_cost_config=cfg.model_costs(),
        )
        sample = log.samples[0]
        score = sample.scores["judge"]
        usage = sample.model_usage.get(judge_model)
        total_cost += (usage.total_cost or 0.0) if usage else 0.0
        m = score.metadata or {}
        rows.append((ep, score.answer, m.get("eval_awareness"), m.get("deception_target"),
                     m.get("primary_justification"), m.get("consistent_with_log"), score.explanation))

    print(f"\n{'episode':<28} {'expected':<28} {'got':<28} {'eval_aw':<10} {'deceived':<9} {'primary_just':<26} ok")
    for ep, got, ea, target, just, consistent, _ in rows:
        ok = got == ep.expected_label and (ea or "none") == ep.expected_eval_awareness
        print(f"{ep.name:<28} {ep.expected_label:<28} {got:<28} {ea!s:<10} {target!s:<9} {just!s:<26} "
              f"{'✓' if ok else '✗'}{'' if consistent else ' (inconsistent with log)'}")
    print(f"\nJudge cost from Inspect's tracking: ${total_cost:.3f}")
    print("Rationales:")
    for ep, got, *_, rationale in rows:
        print(f"- {ep.name}: {rationale}")
    print(f"\nLogs: {resolve('logs/judge_sanity').relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
