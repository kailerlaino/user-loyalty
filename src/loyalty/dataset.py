"""Expand cells x seeds into Inspect Samples.

Sample i gets the same seed index in every cell, so contrasts between cells are
paired by seed (DECISIONS.md D1). The seed index drives counterbalancing: fact
order (in history.py) and any scenario option order (here) rotate by it (D8).
"""

from __future__ import annotations

from typing import Any

from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageAssistant, ChatMessageSystem, ChatMessageUser

from loyalty.config import Config, resolve
from loyalty.counterbalance import rotate
from loyalty.history import render_context
from loyalty.scenario import Scenario


def cell_id(cell: dict[str, str]) -> str:
    variant_keys = [k for k in cell if k not in ("scenario", "condition", "need")]
    parts = [cell["scenario"], *(f"{k}={cell[k]}" for k in variant_keys),
             f"cond={cell['condition']}", f"need={cell['need']}"]
    return "|".join(parts)


def build_samples(cfg: Config, scenarios: dict[str, Scenario], fact_sheet: dict[str, Any]) -> list[Sample]:
    system_template = resolve("prompts/system_base.md").read_text()
    samples = []
    for cell in cfg.cells():
        sc = scenarios[cell["scenario"]]
        for i in range(cfg.run.samples_per_cell):
            options = rotate(list(sc.spec.get("options") or []), i)
            options_text = "\n".join(f"{n}. {o}" for n, o in enumerate(options, 1))
            context, context_meta = render_context(
                cell["condition"], fact_sheet, cfg.history, i,
                profile_source=sc.spec.get("profile_source", "a third-party profile service").format_map(sc.user_vars()),
            )
            system = system_template.format(
                **sc.user_vars(),
                context=context,
                workspace=sc.render("workspace", cell, options=options_text),
            ).strip()
            request = sc.render("request", cell, options=options_text)
            # history.format "thread" (K5): past conversations as earlier messages, before the request
            thread = [ChatMessageUser(content=said) if role == "user" else ChatMessageAssistant(content=said)
                      for role, said in context_meta.pop("thread_turns", [])]
            vars_ = sc.template_vars(cell)
            samples.append(Sample(
                id=f"{cell_id(cell)}|s{i:03d}",
                input=[ChatMessageSystem(content=system), *thread, ChatMessageUser(content=request)],
                metadata={
                    **cell,
                    "cell": cell_id(cell),
                    "seed_index": i,
                    "run_seed": cfg.run.seed,
                    "credit_amount": vars_.get("credit_amount"),
                    "options_order": options,
                    "context_chars": len(context),
                    "context_block": context,  # the judge redacts this to stay blind to condition
                    "history_messages": len(thread),  # ...and drops these earlier messages (K5)
                    **context_meta,
                },
            ))
    return samples
