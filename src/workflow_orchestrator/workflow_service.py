"""Application services for initializing and inspecting workflow runs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow_orchestrator.adapters.git import GitAdapter
from workflow_orchestrator.models import WorkflowState
from workflow_orchestrator.process import run_process
from workflow_orchestrator.state_store import StateStore, StateStoreError


class WorkflowCommandError(RuntimeError):
    """Raised when a workflow CLI operation cannot safely proceed."""


def start_workflow(
    repository: Path,
    change_id: str,
    *,
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Create a persisted READY run after recording a Git baseline.

    This command only initializes workflow state. It deliberately does not call
    OpenSpec or GigaCode yet; the real preflight and implementation phases are
    added in later milestones.
    """
    repo = repository.expanduser().resolve()
    if not repo.is_dir():
        raise WorkflowCommandError(f"Repository directory does not exist: {repo}")
    if max_attempts < 1:
        raise WorkflowCommandError("--max-attempts must be at least 1")

    store = StateStore(repo)
    # Validate the change ID before doing any filesystem changes.
    try:
        store.run_dir(change_id)
    except ValueError as exc:
        raise WorkflowCommandError(str(exc)) from exc

    _ensure_workflow_state_git_ignored(repo)

    snapshot = GitAdapter().snapshot(repo)
    if snapshot.error:
        raise WorkflowCommandError(
            f"Cannot capture Git baseline for {repo}: {snapshot.error}. "
            "Ensure this is a Git working tree with at least one commit."
        )

    state = WorkflowState.new(
        change_id=change_id,
        repository_path=str(repo),
        max_attempts=max_attempts,
        baseline_git_head=snapshot.head,
        baseline_git_status=snapshot.status_porcelain,
    )
    state.next_action = (
        "Run OpenSpec/GigaCode preflight before implementation; this version only initializes state."
    )
    try:
        store.create(state)
    except (StateStoreError, OSError) as exc:
        raise WorkflowCommandError(str(exc)) from exc

    warnings: list[str] = []
    if snapshot.clean is False:
        warnings.append(
            "The worktree already had changes at start. They are recorded in the baseline and must not be attributed to the agent."
        )
    return {
        "command": "start",
        "created": True,
        "execution_started": False,
        "repository": str(repo),
        "state_file": str(store.state_path(change_id)),
        "events_file": str(store.events_path(change_id)),
        "state": state.to_dict(),
        "baseline_worktree_clean": snapshot.clean,
        "warnings": warnings,
        "notice": "State initialization only: OpenSpec preflight and GigaCode implementation are not wired into start yet.",
    }


def get_workflow_status(
    repository: Path,
    change_id: str | None = None,
    *,
    include_events: bool = False,
) -> dict[str, Any]:
    """Load the saved state for one run and optionally include its event log."""
    repo = repository.expanduser().resolve()
    if not repo.is_dir():
        raise WorkflowCommandError(f"Repository directory does not exist: {repo}")

    store = StateStore(repo)
    try:
        selected_change = change_id
        if selected_change is None:
            changes = store.list_changes()
            if not changes:
                raise WorkflowCommandError(
                    f"No workflow runs found under {store.runs_root}. Start one with 'workflow start <change-id>'."
                )
            if len(changes) > 1:
                choices = ", ".join(changes)
                raise WorkflowCommandError(
                    f"Multiple workflow runs exist ({choices}); specify one with 'workflow status <change-id>'."
                )
            selected_change = changes[0]
        state = store.load(selected_change)
        result: dict[str, Any] = {
            "command": "status",
            "repository": str(repo),
            "state_file": str(store.state_path(selected_change)),
            "state": state.to_dict(),
        }
        if include_events:
            result["events"] = store.read_events(selected_change)
        else:
            events = store.read_events(selected_change)
            result["latest_event"] = events[-1] if events else None
        return result
    except (StateStoreError, ValueError) as exc:
        raise WorkflowCommandError(str(exc)) from exc


def _ensure_workflow_state_git_ignored(repo: Path) -> None:
    """Ignore local ``.workflow/`` runtime state without editing tracked files.

    The rule is added to Git's local info/exclude file, not the project's
    tracked .gitignore. This prevents orchestrator state from appearing as an
    unexplained worktree change and avoids modifying the user's source tree.
    """
    result = run_process(["git", "rev-parse", "--git-path", "info/exclude"], cwd=repo)
    if not result.ok or not result.stdout.strip():
        raise WorkflowCommandError(
            f"Cannot locate Git's local exclude file: {result.stderr or 'git rev-parse failed'}"
        )
    exclude_path = Path(result.stdout.strip())
    if not exclude_path.is_absolute():
        exclude_path = (repo / exclude_path).resolve()

    try:
        existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        lines = {line.strip() for line in existing.splitlines()}
        if "/.workflow/" not in lines and ".workflow/" not in lines:
            exclude_path.parent.mkdir(parents=True, exist_ok=True)
            prefix = "" if not existing or existing.endswith("\n") else "\n"
            with exclude_path.open("a", encoding="utf-8") as stream:
                stream.write(f"{prefix}\n# OpenSpec Workflow Orchestrator local state\n/.workflow/\n")
    except OSError as exc:
        raise WorkflowCommandError(
            f"Could not configure local Git exclude file at {exclude_path}: {exc}"
        ) from exc
