from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def run_process(
    argv: Sequence[str], *, cwd: Path | None = None, timeout: int = 60
) -> ProcessResult:
    """Run a command without a shell; capture output and convert timeout to data."""
    try:
        completed = subprocess.run(
            list(argv), cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        return ProcessResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)
    except FileNotFoundError as exc:
        return ProcessResult(tuple(argv), 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return ProcessResult(tuple(argv), 124, stdout, stderr or f"Command timed out after {timeout}s", True)
