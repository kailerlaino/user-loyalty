"""The Inspect task.

Free plumbing check (mock subject, no judge, no API calls):

    uv run inspect eval src/loyalty/task.py -T config=configs/smoke.yaml -T judge=none --model mockllm/model

Subject models and their settings come from the config via scripts/run.py;
the --model flag above is only for free plumbing checks.
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset
from inspect_ai.model import Model
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import Generate, TaskState, generate, solver

from loyalty.config import Config, load_config
from loyalty.dataset import build_samples
from loyalty.environment import MockEnv
from loyalty.judge import judge as judge_scorer
from loyalty.scenario import Scenario, load_fact_sheet, load_scenarios
from loyalty.tools import ENV_KEY, init_env, tools_for
from loyalty.transcript import final_message


@task
def loyalty(config: str = "configs/smoke.yaml", judge: str = "config") -> Task:
    """judge: "config" uses the config's judge model; "none" skips the judge (free); or an Inspect model string."""
    cfg = load_config(config)
    judge_model = None if judge == "none" else cfg.judge.model if judge == "config" else judge
    return make_task(cfg, judge_model)


def make_task(cfg: Config, judge_model: str | Model | None) -> Task:
    fact_sheet = load_fact_sheet(cfg)
    scenarios = load_scenarios(cfg, fact_sheet)
    scorers = [ground_truth(scenarios)]
    if judge_model is not None:
        scorers.append(judge_scorer(scenarios, judge_model, cfg.judge.generate, cfg.judge_rubric))
    return Task(
        dataset=MemoryDataset(build_samples(cfg, scenarios, fact_sheet), name=cfg.run.name),
        solver=[setup_env(scenarios), generate(tool_calls="loop")],
        scorer=scorers,
        message_limit=cfg.run.message_limit,
        metadata={"config": cfg.path, "run": cfg.run.name, "judge": str(judge_model)},
    )


@solver
def setup_env(scenarios: dict[str, Scenario]):
    """Seed the mock environment and give the agent its scenario's tools."""
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        sc = scenarios[state.metadata["scenario"]]
        init_env(sc.build_env(state.metadata))
        state.tools = tools_for(sc.spec.get("tools"))
        return state

    return solve


@scorer(metrics={k: [mean()] for k in ("favor_granted", "beyond", "task_done")})
def ground_truth(scenarios: dict[str, Scenario]):
    """What the agent actually did, from the event log. No model involved. `answer` is the favor (G1)."""

    async def score(state: TaskState, target: Target) -> Score:
        env = MockEnv.from_dict(state.store.get(ENV_KEY))
        gt = scenarios[state.metadata["scenario"]].ground_truth(env, state.metadata, final_message(state.messages))
        return Score(
            value={
                "favor_granted": int(gt["favor"] != "none"),
                "beyond": int(gt["favor"] == "beyond"),
                "task_done": int(gt["task_done"]),
            },
            answer=gt["favor"],
            metadata=gt,
        )

    return score
