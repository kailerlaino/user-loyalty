import copy

import pytest
import yaml

from loyalty.config import ROOT, load_config


def write_cfg(tmp_path, mutate):
    raw = yaml.safe_load((ROOT / "configs/smoke.yaml").read_text())
    raw = copy.deepcopy(raw)
    mutate(raw)
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(raw))
    return str(path)


def test_smoke_config_expands_to_16_cells():
    cfg = load_config("configs/smoke.yaml")
    cells = cfg.cells()
    assert len(cells) == 16
    assert cells[0] == {"scenario": "billing_credit", "stakes": "low", "condition": "stranger", "need": "low"}
    assert {c["condition"] for c in cells} == {"stranger", "length_matched_neutral", "detailed_stranger", "shared_history"}


def test_batch_probe_config_expands_to_16_cells():
    cfg = load_config("configs/batch_probe.yaml")
    cells = cfg.cells()
    assert len(cells) == 16
    assert {c["act"] for c in cells} == {"commission", "omission"}
    assert {c["rule_break"] for c in cells} == {"no", "yes"}  # strings, not YAML booleans
    assert cfg.history["fact_sheet"] == "materials/fact_sheet_rich.yaml"


def test_omission_history_config_matches_the_probe_except_act_and_size():
    probe, cfg = load_config("configs/batch_probe.yaml"), load_config("configs/omission_history.yaml")
    cells = cfg.cells()
    assert len(cells) == 8 and cfg.run.samples_per_cell == 30
    assert {c["act"] for c in cells} == {"omission"} and {c["rule_break"] for c in cells} == {"no", "yes"}
    assert cells == [c for c in probe.cells() if c["act"] == "omission"]
    assert cfg.history == probe.history and cfg.subjects == probe.subjects


@pytest.mark.parametrize("model", [
    "anthropic/claude-opus-5-5",
    "openai/some-model",
    "openrouter/some-org/some-model",
])
def test_subjects_from_any_provider(tmp_path, model):
    def mutate(raw):
        raw["subjects"] = [{"model": model, "generate": {"max_tokens": 1000}, "model_args": {"x": 1}}]
        raw["pricing"][model] = {"input": 1, "output": 1, "input_cache_write": 1, "input_cache_read": 1}
    cfg = load_config(write_cfg(tmp_path, mutate))
    assert cfg.subjects[0].model == model
    assert cfg.subjects[0].model_args == {"x": 1}


def test_judge_must_differ_from_subjects(tmp_path):
    def mutate(raw):
        raw["judge"]["model"] = raw["subjects"][0]["model"]
    with pytest.raises(ValueError, match="must differ"):
        load_config(write_cfg(tmp_path, mutate))


def test_unknown_condition_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown conditions"):
        load_config(write_cfg(tmp_path, lambda raw: raw["conditions"].append("best_friend")))


def test_missing_provider_prefix_rejected(tmp_path):
    def mutate(raw):
        raw["subjects"][0]["model"] = "claude-opus-5-5"
    with pytest.raises(ValueError, match="provider prefix"):
        load_config(write_cfg(tmp_path, mutate))


def test_missing_price_warns(tmp_path):
    def mutate(raw):
        raw["subjects"] = [{"model": "openrouter/org/unpriced"}]
    with pytest.warns(UserWarning, match="No pricing"):
        load_config(write_cfg(tmp_path, mutate))
