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
