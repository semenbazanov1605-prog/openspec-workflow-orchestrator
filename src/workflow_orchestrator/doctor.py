from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from workflow_orchestrator.adapters.git import GitAdapter
from workflow_orchestrator.adapters.gigacode import GigaCodeAdapter
from workflow_orchestrator.adapters.openspec import OpenSpecAdapter


@dataclass(frozen=True)
class DoctorItem:
    name: str
    ok: bool | None
    summary: str
    details: dict[str, Any] | None = None


def run_doctor(repo: Path, change_id: str, *, gigacode_command: tuple[str, ...] = ("gigacode", "--output-format", "json")) -> dict[str, Any]:
    repo = repo.resolve()
    items: list[DoctorItem] = []
    items.append(DoctorItem("repository", (repo / ".git").exists() or _is_git_worktree(repo), str(repo)))

    git = GitAdapter()
    snapshot = git.snapshot(repo)
    items.append(DoctorItem("git_snapshot", snapshot.error is None,
        "Git snapshot captured" if snapshot.error is None else snapshot.error,
        {"head": snapshot.head, "worktree_clean": snapshot.clean}))

    openspec = OpenSpecAdapter()
    openspec_path = shutil.which("openspec")
    items.append(DoctorItem("openspec_cli", openspec_path is not None, openspec_path or "openspec not found on PATH"))
    if openspec_path:
        version = openspec.version(repo)
        items.append(DoctorItem("openspec_version", version.ok, (version.stdout or version.stderr).strip()))
        status = openspec.status(repo, change_id)
        items.append(DoctorItem(status.name, status.ok, status.summary, status.details))
        validation = openspec.validate(repo, change_id)
        items.append(DoctorItem(validation.name, validation.ok, validation.summary))

    gigacode_path = shutil.which(gigacode_command[0])
    items.append(DoctorItem("gigacode_cli", gigacode_path is not None,
        f"Found at {gigacode_path}; invocation syntax still requires a live probe" if gigacode_path else f"{gigacode_command[0]} not found on PATH"))
    return {
        "repo": str(repo),
        "change_id": change_id,
        "overall_ok": all(item.ok is not False for item in items),
        "items": [asdict(item) for item in items],
        "note": "This command only inspects the environment; it does not modify project files.",
    }


def _is_git_worktree(path: Path) -> bool:
    import subprocess
    try:
        result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path, capture_output=True, text=True, timeout=5)
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (OSError, subprocess.TimeoutExpired):
        return False
