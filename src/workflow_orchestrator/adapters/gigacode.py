from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from workflow_orchestrator.process import ProcessResult, run_process


@dataclass(frozen=True)
class GigaCodeResult:
    """Normalized result from one non-interactive GigaCode CLI turn.

    `ok` means the CLI turn ended successfully and no tool permission was
    denied. It does not assert that the requested code change is correct;
    workflow verification must still inspect the diff and run checks.
    """

    ok: bool
    returncode: int
    session_id: str | None
    stop_reason: str | None
    is_error: bool | None
    raw_json: dict[str, Any] | None
    stdout: str
    stderr: str
    error: str | None = None
    events: tuple[dict[str, Any], ...] = ()
    permission_denials: tuple[dict[str, Any], ...] = ()
    assistant_text: str = ""
    result_payload: dict[str, Any] | None = None

    @property
    def needs_approval(self) -> bool:
        """True when GigaCode reported one or more denied tool operations."""
        return bool(self.permission_denials)


class GigaCodeAdapter:
    """Adapter for GigaCode CLI's observed newline-delimited stream JSON.

    This first integration version is one-shot: it parses all emitted events
    after the process exits. It detects denied permissions but does not yet
    answer approval requests or resume a denied tool call.
    """

    def __init__(
        self,
        command: Sequence[str] = (
            "gigacode", "-p", "", "--output-format", "stream-json",
            "--approval-mode", "default",
        ),
        timeout: int = 1800,
    ):
        self.command = tuple(command)
        self.timeout = timeout

    def version(self, cwd: Path) -> ProcessResult:
        return run_process([self.command[0], "--version"], cwd=cwd, timeout=30)

    def run_prompt(self, cwd: Path, prompt: str) -> GigaCodeResult:
        # Keep the prompt as one argv element; never invoke a shell.
        argv = _command_with_prompt(self.command, prompt)
        process = run_process(argv, cwd=cwd, timeout=self.timeout)
        parsed = parse_stream_json(process.stdout)

        result_event = next(
            (event for event in reversed(parsed.events) if event.get("type") == "result"),
            None,
        )
        init_event = next(
            (
                event for event in parsed.events
                if event.get("type") == "system" and event.get("subtype") == "init"
            ),
            None,
        )
        session_id = _first_string(
            (result_event or {}).get("session_id"),
            (init_event or {}).get("session_id"),
        )
        result_payload = result_event
        raw_error = result_event.get("is_error") if result_event else None
        is_error = raw_error if isinstance(raw_error, bool) else None
        stop_reason = _as_optional_str(result_event.get("stop_reason")) if result_event else None
        denials = _permission_denials(result_event)
        has_result = result_event is not None
        ok = process.ok and has_result and is_error is not True and not denials

        error: str | None = None
        if process.timed_out:
            error = process.stderr.strip() or f"GigaCode timed out after {self.timeout}s"
        elif process.returncode != 0:
            error = process.stderr.strip() or f"GigaCode exited with code {process.returncode}"
        elif not has_result:
            error = parsed.error or "GigaCode stream did not contain a final result event"
        elif is_error is True:
            error = _as_optional_str(result_event.get("result")) or "GigaCode reported an error"
        elif denials:
            names = ", ".join(
                str(item.get("tool_name", "unknown tool")) for item in denials
            )
            error = f"GigaCode denied permission for: {names}"

        return GigaCodeResult(
            ok=ok,
            returncode=process.returncode,
            session_id=session_id,
            stop_reason=stop_reason,
            is_error=is_error,
            raw_json=result_payload or (parsed.events[-1] if parsed.events else None),
            stdout=process.stdout,
            stderr=process.stderr,
            error=error,
            events=parsed.events,
            permission_denials=denials,
            assistant_text=parsed.assistant_text,
            result_payload=result_payload,
        )


@dataclass(frozen=True)
class ParsedStream:
    events: tuple[dict[str, Any], ...]
    assistant_text: str
    error: str | None = None


def parse_stream_json(output: str) -> ParsedStream:
    """Parse GigaCode NDJSON, retaining valid events and reporting bad lines."""
    events: list[dict[str, Any]] = []
    text_chunks: list[str] = []
    malformed_lines: list[int] = []

    for line_number, line in enumerate(output.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            malformed_lines.append(line_number)
            continue
        if not isinstance(value, dict):
            malformed_lines.append(line_number)
            continue
        events.append(value)
        if value.get("type") == "assistant":
            message = value.get("message")
            content = message.get("content", []) if isinstance(message, dict) else []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text")
                        if isinstance(text, str):
                            text_chunks.append(text)

    error = None
    if not events:
        error = "No valid JSON events found in GigaCode stdout"
    elif malformed_lines:
        # Keep parsing valid lines; expose a diagnostic instead of discarding
        # all useful events. Callers can inspect this in tests/logs.
        error = "Malformed stream-json line(s): " + ", ".join(map(str, malformed_lines))

    return ParsedStream(tuple(events), "".join(text_chunks), error)


def _permission_denials(result_event: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
    if not isinstance(result_event, dict):
        return ()
    value = result_event.get("permission_denials")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _command_with_prompt(command: Sequence[str], prompt: str) -> list[str]:
    """Replace the first empty argument after `-p`/`--prompt`, or append it."""
    argv = list(command)
    for index, item in enumerate(argv[:-1]):
        if item in ("-p", "--prompt") and argv[index + 1] == "":
            argv[index + 1] = prompt
            return argv
    if "-p" in argv or "--prompt" in argv:
        # A non-empty prompt in the configured command is almost certainly a
        # configuration mistake; don't silently append a second prompt.
        raise ValueError("Configured GigaCode command must leave its prompt argument empty")
    return [*argv, "-p", prompt]


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _as_optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
