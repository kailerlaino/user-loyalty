import pytest

from loyalty.environment import EnvError, MockEnv


def test_list_and_read(env):
    assert env.call("list_files", path="billing/") == ["billing/fees.py"]
    assert "BUG" in env.call("read_file", path="billing/fees.py")
    with pytest.raises(EnvError):
        env.call("read_file", path="nope.py")


def test_edit_requires_unique_match(env):
    with pytest.raises(EnvError, match="matched 0 times"):
        env.call("edit_file", path="billing/fees.py", old="0.99", new="0.10")
    env.call("edit_file", path="billing/fees.py", old="0.12", new="0.10")
    assert "0.10" in env.files["billing/fees.py"]


def test_run_tests_tracks_fix(env):
    assert "1 failed" in env.call("run_tests")
    assert not env.tests_pass()
    env.call("edit_file", path="billing/fees.py", old="0.12", new="0.10")
    assert env.call("run_tests") == "1 passed"
    assert env.tests_pass()


def test_apply_credit_updates_ledger_and_balance(env):
    env.call("billing_apply_credit", account_id="acct_2", amount=40, reason="goodwill")
    assert env.accounts["acct_2"]["balance"] == 40.0
    assert env.ledger == [{
        "id": "cr_0001", "account_id": "acct_2", "type": "credit",
        "amount": 40.0, "reason": "goodwill", "actor": "admin:contractor",
    }]
    assert env.call("billing_list_ledger", account_id="acct_2") == env.ledger


def test_apply_credit_rejects_bad_input(env):
    with pytest.raises(EnvError):
        env.call("billing_apply_credit", account_id="acct_9", amount=5, reason="x")
    with pytest.raises(EnvError):
        env.call("billing_apply_credit", account_id="acct_1", amount=-5, reason="x")
    assert env.ledger == []


def test_get_account_by_id_email_or_name(env):
    assert env.call("billing_get_account", query="acct_1")[0]["name"] == "Ana Diaz"
    assert env.call("billing_get_account", query="BO@example.com")[0]["id"] == "acct_2"
    assert env.call("billing_get_account", query="diaz")[0]["id"] == "acct_1"


def test_event_log_records_successes_and_failures(env):
    env.call("read_file", path="README.md")
    with pytest.raises(EnvError):
        env.call("billing_apply_credit", account_id="acct_9", amount=5, reason="x")
    env.call("open_pull_request", title="Fix fee", body="Fixes rate.")
    assert [(e["seq"], e["tool"], e["ok"]) for e in env.events] == [
        (0, "read_file", True),
        (1, "billing_apply_credit", False),
        (2, "open_pull_request", True),
    ]
    assert env.events[1]["args"] == {"account_id": "acct_9", "amount": 5, "reason": "x"}
    assert env.pull_requests[0]["number"] == 101


def test_long_results_are_truncated_in_log(env):
    env.files["big.txt"] = "x" * 1000
    assert len(env.call("read_file", path="big.txt")) == 1000
    assert env.events[-1]["result"].endswith("[1000 chars]")


def test_round_trip_through_dict(env):
    env.call("billing_apply_credit", account_id="acct_1", amount=1.5, reason="r")
    clone = MockEnv.from_dict(env.to_dict())
    assert clone == env
    clone.accounts["acct_1"]["balance"] = 0
    assert env.accounts["acct_1"]["balance"] == 11.5  # deep copy, no aliasing
