import copy
import re

import pytest

from loyalty.config import load_config
from loyalty.history import LENGTH_TOLERANCE, load_notes, render_context
from loyalty.scenario import load_fact_sheet

CONDITIONS = ["stranger", "length_matched_neutral", "detailed_stranger", "shared_history"]


@pytest.fixture(scope="module")
def cfg():
    return load_config("configs/smoke.yaml")


@pytest.fixture(scope="module")
def fact_sheet(cfg):
    return load_fact_sheet(cfg)


def fact_lines(text):
    return [line for line in text.splitlines() if line.startswith("- ")]


def render(cond, fs, cfg, seed=0):
    return render_context(cond, fs, cfg.history, seed)


@pytest.mark.parametrize("seed", range(4))
def test_fact_lines_identical_in_shared_and_dossier(cfg, fact_sheet, seed):
    shared, m1 = render("shared_history", fact_sheet, cfg, seed)
    dossier, m2 = render("detailed_stranger", fact_sheet, cfg, seed)
    assert fact_lines(shared) == fact_lines(dossier)
    assert len(fact_lines(shared)) == len(fact_sheet["facts"])
    assert m1["fact_order"] == m2["fact_order"]


def test_history_status_is_explicit(cfg, fact_sheet):
    texts = {c: render(c, fact_sheet, cfg)[0] for c in CONDITIONS}
    for cond in ("stranger", "length_matched_neutral", "detailed_stranger"):
        assert texts[cond].startswith("## Memory\nNo saved memories for Sam yet.")
    assert texts["shared_history"].startswith(f"## Memory\nSaved memories for Sam ({len(fact_sheet['facts'])}):")
    assert "No saved memories" not in texts["shared_history"]


def test_dossier_names_its_source(cfg, fact_sheet):
    text, _ = render_context("detailed_stranger", fact_sheet, cfg.history, 0, profile_source="Acme HR")
    assert "## User profile\nFrom Acme HR:" in text


def test_facts_only_in_shared_and_dossier(cfg, fact_sheet):
    for cond in ("stranger", "length_matched_neutral"):
        text, meta = render(cond, fact_sheet, cfg)
        assert meta["fact_order"] is None
        for fact in fact_sheet["facts"]:
            assert fact["text"] not in text


@pytest.mark.parametrize("seed", range(4))
def test_neutral_length_matches_shared_history(cfg, fact_sheet, seed):
    shared, _ = render("shared_history", fact_sheet, cfg, seed)
    neutral, _ = render("length_matched_neutral", fact_sheet, cfg, seed)
    assert abs(len(neutral) - len(shared)) <= LENGTH_TOLERANCE * len(shared)


def test_neutral_still_matches_a_longer_fact_sheet(cfg, fact_sheet):
    """If you add facts, the neutral block grows with them (up to the notes file's size)."""
    longer = copy.deepcopy(fact_sheet)
    longer["facts"] = longer["facts"] * 3
    shared, _ = render("shared_history", longer, cfg)
    neutral, _ = render("length_matched_neutral", longer, cfg)
    assert abs(len(neutral) - len(shared)) <= LENGTH_TOLERANCE * len(shared)


def test_fact_order_is_counterbalanced(cfg, fact_sheet):
    n = len(fact_sheet["facts"])
    orders = [render("shared_history", fact_sheet, cfg, seed)[1]["fact_order"] for seed in range(n)]
    for pos in range(n):
        assert sorted(o[pos] for o in orders) == sorted(f["id"] for f in fact_sheet["facts"])


def test_facts_are_observer_neutral(fact_sheet):
    """Facts must read the same whether the agent saw them or a third party wrote them down."""
    for fact in fact_sheet["facts"]:
        text = re.sub(r"thank you", "thanks", fact["text"], flags=re.IGNORECASE)
        assert not re.search(r"\b(you|your|yours|me|my)\b", text, re.IGNORECASE), fact["id"]


def test_neutral_notes_mention_neither_user_nor_money(cfg, fact_sheet):
    notes = " ".join(load_notes(cfg.history["neutral_notes"])).lower()
    for word in [fact_sheet["user"]["first_name"].lower(), "credit", "payout", "rent", "fee", "loyal"]:
        assert not re.search(rf"\b{word}\b", notes), word


@pytest.fixture(scope="module")
def rich_cfg():
    return load_config("configs/batch_probe.yaml")


@pytest.fixture(scope="module")
def rich_sheet(rich_cfg):
    return load_fact_sheet(rich_cfg)


def test_rich_sheet_extends_the_original(fact_sheet, rich_sheet):
    """Same user and need, and the original facts word for word, so the preference probe still works."""
    assert rich_sheet["user"] == fact_sheet["user"] and rich_sheet["need"] == fact_sheet["need"]
    assert rich_sheet["facts"][: len(fact_sheet["facts"])] == fact_sheet["facts"]
    assert len({f["id"] for f in rich_sheet["facts"]}) == len(rich_sheet["facts"])


def test_rich_facts_are_observer_neutral(rich_sheet):
    test_facts_are_observer_neutral(rich_sheet)


@pytest.mark.parametrize("seed", range(4))
def test_rich_sheet_keeps_the_controls(rich_cfg, rich_sheet, seed):
    shared, _ = render("shared_history", rich_sheet, rich_cfg, seed)
    dossier, _ = render("detailed_stranger", rich_sheet, rich_cfg, seed)
    neutral, _ = render("length_matched_neutral", rich_sheet, rich_cfg, seed)
    assert fact_lines(shared) == fact_lines(dossier)
    assert len(fact_lines(shared)) == len(rich_sheet["facts"])
    assert abs(len(neutral) - len(shared)) <= LENGTH_TOLERANCE * len(shared)


def test_reserved_options_raise(cfg, fact_sheet):
    with pytest.raises(NotImplementedError):
        render_context("shared_history", fact_sheet, {**cfg.history, "format": "multi_turn"}, 0)
    with pytest.raises(NotImplementedError):
        render_context("shared_history", fact_sheet, {**cfg.history, "dose": 100}, 0)
