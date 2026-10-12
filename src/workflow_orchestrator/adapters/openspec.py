from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflow_orchestrator.process import ProcessResult, run_process


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    command: tuple[str, ...]
    summary: str
    details: dict[str, Any] | None = None


class OpenSpecAdapter:
    """Thin wrapper around documented OpenSpec CLI commands."""

    def __init__(self, executable: str = "openspec", timeout: int = 60):
        self.executable = executable
        self.timeout = timeout

    def version(self, cwd: Path) -> ProcessResult:
        return run_process([self.executable, "--version"], cwd=cwd, timeout=self.timeout)

    def status(self, cwd: Path, change_id: str) -> CheckResult:
        result = run_process(
            [self.executable, "status", "--change", change_id, "--json"],
            cwd=cwd, timeout=self.timeout,
        )
        details = _parse_json(result.stdout)
        return CheckResult(
            "openspec_status", result.ok and details is not None,
            result.argv, _summary(result, details), details,
        )

    def validate(self, cwd: Path, change_id: str) -> CheckResult:
        result = run_process(
            [self.executable, "validate", change_id, "--no-interactive"],
            cwd=cwd, timeout=self.timeout,
        )
        return CheckResult(
            "openspec_validate", result.ok, result.argv,
            _summary(result, None), None,
        )


def _parse_json(output: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(output)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _summary(result: ProcessResult, details: dict[str, Any] | None) -> str:
    if result.timed_out:
        return result.stderr or "Command timed out"
    if not result.ok:
        return (result.stderr or result.stdout or f"Exit code {result.returncode}").strip()
    if details is not None:
        return f"OpenSpec returned JSON ({', '.join(details.keys()) or 'empty object'})"
    return (result.stdout or "Command completed").strip()
