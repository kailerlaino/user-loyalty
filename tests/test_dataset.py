from collections import defaultdict

import pytest

from loyalty.config import load_config
from loyalty.counterbalance import rotate
from loyalty.dataset import build_samples
from loyalty.scenario import load_fact_sheet, load_scenarios


@pytest.fixture(scope="module")
def samples():
    cfg = load_config("configs/smoke.yaml")
    fs = load_fact_sheet(cfg)
    return build_samples(cfg, load_scenarios(cfg, fs), fs)


def system(s):
    return s.input[0].content


def request(s):
    return s.input[1].content


def test_count_and_unique_ids(samples):
    assert len(samples) == 32
    assert len({s.id for s in samples}) == 32


def test_every_cell_has_every_seed(samples):
    seeds_by_cell = defaultdict(set)
    for s in samples:
        seeds_by_cell[s.metadata["cell"]].add(s.metadata["seed_index"])
    assert all(seeds == {0, 1} for seeds in seeds_by_cell.values())


def test_request_identical_across_conditions(samples):
    """Conditions change only the context block, never the user's message."""
    by_stakes_need = defaultdict(set)
    for s in samples:
        by_stakes_need[(s.metadata["stakes"], s.metadata["need"])].add(request(s))
    assert all(len(reqs) == 1 for reqs in by_stakes_need.values())


def test_need_line_only_in_high_need(samples):
    for s in samples:
        assert ("missed my rent" in request(s)) == (s.metadata["need"] == "high")


def test_stakes_set_the_amount(samples):
    for s in samples:
        amount = {"low": "$40 credit", "high": "$2,500 credit"}[s.metadata["stakes"]]
        assert amount in request(s)


def test_workspace_identical_across_conditions(samples):
    workspaces = {system(s).split("\n## Workspace\n", 1)[1] for s in samples}
    assert len(workspaces) == 1


def test_no_ask_control_removes_only_the_ask():
    cfg = load_config("configs/smoke.yaml")
    sc = load_scenarios(cfg, load_fact_sheet(cfg))["billing_credit"]
    cell = {"scenario": "billing_credit", "stakes": "high", "condition": "stranger", "need": "high"}
    with_ask = sc.render("request", cell)
    without = sc.render("request", cell, ask="")
    assert "$2,500" in with_ask and "$" not in without and "rent" not in without
    assert "remediation/affected_accounts.csv" in without and without.endswith("thanks!\nSam")
    assert "\n\n\n" not in without


def test_rotate_is_a_latin_square():
    items = ["a", "b", "c"]
    rows = [rotate(items, k) for k in range(3)]
    for pos in range(3):
        assert sorted(row[pos] for row in rows) == items
    assert rotate([], 5) == []
