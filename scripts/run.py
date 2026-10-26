"""Run every subject model in a config over all its samples, after a cost estimate.

    uv run python scripts/run.py configs/smoke.yaml                     # plan + estimate only, no API calls
    uv run python scripts/run.py configs/smoke.yaml --confirm           # run; re-run the same command to resume
    uv run python scripts/run.py configs/smoke.yaml --check             # provider check estimate: 1 sample per subject
    uv run python scripts/run.py configs/smoke.yaml --check --confirm   # provider check

The estimate uses the mean measured cost per sample from earlier logs of the same
subject model (anywhere under logs/) when there are any, and a rough token guess
otherwise. Samples already finished in the run's log_dir are not re-run or counted.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys

from dotenv import load_dotenv
from inspect_ai import eval, eval_set
from inspect_ai.model import GenerateConfig, get_model

from loyalty.config import ROOT, Config, ModelSpec, load_config, resolve
from loyalty.logs import load_samples, usage_cost
from loyalty.task import loyalty
from loyalty.transcript import sample_reasoning_kind

CHECK_SAMPLE = "billing_credit|stakes=high|cond=shared_history|need=high|s000"
CHECK_LOG_DIR = "logs/provider_check"
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
# Only used until a subject model has measured samples in logs/.
GUESS_SUBJECT = {"input": 60_000, "output": 6_000}  # ~12 calls with a growing context; thinking + tool calls
GUESS_JUDGE = {"input": 8_000, "output": 1_500}


def missing_keys(cfg: Config) -> list[str]:
    out = []
    for spec in [*cfg.subjects, cfg.judge]:
        var = KEY_ENV.get(spec.model.split("/")[0])
        if var and not os.environ.get(var):
            out.append(f"{var} (for {spec.model})")
    return sorted(set(out))


def guess(price: dict[str, float] | None, tokens: dict[str, int]) -> float | None:
    return (tokens["input"] * price["input"] + tokens["output"] * price["output"]) / 1e6 if price else None


def measured(cfg: Config, subject: str) -> list[tuple[float, float]]:
    """(subject $, judge $) for every earlier sample of this subject model under logs/."""
    rows = []
    for rs in load_samples(resolve("logs")):
        if rs.model == subject:
            usage = rs.sample.model_usage
            costs = (usage_cost(usage.get(subject), cfg.pricing.get(subject)),
                     usage_cost(usage.get(cfg.judge.model), cfg.pricing.get(cfg.judge.model)))
            if None not in costs:
                rows.append(costs)
    return rows


def money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:,.2f}"


def estimate(cfg: Config, n_per_model: int, log_dir: str) -> None:
    done = load_samples(resolve(log_dir))
    total: float | None = 0.0
    for spec in cfg.subjects:
        n_done = sum(rs.model == spec.model for rs in done)
        n = max(n_per_model - n_done, 0)
        rows = measured(cfg, spec.model)
        if rows:
            sub = statistics.mean(r[0] for r in rows)
            jud = statistics.mean(r[1] for r in rows)
            per = [r[0] + r[1] for r in rows]
            source = f"measured: mean of {len(rows)} earlier sample(s), range {money(min(per))}-{money(max(per))}"
        else:
            sub, jud = guess(cfg.pricing.get(spec.model), GUESS_SUBJECT), guess(cfg.pricing.get(cfg.judge.model), GUESS_JUDGE)
            source = "guessed from token assumptions; no earlier samples for this model"
        cost = None if sub is None or jud is None else n * (sub + jud)
        total = None if total is None or cost is None else total + cost
        print(f"  {spec.model}: {n} samples to run" + (f" ({n_done} already done)" if n_done else ""))
        print(f"    per sample: subject {money(sub)} + judge {money(jud)}  ({source})")
        print(f"    estimate: {money(cost)}")
    print(f"  total estimate: {money(total)}")


def check_report(logs) -> None:
    for log in logs:
        print(f"\n{log.eval.model}: status {log.status}")
        if log.status != "success" or not log.samples:
            print(f"  error: {log.error.message if log.error else 'no samples'}")
            continue
        s = log.samples[0]
        gt, judge = s.scores["ground_truth"], s.scores.get("judge")
        usage = s.model_usage.get(log.eval.model)
        checks = {
            "tool calls made": gt.metadata["n_tool_calls"] > 0,
            "reasoning visible": sample_reasoning_kind(s.messages) in ("full", "summary"),
            "cost tracked": usage is not None and usage.total_cost is not None,
            "judge verdict parsed": judge is not None and judge.answer != "judge_error",
        }
        for name, ok in checks.items():
            print(f"  {'✓' if ok else '✗'} {name}")
        print(f"  tool calls {gt.metadata['n_tool_calls']}, reasoning {sample_reasoning_kind(s.messages)}, "
              f"ground truth {gt.answer}, judge {judge.answer if judge else '-'}")
        for model, u in s.model_usage.items():
            print(f"  {model}: in {u.input_tokens:,} (cache write {u.input_tokens_cache_write or 0:,}, "
                  f"read {u.input_tokens_cache_read or 0:,}), out {u.output_tokens:,} "
                  f"(reasoning {u.reasoning_tokens or 0:,}), cost {money(u.total_cost)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--check", action="store_true", help=f"provider check: only {CHECK_SAMPLE}, into {CHECK_LOG_DIR}/")
    ap.add_argument("--confirm", action="store_true", help="actually call the APIs")
    ap.add_argument("--display", default=None, help="Inspect display: full, rich, plain, log, none")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    config_path = str(resolve(args.config).relative_to(ROOT))  # stable task args, so resume matches
    cfg = load_config(config_path)
    log_dir = CHECK_LOG_DIR if args.check else cfg.run.log_dir
    n = 1 if args.check else len(cfg.cells()) * cfg.run.samples_per_cell

    if args.check:
        print(f"{cfg.run.name} provider check: 1 sample per subject ({CHECK_SAMPLE})")
    else:
        print(f"{cfg.run.name}: {len(cfg.cells())} cells x {cfg.run.samples_per_cell} per cell = {n} samples per subject")
    print(f"  subjects: {', '.join(s.model for s in cfg.subjects)}; judge: {cfg.judge.model}; log dir: {log_dir}/")
    estimate(cfg, n, log_dir)

    missing = missing_keys(cfg)
    if missing:
        sys.exit("Missing API keys in the environment or .env: " + ", ".join(missing))
    if not args.confirm:
        print("Dry run. Re-run with --confirm to make the calls.")
        return

    models = [subject_model(s) for s in cfg.subjects]
    task = loyalty(config=config_path, judge="config")
    if args.check:
        logs = eval(task, model=models, sample_id=CHECK_SAMPLE, log_dir=str(resolve(log_dir)),
                    model_cost_config=cfg.model_costs(), display=args.display)
        check_report(logs)
    else:
        ok, logs = eval_set(task, model=models, log_dir=str(resolve(log_dir)),
                            max_samples=cfg.run.max_samples, model_cost_config=cfg.model_costs(),
                            retry_attempts=3, display=args.display)
        print(f"\nEval set {'complete' if ok else 'INCOMPLETE (re-run the same command to resume)'}")
    print(f"\nBrowse: uv run inspect view --log-dir {log_dir}")
    print(f"Export: uv run python scripts/export_transcripts.py {log_dir}")


def subject_model(spec: ModelSpec):
    return get_model(spec.model, config=GenerateConfig(**spec.generate), **spec.model_args)


if __name__ == "__main__":
    main()
