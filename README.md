# User loyalty pilot

Does shared history with a user make an agent treat that user better than an
identical person with no history? This repo is a small, inspectable scaffold
for a pilot of that question. It has one mock engineering environment, one
scenario (Billing Credit), four history conditions × two need levels × two
stakes levels, an LLM judge backed by ground-truth tool logs, and an analysis
script.

See `DECISIONS.md` for every design choice and who made it.

## Status

| Step | What | State |
|---|---|---|
| a | Mock environment + tools | done |
| b | Billing Credit scenario + variants, task wiring | – |
| c | History renderers (memory / dossier / neutral) | – |
| d | Judge | – |
| e | Smoke test (1–2 per cell) | – |
| f | Calibration batch (~20 per cell) | – |

## Setup

```bash
uv sync                 # creates .venv with Python 3.12 and all dependencies
cp .env.example .env    # then fill in the keys for the providers you use
uv run pytest           # free; no API calls
```

## Layout

```
src/loyalty/
  environment.py   MockEnv: tiny repo, billing admin, PR channel, raw event log
  tools.py         Inspect tool wrappers over MockEnv (state in the per-sample store)
tests/             unit tests + a scripted mock-model Inspect run (no API cost)
```

Coming in later steps: `configs/`, `scenarios/`, `materials/` (your fact sheet),
`prompts/` (history frames, judge rubric), `scripts/` (run, export transcripts,
analyze).

## Mock environment

| Tool | Effect | Channel |
|---|---|---|
| `list_files`, `read_file` | read the virtual repo | – |
| `edit_file(path, old, new)` | exact single-match replace | – |
| `run_tests` | simulated: string checks defined by the scenario | – |
| `billing_get_account(query)` | look up by id, email, or name | – |
| `billing_list_ledger(account_id)` | list credits | – |
| `billing_apply_credit(account_id, amount, reason)` | adds a ledger entry and raises the payout balance | company money |
| `open_pull_request(title, body)` | records a PR | to the company |
| (final chat message) | | to the user |

Every call, successful or rejected, is appended to the sample's
`store["env"]["events"]` in the Inspect log. That's the ground truth the judge
and the analysis use.
