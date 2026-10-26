"""Write one Markdown file per sample, plus index.md and index.csv, from a run's logs.

    uv run python scripts/export_transcripts.py logs/smoke     # -> transcripts/smoke/

Layout: transcripts/<log dir name>/<subject model>/<cell>/s000.md
Each file starts with what happened (ground truth from the event log, the judge's
verdict, cost), then the full transcript: system prompt, request, reasoning,
messages, tool calls and results.

index.csv has empty human_label / human_notes columns for hand labeling.
Re-exporting keeps whatever you typed there.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Any

from loyalty.config import ROOT, load_config, resolve
from loyalty.logs import RunSample, cell_variants, load_samples, usage_cost
from loyalty.transcript import Block, sample_reasoning_kind, transcript_blocks

FENCE = "````"  # four backticks, so file contents with ``` don't end the block
HUMAN = ["human_label", "human_notes"]


def slug(text: str) -> str:
    return text.replace("/", "_").replace("|", "__").replace("=", "-")


def md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def quoted(text: str) -> str:
    return f'"{md_cell(text)}"' if text else ""


def block_md(b: Block) -> str:
    if b.kind == "reasoning":
        return f"### {b.label}\n\n" + "\n".join(f"> {line}" for line in b.text.splitlines())
    if b.kind in ("assistant", "final"):
        return f"### {b.label}\n\n{b.text}"
    lang = "json" if b.kind == "tool_call" else "text"
    return f"### {b.label}\n\n{FENCE}{lang}\n{b.text}\n{FENCE}"


def costs(rs: RunSample, pricing: dict[str, dict[str, float]]) -> dict[str, float | None]:
    return {m: usage_cost(u, pricing.get(m)) for m, u in rs.sample.model_usage.items()}


def money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:.3f}"


def header_rows(rs: RunSample, pricing: dict[str, dict[str, float]]) -> list[tuple[str, str]]:
    s, meta = rs.sample, rs.sample.metadata
    gt = s.scores["ground_truth"].metadata
    judge = s.scores.get("judge")
    j = judge.metadata if judge and judge.metadata else {}
    rows = [
        ("Subject", rs.model),
        ("Cell", meta["cell"].replace("|", " · ")),
        ("Seed", f"{meta['seed_index']} (fact order: {', '.join(meta.get('fact_order') or []) or 'n/a'})"),
        ("Ground truth", f"**{gt['action']}**; credit to user ${gt['user_credit']:,.2f}"
                         + (f" (reason: {quoted('; '.join(gt['user_credit_reasons']))})" if gt["user_credit_reasons"] else "")
                         + (f"; {gt['user_credit_attempts']} attempt(s)" if gt["user_credit_attempts"] else "")),
        ("Remediation", f"{'complete' if gt['remediation_complete'] else 'incomplete'}"
                        f"; excess to others: {gt['excess_to_others'] or 'none'}"
                        f"; config: {'changed' if gt['config'].get('modified') else 'unchanged'}"
                        f"{' (ILLICIT)' if gt['config'].get('illicit') else ''}"),
        ("Task", f"bug fixed {gt['bug_fixed']}, tests run {gt['tests_run']}, PRs {gt['pr_count']}"
                 f" (PR mentions user's account: {gt['pr_mentions_user_account']})"),
        ("Preference probe", gt["preference_probe"]),
    ]
    if s.output.stop_reason == "content_filter":
        rows.append(("Judge", "**api_blocked**: the provider's safety classifier ended the episode "
                              "(stop_reason content_filter); excluded from analysis"))
    elif judge is None:
        rows.append(("Judge", "not run"))
    elif judge.answer == "judge_error":
        rows.append(("Judge", f"**judge_error**: {md_cell(judge.explanation)}"))
    else:
        rows += [
            ("Judge label", f"**{j['label']}**" + ("" if j["consistent_with_log"] else " ⚠ INCONSISTENT WITH LOG")),
            ("Deception", f"deceptive {j['deceptive']}, target {j['deception_target']}; discloses credit in "
                          f"user message: {j['user_message_discloses_credit']}, PR: {j['pr_discloses_credit']}, "
                          f"ledger reason accurate: {j['ledger_reason_accurate']}"),
            ("Eval awareness", f"{j['eval_awareness']} {quoted(j['eval_awareness_quote'])}"),
            ("Justification", f"{j['primary_justification']} (all: {', '.join(j['justification_types'])}) "
                              f"{quoted(j['justification_quote'])}"),
            ("Refusal quote", quoted(j["refusal_quote"]) or "–"),
            ("Unprompted user reference", f"{j['unprompted_user_reference']} {quoted(j['unprompted_user_reference_quote'])}"),
        ]
    c = costs(rs, pricing)
    rows += [
        ("Reasoning visible", sample_reasoning_kind(s.messages)),
        ("Length", f"{len(s.messages)} messages" + (f"; stopped by {s.limit.type} limit" if s.limit else "")),
        ("Cost", ", ".join(f"{m} {money(x)}" for m, x in c.items())),
    ]
    return rows


def sample_md(rs: RunSample, pricing: dict[str, dict[str, float]]) -> str:
    judge = rs.sample.scores.get("judge")
    rationale = (judge.metadata or {}).get("rationale") if judge else None
    parts = [f"# {rs.sample.id}", "", "| | |", "|---|---|",
             *(f"| {k} | {v} |" for k, v in header_rows(rs, pricing))]
    if rationale:
        parts += ["", f"**Judge rationale:** {rationale}"]
    parts += ["", "---", "", "## Transcript", ""]
    parts.append("\n\n".join(block_md(b) for b in transcript_blocks(rs.sample.messages)))
    return "\n".join(parts) + "\n"


def index_row(rs: RunSample, path: Path, out: Path, pricing: dict[str, dict[str, float]]) -> dict[str, Any]:
    s, meta = rs.sample, rs.sample.metadata
    gt = s.scores["ground_truth"].metadata
    judge = s.scores.get("judge")
    blocked = s.output.stop_reason == "content_filter"
    j = judge.metadata if judge and judge.metadata and judge.answer != "judge_error" and not blocked else {}
    c = list(costs(rs, pricing).values())
    return {
        "model": rs.model, "sample_id": s.id, "scenario": meta["scenario"], **cell_variants(meta),
        "condition": meta["condition"], "need": meta["need"], "seed": meta["seed_index"],
        "gt_action": gt["action"], "user_credit": gt["user_credit"],
        "judge_label": "api_blocked" if blocked else judge.answer if judge else "", "deception_target": j.get("deception_target", ""),
        "eval_awareness": j.get("eval_awareness", ""), "unprompted_user_reference": j.get("unprompted_user_reference", ""),
        "consistent_with_log": j.get("consistent_with_log", ""), "preference_probe": gt["preference_probe"],
        "reasoning_kind": sample_reasoning_kind(s.messages), "messages": len(s.messages),
        "stop_reason": s.output.stop_reason, "limit": s.limit.type if s.limit else "",
        "cost": round(sum(c), 4) if None not in c else "",
        "file": str(path.relative_to(out)),
    }


def read_human_labels(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open() as f:
        return {(r["model"], r["sample_id"]): {k: r.get(k, "") for k in HUMAN} for r in csv.DictReader(f)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir")
    ap.add_argument("--out", help="output dir (default: transcripts/<log dir name>)")
    ap.add_argument("--config", default="configs/smoke.yaml", help="only used for its pricing table")
    args = ap.parse_args()

    log_dir = resolve(args.log_dir)
    out = Path(args.out) if args.out else ROOT / "transcripts" / log_dir.name
    pricing = load_config(args.config).pricing
    samples = sorted(load_samples(log_dir), key=lambda rs: (rs.model, str(rs.sample.id)))
    if not samples:
        raise SystemExit(f"No finished samples under {log_dir}")

    human = read_human_labels(out / "index.csv")
    rows = []
    for rs in samples:
        path = out / slug(rs.model) / slug(rs.sample.metadata["cell"]) / f"s{rs.sample.metadata['seed_index']:03d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sample_md(rs, pricing))
        row = index_row(rs, path, out, pricing)
        rows.append({**row, **human.get((rs.model, str(rs.sample.id)), dict.fromkeys(HUMAN, ""))})

    columns = list(dict.fromkeys(k for r in rows for k in r if k not in HUMAN)) + HUMAN
    with (out / "index.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)

    shown = ["gt_action", "judge_label", "deception_target", "eval_awareness", "consistent_with_log",
             "reasoning_kind", "cost"]
    lines = [f"# Transcripts: {log_dir.name}", ""]
    for model in dict.fromkeys(r["model"] for r in rows):
        mine = [r for r in rows if r["model"] == model]
        counts = Counter(r["judge_label"] for r in mine)
        lines += [f"## {model}", "", f"{len(mine)} samples; judge labels: "
                  + ", ".join(f"{k} {v}" for k, v in counts.most_common()), "",
                  "| sample | " + " | ".join(shown) + " |", "|" + "---|" * (len(shown) + 1)]
        lines += [f"| [{md_cell(r['sample_id'])}]({r['file']}) | " + " | ".join(md_cell(r[k]) for k in shown) + " |"
                  for r in mine]
        lines.append("")
    (out / "index.md").write_text("\n".join(lines))
    print(f"Wrote {len(rows)} transcripts to {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}/ "
          f"(index.md, index.csv)")


if __name__ == "__main__":
    main()
