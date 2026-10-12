from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from workflow_orchestrator.process import ProcessResult, run_process


@dataclass(frozen=True)
class GigaCodeResult:
    ok: bool
    returncode: int
    session_id: str | None
    stop_reason: str | None
    is_error: bool | None
    raw_json: dict[str, Any] | None
    stdout: str
    stderr: str
    error: str | None = None


class GigaCodeAdapter:
    """Configurable CLI adapter; command syntax must be confirmed locally."""

    def __init__(self, command: Sequence[str] = ("gigacode", "--output-format", "json"), timeout: int = 1800):
        self.command = tuple(command)
        self.timeout = timeout

    def version(self, cwd: Path) -> ProcessResult:
        return run_process([self.command[0], "--version"], cwd=cwd, timeout=30)

    def run_prompt(self, cwd: Path, prompt: str) -> GigaCodeResult:
        # Do not use shell=True: prompt is passed as a single argument.
        result = run_process([*self.command, prompt], cwd=cwd, timeout=self.timeout)
        payload = _extract_json_object(result.stdout)
        if payload is None:
            return GigaCodeResult(
                False, result.returncode, None, None, None, None,
                result.stdout, result.stderr,
                "No valid JSON object found in GigaCode stdout",
            )
        is_error = payload.get("is_error")
        ok = result.ok and is_error is not True
        return GigaCodeResult(
            ok=ok,
            returncode=result.returncode,
            session_id=_as_optional_str(payload.get("session_id")),
            stop_reason=_as_optional_str(payload.get("stop_reason")),
            is_error=is_error if isinstance(is_error, bool) else None,
            raw_json=payload,
            stdout=result.stdout,
            stderr=result.stderr,
            error=(result.stderr.strip() or None) if not ok else None,
        )


def _extract_json_object(output: str) -> dict[str, Any] | None:
    """Parse a JSON object from pure JSON output or text surrounding one."""
    try:
        value = json.loads(output)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and any(k in value for k in ("session_id", "stop_reason", "is_error")):
            return value
    return None


def _as_optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
