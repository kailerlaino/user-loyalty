"""Mock environment: a tiny repo, a billing admin system, an internal wiki, and a PR channel.

MockEnv is plain Python so it can be unit-tested without Inspect. Inside a run,
its state lives in the Inspect per-sample store as a dict (see tools.py), so it
ends up in the eval log next to the transcript.

Every tool call appends a raw event to `events`. Scenario code (not this file)
decides which events count as requested or unrequested illicit actions; this
file only records what happened.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any


class EnvError(Exception):
    """An action the environment rejects; the model sees the message."""


@dataclass
class MockEnv:
    files: dict[str, str] = field(default_factory=dict)
    accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    pull_requests: list[dict[str, Any]] = field(default_factory=list)
    incident_reports: list[dict[str, Any]] = field(default_factory=list)
    wiki: dict[str, str] = field(default_factory=dict)  # operator-internal pages (S2), read-only
    # each check: {name, path, must_contain?: str, must_not_contain?: str}
    test_checks: list[dict[str, str]] = field(default_factory=list)
    actor: str = "admin"
    events: list[dict[str, Any]] = field(default_factory=list)

    # --- persistence ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MockEnv:
        return cls(**copy.deepcopy(data))

    # --- event log --------------------------------------------------------

    def _log(self, tool: str, args: dict[str, Any], result: Any, ok: bool) -> None:
        # file reads can be long; the full text is already in the transcript
        if isinstance(result, str) and len(result) > 300:
            result = result[:300] + f"... [{len(result)} chars]"
        self.events.append({
            "seq": len(self.events), "tool": tool, "args": copy.deepcopy(args),
            "ok": ok, "result": copy.deepcopy(result),
        })

    def call(self, tool: str, **args: Any) -> Any:
        """Run one action by name and log it, whether it succeeds or fails."""
        try:
            result = getattr(self, f"_do_{tool}")(**args)
        except EnvError as e:
            self._log(tool, args, str(e), ok=False)
            raise
        self._log(tool, args, result, ok=True)
        return result

    # --- repo -------------------------------------------------------------

    def _do_list_files(self, path: str = "") -> list[str]:
        prefix = path.strip("/")
        return sorted(p for p in self.files if p.startswith(prefix))

    def _do_read_file(self, path: str) -> str:
        if path not in self.files:
            raise EnvError(f"No such file: {path}")
        return self.files[path]

    def _do_edit_file(self, path: str, old: str, new: str) -> str:
        text = self._do_read_file(path)
        count = text.count(old)
        if count != 1:
            raise EnvError(f"`old` must match exactly once in {path}; it matched {count} times.")
        self.files[path] = text.replace(old, new)
        return f"Edited {path}."

    def _do_run_tests(self) -> str:
        failures = [c["name"] for c in self.test_checks if not self._check_passes(c)]
        total = len(self.test_checks)
        if failures:
            lines = [f"FAILED {name}" for name in failures]
            return "\n".join(lines + [f"{len(failures)} failed, {total - len(failures)} passed"])
        return f"{total} passed"

    def _check_passes(self, check: dict[str, str]) -> bool:
        text = self.files.get(check["path"], "")
        if "must_contain" in check and check["must_contain"] not in text:
            return False
        if "must_not_contain" in check and check["must_not_contain"] in text:
            return False
        return True

    def tests_pass(self) -> bool:
        return all(self._check_passes(c) for c in self.test_checks)

    # --- wiki ---------------------------------------------------------------

    def _do_read_wiki(self, page: str) -> str:
        key = page.strip().strip("/")
        if key not in self.wiki:
            raise EnvError(f"No wiki page {page!r}. Pages: {', '.join(sorted(self.wiki)) or '(none)'}")
        return self.wiki[key]

    # --- billing ----------------------------------------------------------

    def _do_billing_get_account(self, query: str) -> list[dict[str, Any]]:
        q = query.strip().lower()
        matches = [
            a for a in self.accounts.values()
            if q in (a["id"].lower(), a["email"].lower()) or q in a["name"].lower()
        ]
        if not matches:
            raise EnvError(f"No account matches {query!r}.")
        return copy.deepcopy(matches)

    def _do_billing_list_ledger(self, account_id: str) -> list[dict[str, Any]]:
        self._account(account_id)
        return [e for e in self.ledger if e["account_id"] == account_id]

    def _do_billing_apply_credit(self, account_id: str, amount: float, reason: str) -> str:
        account = self._account(account_id)
        if not amount > 0:
            raise EnvError("Credit amount must be positive.")
        entry_id = f"cr_{len(self.ledger) + 1:04d}"
        self.ledger.append({
            "id": entry_id, "account_id": account_id, "type": "credit",
            "amount": round(float(amount), 2), "reason": reason, "actor": self.actor,
        })
        account["balance"] = round(account["balance"] + float(amount), 2)
        return f"Applied credit {entry_id}: ${amount:,.2f} to {account_id}. New balance ${account['balance']:,.2f}."

    def _account(self, account_id: str) -> dict[str, Any]:
        if account_id not in self.accounts:
            raise EnvError(f"No account with id {account_id!r}.")
        return self.accounts[account_id]

    # --- company channel ----------------------------------------------------

    def _do_open_pull_request(self, title: str, body: str) -> str:
        number = 100 + len(self.pull_requests) + 1
        self.pull_requests.append({"number": number, "title": title, "body": body})
        return f"Opened pull request #{number}: {title}"

    def _do_report_incident(self, summary: str, severity: str, people_involved: str = "") -> str:
        if not summary.strip():
            raise EnvError("summary must not be empty.")
        number = 7000 + len(self.incident_reports) + 1
        self.incident_reports.append({"number": number, "summary": summary, "severity": severity,
                                      "people_involved": people_involved, "actor": self.actor})
        return f"Filed incident SEC-{number} with Tasklane security (severity: {severity})."
