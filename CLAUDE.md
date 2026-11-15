# user-loyalty

Research code for a study of whether shared history makes an AI agent favor a user. The study owner
often designs in a regular chat and brings the design here to build and run. The living project
summary is imported below; work from it.

@PROJECT_CONTEXT.md

## Keep PROJECT_CONTEXT.md current, every turn

Before ending a turn, update `PROJECT_CONTEXT.md` if the turn changed anything it describes:

- files built or changed;
- a run started or finished, with its numbers and cost;
- a result, or a new reading of one;
- a decision or new direction agreed with the owner, even one made only in chat;
- a doc published or updated;
- a commit or push.

How to update it:

- Edit in place. Revise "Where it stands", add a row to the experiments table, move settled items
  out of "Open threads", fix "Git state", and change the "Last updated" date.
- Keep it under about 250 lines. Detail goes in `DECISIONS.md`, and the context file points there.
- A Stop hook (`.claude/hooks/check_project_context.sh`) blocks the end of a turn once when repo
  files are newer than `PROJECT_CONTEXT.md`. Generated output and caches don't count: `logs/`,
  `transcripts/`, `previews/`, `.git`, `.venv` and `.claude/`. If nothing in the file needs to
  change, update its "Last updated" line so the next turn starts clean.

## Standing rules from the owner

- **Paid API calls.**
  - Before any paid run, show the diff and the cost estimate (`scripts/run.py <config> --no-judge`
    without `--confirm`), then wait for an explicit yes.
  - Each approval covers one run.
  - Subagents never spend money.
- **Keys.** Never read `.env` and never print API keys, including the ai-village HF_TOKEN.
- **Privacy.** The motivating case involves a real person.
  - Keep that person's personal details out of every output: code, docs, artifacts and commits.
  - Never open, upload or publish these files:
    - `/Users/homew/ai-village/analysis/out/nervli_confidentiality_hits.csv`
    - `/Users/homew/ai-village/analysis/cache/nervli_notes.jsonl`
    - `fable5_turns.jsonl` and `fable5_memories.jsonl`
- **Git.**
  - Commit only when asked. The owner reviews commits in chunks.
  - Add no co-author or other Claude attribution lines to commits.
  - Never commit `Claude outputs/`; it holds the redacted case file.
- **Credentials in files.** Don't write strings shaped like real credentials; GitHub push protection
  blocked fake Stripe keys before. Escape them as in `scenarios/incident_report.yaml`
  (`sk\x5ftest\x5f…`).
- **OpenRouter.** Don't change the account's privacy or "paid model training" setting. Pin hosts in
  the config instead (`provider.order`, `allow_fallbacks: false`).
- **Registered files are frozen.** Don't edit `configs/s1_replication.yaml`,
  `configs/depth_registered.yaml`, `scripts/preregistered_s1.py`, `scripts/preregistered_depth.py`
  or `materials/past_sessions.yaml`.
- **Shared code.** Changing shared code is fine, as long as every existing test still passes and
  every existing scenario's rendered prompts stay the same.
- **Recording decisions.**
  - Record each design decision in `DECISIONS.md` as a new step with numbered rows, in the style of
    the existing ones.
  - Add results entries under "## Open questions", newest first.
  - Add a status row to `README.md`.
