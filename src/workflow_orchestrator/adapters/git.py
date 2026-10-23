from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from workflow_orchestrator.process import run_process


@dataclass(frozen=True)
class GitSnapshot:
    head: str | None
    status_porcelain: str | None
    error: str | None = None

    @property
    def clean(self) -> bool | None:
        if self.status_porcelain is None:
            return None
        return not self.status_porcelain.strip()


class GitAdapter:
    def snapshot(self, cwd: Path) -> GitSnapshot:
        head = run_process(["git", "rev-parse", "HEAD"], cwd=cwd)
        status = run_process(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=cwd)
        if not head.ok or not status.ok:
            return GitSnapshot(None, None, head.stderr or status.stderr or "Git command failed")
        return GitSnapshot(head.stdout.strip(), status.stdout, None)

    def diff_stat(self, cwd: Path) -> str | None:
        result = run_process(["git", "diff", "--stat", "HEAD"], cwd=cwd)
        return result.stdout if result.ok else None
