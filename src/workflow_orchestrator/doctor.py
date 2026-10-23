from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from workflow_orchestrator.adapters.git import GitAdapter
from workflow_orchestrator.adapters.openspec import OpenSpecAdapter
from workflow_orchestrator.state_store import StateStore


@dataclass(frozen=True)
class DoctorItem:
    name: str
    ok: bool | None
    summary: str
    details: dict[str, Any] | None = None


def run_doctor(
    repo: Path,
    change_id: str,
    *,
    gigacode_command: tuple[str, ...] = ("gigacode", "--output-format", "json"),
) -> dict[str, Any]:
    """Check repository readiness, OpenSpec change validity, and GigaCode availability.

    This function is read-only with respect to project source files. It does not
    invoke the GigaCode agent or ask it to modify code.
    """
    repo = repo.expanduser().resolve()
    items: list[DoctorItem] = []

    if not repo.is_dir():
        items.append(DoctorItem("repository", False, f"Directory does not exist: {repo}"))
        return _report(repo, change_id, items)

    # Reuse the same change-ID validation used by persisted state paths.
    try:
        StateStore(repo).run_dir(change_id)
        change_id_ok = True
        change_id_summary = "Change ID format is safe"
    except ValueError as exc:
        change_id_ok = False
        change_id_summary = str(exc)
    items.append(DoctorItem("change_id", change_id_ok, change_id_summary))
    if not change_id_ok:
        # Reject unsafe IDs before any external CLI is invoked.
        return _report(repo, change_id, items)

    is_repo = (repo / ".git").exists() or _is_git_worktree(repo)
    items.append(DoctorItem("repository", is_repo, str(repo)))

    snapshot = GitAdapter().snapshot(repo)
    items.append(
        DoctorItem(
            "git_snapshot",
            snapshot.error is None,
            "Git snapshot captured" if snapshot.error is None else snapshot.error,
            {"head": snapshot.head, "worktree_clean": snapshot.clean},
        )
    )

    openspec_executable = shutil.which("openspec")
    items.append(
        DoctorItem(
            "openspec_cli",
            openspec_executable is not None,
            openspec_executable or "openspec not found on PATH",
        )
    )
    if openspec_executable and change_id_ok:
        openspec = OpenSpecAdapter()
        version = openspec.version(repo)
        items.append(
            DoctorItem(
                "openspec_version",
                version.ok,
                (version.stdout or version.stderr).strip() or "OpenSpec CLI responded without version text",
            )
        )
        status = openspec.status(repo, change_id)
        status_ok = status.ok
        status_summary = status.summary
        if status_ok and status.details:
            reported_change = status.details.get("changeName") or status.details.get("changeId")
            if reported_change is not None and reported_change != change_id:
                status_ok = False
                status_summary = f"OpenSpec returned change '{reported_change}', expected '{change_id}'"
        items.append(DoctorItem(status.name, status_ok, status_summary, status.details))
        validation = openspec.validate(repo, change_id)
        items.append(DoctorItem(validation.name, validation.ok, validation.summary))

    gigacode_executable = gigacode_command[0] if gigacode_command else "gigacode"
    gigacode_path = shutil.which(gigacode_executable)
    items.append(
        DoctorItem(
            "gigacode_cli",
            gigacode_path is not None,
            (
                f"Found at {gigacode_path}; preflight does not invoke the agent"
                if gigacode_path
                else f"{gigacode_executable} not found on PATH"
            ),
        )
    )

    return _report(repo, change_id, items)


def _report(repo: Path, change_id: str, items: list[DoctorItem]) -> dict[str, Any]:
    return {
        "repo": str(repo),
        "change_id": change_id,
        "overall_ok": bool(items) and all(item.ok is True for item in items),
        "items": [asdict(item) for item in items],
        "note": "Preflight checks do not invoke GigaCode or modify project source files.",
    }


def _is_git_worktree(path: Path) -> bool:
    from workflow_orchestrator.process import run_process
    result = run_process(["git", "rev-parse", "--is-inside-work-tree"], cwd=path, timeout=5)
    return result.ok and result.stdout.strip() == "true"
