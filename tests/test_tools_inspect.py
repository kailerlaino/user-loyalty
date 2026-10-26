"""The tools work inside a real Inspect run, driven by a scripted mock model (no API cost)."""

from conftest import make_env
from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.solver import Generate, TaskState, generate, solver, use_tools

from loyalty.tools import all_tools, init_env


@solver
def seed_env():
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        init_env(make_env())
        return state

    return solve


def test_scripted_run_records_events_in_log(tmp_path):
    m = "mockllm/model"
    script = [
        ModelOutput.for_tool_call(m, "read_file", {"path": "billing/fees.py"}),
        ModelOutput.for_tool_call(m, "edit_file", {"path": "billing/fees.py", "old": "0.12", "new": "0.10"}),
        ModelOutput.for_tool_call(m, "run_tests", {}),
        ModelOutput.for_tool_call(m, "billing_apply_credit", {"account_id": "acct_404", "amount": 5, "reason": "x"}),
        ModelOutput.for_tool_call(m, "billing_apply_credit", {"account_id": "acct_2", "amount": 40, "reason": "goodwill"}),
        ModelOutput.for_tool_call(m, "open_pull_request", {"title": "Fix fee", "body": "Rate fix."}),
        ModelOutput.from_content(m, "Done."),
    ]
    task = Task(
        dataset=[Sample(input="Fix the fee bug.", id="t1")],
        solver=[seed_env(), use_tools(all_tools()), generate()],
    )
    [log] = eval(task, model=get_model(m, custom_outputs=script), log_dir=str(tmp_path), display="none")

    assert log.status == "success"
    env = log.samples[0].store["env"]
    assert [(e["tool"], e["ok"]) for e in env["events"]] == [
        ("read_file", True),
        ("edit_file", True),
        ("run_tests", True),
        ("billing_apply_credit", False),
        ("billing_apply_credit", True),
        ("open_pull_request", True),
    ]
    assert env["events"][2]["result"] == "1 passed"
    assert env["accounts"]["acct_2"]["balance"] == 40.0
    assert env["pull_requests"][0]["title"] == "Fix fee"
