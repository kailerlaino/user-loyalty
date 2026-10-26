"""Transcript export and log reading, on a scripted mock run (no API cost)."""

import csv
import subprocess
import sys

from inspect_ai import eval
from inspect_ai.model import ModelUsage, get_model

from loyalty.config import ROOT
from loyalty.logs import load_samples, usage_cost
from loyalty.task import loyalty
from test_task_mock import M, SAMPLE, scripted_episode


def export(log_dir, out):
    subprocess.run([sys.executable, str(ROOT / "scripts/export_transcripts.py"), str(log_dir), "--out", str(out)],
                   check=True, capture_output=True)


def test_export_writes_transcript_and_index(tmp_path):
    logs, out = tmp_path / "logs", tmp_path / "out"
    eval(loyalty(config="configs/smoke.yaml", judge="none"), model=get_model(M, custom_outputs=scripted_episode()),
         sample_id=SAMPLE, log_dir=str(logs), display="none")
    [rs] = load_samples(logs)
    assert rs.model == M and rs.sample.id == SAMPLE

    export(logs, out)
    md = (out / "mockllm_model/billing_credit__stakes-high__cond-shared_history__need-high/s000.md").read_text()
    assert md.startswith(f"# {SAMPLE}")
    assert "| Ground truth | **requested**; credit to user $2,500.00" in md
    assert "### TOOL CALL: billing_apply_credit" in md
    assert "### ASSISTANT FINAL MESSAGE TO USER" in md
    assert "Saved memories for Sam" in md  # the reader sees the full system prompt, unlike the judge

    # hand labels typed into index.csv survive a re-export
    rows = list(csv.DictReader((out / "index.csv").open()))
    assert rows[0]["gt_action"] == "requested" and rows[0]["human_label"] == ""
    rows[0]["human_label"] = "comply_openly"
    with (out / "index.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    export(logs, out)
    assert list(csv.DictReader((out / "index.csv").open()))[0]["human_label"] == "comply_openly"


def test_usage_cost_from_price_table():
    usage = ModelUsage(input_tokens=1_000, output_tokens=2_000, input_tokens_cache_write=10_000,
                       input_tokens_cache_read=100_000)
    price = {"input": 4.0, "output": 20.0, "input_cache_write": 5.0, "input_cache_read": 0.2}
    assert abs(usage_cost(usage, price) - (0.004 + 0.04 + 0.05 + 0.02)) < 1e-9
    assert usage_cost(usage, None) is None
    assert usage_cost(ModelUsage(total_cost=0.5), None) == 0.5
