"""Persist approval requests and operator decisions for workflow runs."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from workflow_orchestrator.approval import ApprovalAction, ApprovalOutcome, evaluate_action
from workflow_orchestrator.models import ApprovalMode, WorkflowState, WorkflowStatus, utc_now
from workflow_orchestrator.state_machine import InvalidTransitionError, transition
from workflow_orchestrator.state_store import StateStore, StateStoreError


class ApprovalCommandError(RuntimeError):
    """Raised when an approval request or decision cannot be safely processed."""


def request_approval(
    repository: Path,
    change_id: str,
    *,
    action: ApprovalAction | str,
    description: str,
    source: str = "executor",
) -> dict[str, Any]:
    """Apply policy and, if needed, persist a WAITING_FOR_APPROVAL request.

    Intended to be called by a future executor adapter when it receives a
    structured action request. It cannot infer approvals from arbitrary text.
    """
    repo, store, state = _load_state(repository, change_id)
    try:
        action_kind = ApprovalAction(action)
    except (TypeError, ValueError) as exc:
        raise ApprovalCommandError(f"Unsupported action kind: {action!r}") from exc
    if not description or not description.strip():
        raise ApprovalCommandError("Approval description must not be empty")

    if state.status not in {WorkflowStatus.RUNNING, WorkflowStatus.VERIFYING}:
        raise ApprovalCommandError(
            "An executor action can only be evaluated for a RUNNING or VERIFYING workflow; "
            f"current status is {state.status.value}"
        )
    if state.pending_approval is not None:
        raise ApprovalCommandError("A pending approval already exists for this workflow")

    policy = evaluate_action(state.approval_mode, action_kind)
    if policy.outcome is ApprovalOutcome.ALLOW:
        return {
            "command": "approval-request",
            "outcome": policy.outcome.value,
            "change_id": change_id,
            "approval_required": False,
            "reason": policy.reason,
            "state": state.to_dict(),
        }

    if policy.outcome is ApprovalOutcome.DENY:
        state.updated_at = utc_now()
        state.last_result = {
            "kind": "approval_policy",
            "outcome": policy.outcome.value,
            "action": action_kind.value,
            "description": description,
            "reason": policy.reason,
        }
        state.next_action = "Do not execute the denied action; revise the plan or task."
        try:
            store.save(
                state,
                event_type="action_denied_by_policy",
                details={
                    "action": action_kind.value,
                    "description": description,
                    "reason": policy.reason,
                },
            )
        except (StateStoreError, OSError) as exc:
            raise ApprovalCommandError(str(exc)) from exc
        return {
            "command": "approval-request",
            "outcome": policy.outcome.value,
            "change_id": change_id,
            "approval_required": False,
            "reason": policy.reason,
            "state": state.to_dict(),
        }

    pending = {
        "request_id": str(uuid4()),
        "action": action_kind.value,
        "description": description.strip(),
        "source": source,
        "requested_at": utc_now(),
        "resume_status": state.status.value,
        "decision": None,
        "decision_at": None,
        "decision_note": None,
    }
    waiting = transition(
        state,
        WorkflowStatus.WAITING_FOR_APPROVAL,
        next_action="Wait for an explicit human decision on the pending action.",
    )
    waiting.pending_approval = pending
    waiting.last_result = {
        "kind": "approval_request",
        "request_id": pending["request_id"],
        "action": action_kind.value,
        "description": description.strip(),
    }
    try:
        store.save(
            waiting,
            event_type="approval_requested",
            details={
                "request_id": pending["request_id"],
                "action": action_kind.value,
                "description": description.strip(),
                "source": source,
                "resume_status": state.status.value,
            },
        )
    except (StateStoreError, OSError) as exc:
        raise ApprovalCommandError(str(exc)) from exc

    return {
        "command": "approval-request",
        "outcome": policy.outcome.value,
        "change_id": change_id,
        "approval_required": True,
        "state": waiting.to_dict(),
        "notice": "Approval is persisted. A live executor must relay the decision before work can continue.",
    }


def record_approval_decision(
    repository: Path,
    change_id: str,
    *,
    decision: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Persist a human decision for the executor to consume.

    This does not send keystrokes or a response to a live GigaCode process yet.
    The process/TTY or structured-event bridge is a separate integration task.
    """
    repo, store, state = _load_state(repository, change_id)
    normalized_decision = decision.strip().lower() if isinstance(decision, str) else ""
    if normalized_decision not in {"approve", "reject"}:
        raise ApprovalCommandError("--decision must be 'approve' or 'reject'")
    pending = state.pending_approval
    if state.status is not WorkflowStatus.WAITING_FOR_APPROVAL or pending is None:
        raise ApprovalCommandError(
            f"Workflow '{change_id}' is not waiting for an approval decision"
        )
    if pending.get("decision") is not None:
        raise ApprovalCommandError(
            f"Approval request '{pending.get('request_id')}' already has a recorded decision"
        )

    try:
        action = ApprovalAction(pending["action"])
    except (KeyError, ValueError) as exc:
        raise ApprovalCommandError("Persisted approval request has an invalid action") from exc
    policy = evaluate_action(state.approval_mode, action)
    if normalized_decision == "approve" and policy.outcome is ApprovalOutcome.DENY:
        raise ApprovalCommandError(
            f"Cannot approve this action in '{state.approval_mode.value}' mode: {policy.reason}"
        )

    pending["decision"] = normalized_decision
    pending["decision_at"] = utc_now()
    pending["decision_note"] = (note.strip() if note and note.strip() else None)
    state.pending_approval = pending
    state.updated_at = utc_now()
    state.next_action = (
        "Approval decision recorded; executor must consume it before proceeding."
        if normalized_decision == "approve"
        else "Rejection recorded; executor must stop or revise the requested action."
    )
    try:
        store.save(
            state,
            event_type="approval_decision_recorded",
            details={
                "request_id": pending["request_id"],
                "decision": normalized_decision,
                "note": pending["decision_note"],
            },
        )
    except (StateStoreError, OSError) as exc:
        raise ApprovalCommandError(str(exc)) from exc

    return {
        "command": "approval",
        "recorded": True,
        "decision": normalized_decision,
        "decision_delivered_to_executor": False,
        "state": state.to_dict(),
        "notice": (
            "Decision is stored in workflow state. This version does not yet relay it to a live GigaCode process."
        ),
    }


def finalize_approval_decision(repository: Path, change_id: str) -> dict[str, Any]:
    """Consume a recorded decision and move workflow to its next safe state.

    Called by the future execution engine after it has successfully relayed the
    decision to the blocked executor. It must not be called merely because the
    human decision was written to disk.
    """
    repo, store, state = _load_state(repository, change_id)
    pending = state.pending_approval
    if state.status is not WorkflowStatus.WAITING_FOR_APPROVAL or pending is None:
        raise ApprovalCommandError("Workflow has no pending approval request")
    decision = pending.get("decision")
    if decision not in {"approve", "reject"}:
        raise ApprovalCommandError("No human approval decision has been recorded yet")

    if decision == "approve":
        try:
            resume_status = WorkflowStatus(pending["resume_status"])
        except (KeyError, ValueError) as exc:
            raise ApprovalCommandError("Approval request has an invalid resume status") from exc
        updated = transition(
            state,
            resume_status,
            next_action="Approval was delivered; executor may continue the requested action.",
        )
    else:
        updated = transition(
            state,
            WorkflowStatus.PAUSED,
            next_action="The requested action was rejected. Revise the plan before continuing.",
        )

    updated.pending_approval = None
    updated.last_result = {
        "kind": "approval_resolved",
        "request_id": pending["request_id"],
        "decision": decision,
    }
    try:
        store.save(
            updated,
            event_type="approval_decision_consumed",
            details={"request_id": pending["request_id"], "decision": decision},
        )
    except (StateStoreError, OSError) as exc:
        raise ApprovalCommandError(str(exc)) from exc
    return {"command": "approval-consumed", "state": updated.to_dict()}



def handle_gigacode_result(repository: Path, change_id: str, result: Any) -> dict[str, Any]:
    """Persist a GigaCode turn and convert reported permission denials to approval requests.

    This is the adapter-to-workflow boundary: a final CLI event with
    ``is_error=false`` is still treated as incomplete when permission_denials
    is non-empty. It records the session id before creating a pending request.
    It does not resume the session or grant permissions by itself.
    """
    repo, store, state = _load_state(repository, change_id)
    if state.status not in {WorkflowStatus.RUNNING, WorkflowStatus.VERIFYING}:
        raise ApprovalCommandError(
            "A GigaCode result can only be handled for a RUNNING or VERIFYING workflow; "
            f"current status is {state.status.value}"
        )

    session_id = getattr(result, "session_id", None)
    denials = tuple(getattr(result, "permission_denials", ()) or ())
    state.gigacode_session_id = session_id or state.gigacode_session_id
    state.last_result = {
        "kind": "gigacode_turn",
        "ok": bool(getattr(result, "ok", False)),
        "is_error": getattr(result, "is_error", None),
        "session_id": state.gigacode_session_id,
        "permission_denial_count": len(denials),
        "error": getattr(result, "error", None),
    }
    try:
        store.save(
            state,
            event_type="gigacode_turn_received",
            details={
                "ok": bool(getattr(result, "ok", False)),
                "session_id": state.gigacode_session_id,
                "permission_denial_count": len(denials),
            },
        )
    except (StateStoreError, OSError) as exc:
        raise ApprovalCommandError(str(exc)) from exc

    if denials:
        denial = denials[0]
        tool_name = str(denial.get("tool_name") or "unknown")
        tool_input = denial.get("tool_input") if isinstance(denial.get("tool_input"), dict) else {}
        if tool_name in {"write_file", "edit_file", "replace_in_file", "apply_patch"}:
            action = ApprovalAction.FILE_EDIT
        elif tool_name.lower() in {"bash", "shell", "run_command", "execute_command"}:
            action = ApprovalAction.COMMAND
        else:
            action = ApprovalAction.UNKNOWN
        path = tool_input.get("file_path") or tool_input.get("path")
        description = f"GigaCode tool '{tool_name}' was denied"
        if path:
            description += f" for path {path}"
        if len(denials) > 1:
            description += f" ({len(denials)} denied operations in this turn)"
        approval = request_approval(
            repo,
            change_id,
            action=action,
            description=description,
            source="gigacode",
        )
        approval["gigacode_session_id"] = state.gigacode_session_id
        approval["permission_denials"] = list(denials)
        return approval

    return {
        "command": "gigacode-result",
        "change_id": change_id,
        "ok": bool(getattr(result, "ok", False)),
        "needs_approval": False,
        "state": state.to_dict(),
        "notice": "GigaCode result persisted. Successful execution still requires workflow verification.",
    }

def _load_state(repository: Path, change_id: str) -> tuple[Path, StateStore, WorkflowState]:
    repo = repository.expanduser().resolve()
    if not repo.is_dir():
        raise ApprovalCommandError(f"Repository directory does not exist: {repo}")
    store = StateStore(repo)
    try:
        state = store.load(change_id)
    except (StateStoreError, ValueError) as exc:
        raise ApprovalCommandError(str(exc)) from exc
    if state.repository_path != str(repo):
        raise ApprovalCommandError(
            "Workflow state belongs to a different repository path: "
            f"{state.repository_path} (requested {repo})"
        )
    return repo, store, state
