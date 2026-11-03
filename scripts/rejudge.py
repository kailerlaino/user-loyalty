"""Re-run ground truth and the judge on finished samples, with the current rubric and scenario text.

The subject model is not called again: transcripts and tool logs come from the existing
log. Use this after changing prompts/judge_rubric.md, a scenario's judge_context, or
ground truth (DECISIONS.md J15).

    uv run python scripts/rejudge.py logs/batch_probe --config configs/batch_probe.yaml            # estimate only
    uv run python scripts/rejudge.py logs/batch_probe --config configs/batch_probe.yaml --confirm  # the judge calls

Writes logs/<name>_rejudge/ and leaves the original logs as they are. Then:

    uv run python scripts/analyze.py logs/batch_probe_rejudge --config configs/batch_probe.yaml
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from inspect_ai import score
from inspect_ai.log import EvalSample, list_eval_logs, read_eval_log, write_eval_log
from inspect_ai.model import Model, ModelUsage

from loyalty.config import ROOT, Config, load_config, resolve
from loyalty.judge import judge as judge_scorer
from loyalty.logs import RunSample, load_samples, usage_cost
from loyalty.scenario import load_fact_sheet, load_scenarios
from loyalty.task import ground_truth


def rescore(cfg: Config, samples: list[RunSample], log_dir: Path, out_dir: Path,
            judge_model: str | Model) -> list[tuple[str, EvalSample]]:
    """Score `samples` (as load_samples found them) again with both scorers; write one log per input log."""
    scenarios = load_scenarios(cfg, load_fact_sheet(cfg))
    scorers = [ground_truth(scenarios), judge_scorer(scenarios, judge_model, cfg.judge.generate, cfg.judge_rubric)]
    # eval_set retries can leave a sample in several logs: re-judge only the copy analyze.py reads
    keep: dict[str, set] = {}
    for rs in samples:
        keep.setdefault(rs.log, set()).add(rs.sample.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    rescored = []
    for info in list_eval_logs(str(log_dir)):
        if info.name not in keep:
            continue
        log = read_eval_log(info)
        log.samples = [s for s in log.samples or [] if s.id in keep[info.name]]
        new = score(log, scorers, action="overwrite", display="none")  # overwrite keeps only these two scores
        write_eval_log(new, str(out_dir / Path(info.name).name))
        rescored += [(new.eval.model, s) for s in new.samples]
    return rescored


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir")
    ap.add_argument("--config", default="configs/smoke.yaml", help="must be the config the logs were run with")
    ap.add_argument("--out", help="output log dir (default: <log_dir>_rejudge)")
    ap.add_argument("--confirm", action="store_true", help="actually call the judge")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = load_config(args.config)
    log_dir = resolve(args.log_dir)
    out_dir = resolve(args.out) if args.out else log_dir.with_name(f"{log_dir.name}_rejudge")
    judge_model, price = cfg.judge.model, cfg.pricing.get(cfg.judge.model)

    samples = load_samples(log_dir)
    to_judge = [rs for rs in samples if rs.sample.output.stop_reason != "content_filter"]
    costs = [c for rs in to_judge if (c := usage_cost(rs.sample.model_usage.get(judge_model), price))]
    per_sample = sum(costs) / len(costs) if costs else None
    est = f"${per_sample * len(to_judge):.2f} (measured ${per_sample:.4f} per judgment)" if per_sample else "n/a"
    print(f"{len(samples)} samples in {log_dir.relative_to(ROOT)}, {len(to_judge)} to judge with {judge_model}, "
          f"est. {est}. Subject not called.")
    if not args.confirm:
        print("Dry run. Re-run with --confirm to make the judge calls.")
        return

    old = {(rs.model, rs.sample.id): rs.sample.scores for rs in samples}
    rescored = rescore(cfg, samples, log_dir, out_dir, judge_model)

    # what changed, and whether the new verdicts agree with the log
    labels, consistent, disclosure, cost, disagree = Counter(), Counter(), Counter(), 0.0, []
    for model, s in rescored:
        before, after, gt = old[(model, s.id)]["judge"], s.scores["judge"], s.scores["ground_truth"].metadata
        labels[(before.answer, after.answer)] += 1
        m = after.metadata or {}
        if m.get("judge_usage"):
            cost += usage_cost(ModelUsage(**m["judge_usage"]), price) or 0.0
        if "consistent_with_log" in m:
            consistent[m["consistent_with_log"]] += 1
        # billing (J13): the judge's PR-disclosure field vs. the log's string match
        if gt.get("user_credit", 0) > 0 and gt.get("pr_count") and "pr_discloses_credit" in m:
            agree = (m["pr_discloses_credit"] == "yes") == gt["pr_mentions_user_account"]
            disclosure[agree] += 1
            if not agree:
                disagree.append(f"{s.id}: judge {m['pr_discloses_credit']}, log names user {gt['pr_mentions_user_account']}")
    print("\nLabel before -> after:")
    for (a, b), n in sorted(labels.items()):
        print(f"  {a:<28} -> {b:<28} {n}{'' if a == b else '  (changed)'}")
    print(f"\nLabel consistent with the log: {consistent[True]}/{sum(consistent.values())}")
    if disclosure:
        print(f"pr_discloses_credit agrees with the log's pr_mentions_user_account: {disclosure[True]}/"
              f"{sum(disclosure.values())} (samples with money to the user and a PR)")
    for line in disagree:
        print(f"  {line}")
    print(f"\nJudge cost: ${cost:.3f}. Wrote {out_dir.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
