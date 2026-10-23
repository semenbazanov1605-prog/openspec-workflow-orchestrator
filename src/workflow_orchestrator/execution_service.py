"""CLI-connected GigaCode execution and approval-driven session resume."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow_orchestrator.adapters.gigacode import GigaCodeAdapter
from workflow_orchestrator.approval_service import (
    ApprovalCommandError,
    finalize_approval_decision,
    handle_gigacode_result,
)
from workflow_orchestrator.models import ApprovalMode, WorkflowStatus
from workflow_orchestrator.state_machine import transition
from workflow_orchestrator.state_store import StateStore, StateStoreError


class ExecutionCommandError(RuntimeError):
    """Raised when a workflow cannot safely start or resume execution."""


def execute_gigacode(
    repository: Path,
    change_id: str,
    prompt: str,
    *,
    gigacode_executable: str = "gigacode",
    gigacode_approval_mode: str = "default",
    timeout: int = 1800,
    adapter: GigaCodeAdapter | None = None,
) -> dict[str, Any]:
    """Start a new GigaCode turn for a READY or PAUSED workflow run."""
    repo, store, state = _load_state(repository, change_id)
    if not prompt or not prompt.strip():
        raise ExecutionCommandError("Prompt must not be empty")
    if state.status not in {WorkflowStatus.READY, WorkflowStatus.PAUSED}:
        raise ExecutionCommandError(
            f"Cannot start execution from {state.status.value}; expected READY or PAUSED"
        )
    runner = adapter or _adapter(gigacode_executable, gigacode_approval_mode, timeout)
    running = transition(
        state,
        WorkflowStatus.RUNNING,
        next_action="GigaCode is executing the requested prompt.",
    )
    try:
        store.save(running, event_type="gigacode_execution_started", details={"resumed": False})
    except (StateStoreError, OSError) as exc:
        raise ExecutionCommandError(str(exc)) from exc
    result = runner.run_prompt(repo, prompt.strip())
    return _persist_result(repo, change_id, result, resumed=False)


def resume_gigacode(
    repository: Path,
    change_id: str,
    prompt: str | None = None,
    *,
    gigacode_executable: str = "gigacode",
    gigacode_approval_mode: str = "default",
    timeout: int = 1800,
    adapter: GigaCodeAdapter | None = None,
) -> dict[str, Any]:
    """Consume an explicit approval decision and resume its saved GigaCode session.

    The selected GigaCode permission mode is passed explicitly. An orchestrator
    approval does not itself change GigaCode's permission rules or elevate its mode.
    """
    repo, store, state = _load_state(repository, change_id)
    pending = state.pending_approval
    if state.status is not WorkflowStatus.WAITING_FOR_APPROVAL or not pending:
        raise ExecutionCommandError("Workflow is not waiting for an approval decision")
    decision = pending.get("decision")
    if decision not in {"approve", "reject"}:
        raise ExecutionCommandError("No approval decision recorded; use 'workflow approval' first")
    session_id = state.gigacode_session_id
    if decision == "approve" and not session_id:
        raise ExecutionCommandError("Cannot resume: workflow has no saved GigaCode session_id")

    # Finalize only after confirming that a decision exists. Rejection pauses the
    # workflow and never invokes GigaCode.
    finalized = finalize_approval_decision(repo, change_id)
    if decision == "reject":
        return {
            "command": "resume",
            "resumed": False,
            "reason": "approval_rejected",
            "state": finalized["state"],
        }

    current_prompt = prompt.strip() if isinstance(prompt, str) and prompt.strip() else (
        "Continue the previous task after the approved operation. Follow the original task instructions."
    )
    runner = adapter or _adapter(gigacode_executable, gigacode_approval_mode, timeout)
    result = runner.resume_prompt(
        repo,
        session_id,
        current_prompt,
        approval_mode=gigacode_approval_mode,
    )
    return _persist_result(repo, change_id, result, resumed=True)


def _persist_result(repository: Path, change_id: str, result: Any, *, resumed: bool) -> dict[str, Any]:
    report = handle_gigacode_result(repository, change_id, result)
    if report.get("approval_required"):
        report["execution"] = "waiting_for_approval"
        report["resumed"] = resumed
        return report

    store = StateStore(repository)
    state = store.load(change_id)
    if bool(getattr(result, "ok", False)):
        if state.status in {WorkflowStatus.RUNNING, WorkflowStatus.VERIFYING}:
            updated = transition(
                state,
                WorkflowStatus.VERIFYING,
                next_action="GigaCode turn completed. Review the diff and run verification before marking the workflow complete.",
            ) if state.status is WorkflowStatus.RUNNING else state
            try:
                store.save(updated, event_type="gigacode_turn_succeeded", details={"resumed": resumed})
            except (StateStoreError, OSError) as exc:
                raise ExecutionCommandError(str(exc)) from exc
            report["state"] = updated.to_dict()
        report["execution"] = "verification_required"
    else:
        if state.status in {WorkflowStatus.RUNNING, WorkflowStatus.VERIFYING}:
            updated = transition(
                state,
                WorkflowStatus.FAILED,
                next_action="GigaCode execution failed. Inspect last_result and logs before retrying.",
            )
            updated.last_result = {
                **(updated.last_result or {}),
                "kind": "gigacode_execution_failed",
                "error": getattr(result, "error", None) or "GigaCode execution failed",
            }
            try:
                store.save(updated, event_type="gigacode_execution_failed", details={"resumed": resumed})
            except (StateStoreError, OSError) as exc:
                raise ExecutionCommandError(str(exc)) from exc
            report["state"] = updated.to_dict()
        report["execution"] = "failed"
    report["resumed"] = resumed
    return report


def _adapter(executable: str, approval_mode: str, timeout: int) -> GigaCodeAdapter:
    try:
        mode = ApprovalMode(approval_mode)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in ApprovalMode)
        raise ExecutionCommandError(f"--gigacode-approval-mode must be one of: {allowed}") from exc
    return GigaCodeAdapter(
        command=(executable, "-p", "", "--output-format", "stream-json", "--approval-mode", mode.value),
        timeout=timeout,
    )


def _load_state(repository: Path, change_id: str):
    repo = repository.expanduser().resolve()
    if not repo.is_dir():
        raise ExecutionCommandError(f"Repository directory does not exist: {repo}")
    store = StateStore(repo)
    try:
        state = store.load(change_id)
    except (StateStoreError, ValueError) as exc:
        raise ExecutionCommandError(str(exc)) from exc
    if state.repository_path != str(repo):
        raise ExecutionCommandError(
            f"Workflow state belongs to a different repository path: {state.repository_path} (requested {repo})"
        )
    return repo, store, state
