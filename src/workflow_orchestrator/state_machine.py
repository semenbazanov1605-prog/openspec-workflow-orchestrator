"""Pure state-transition rules for workflow runs."""
from __future__ import annotations

from dataclasses import replace

from workflow_orchestrator.models import WorkflowPhase, WorkflowState, WorkflowStatus, utc_now


class InvalidTransitionError(ValueError):
    """Raised when a requested workflow status transition is not allowed."""


_ALLOWED_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.READY: frozenset(
        {WorkflowStatus.RUNNING, WorkflowStatus.PAUSED, WorkflowStatus.FAILED}
    ),
    WorkflowStatus.RUNNING: frozenset(
        {
            WorkflowStatus.VERIFYING,
            WorkflowStatus.RETRY_PENDING,
            WorkflowStatus.PAUSED,
            WorkflowStatus.INTERRUPTED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.VERIFYING: frozenset(
        {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.RETRY_PENDING,
            WorkflowStatus.PAUSED,
            WorkflowStatus.INTERRUPTED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.RETRY_PENDING: frozenset(
        {WorkflowStatus.RUNNING, WorkflowStatus.VERIFYING, WorkflowStatus.PAUSED, WorkflowStatus.FAILED}
    ),
    WorkflowStatus.PAUSED: frozenset(
        {
            WorkflowStatus.READY,
            WorkflowStatus.RUNNING,
            WorkflowStatus.VERIFYING,
            WorkflowStatus.RETRY_PENDING,
            WorkflowStatus.INTERRUPTED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.INTERRUPTED: frozenset(
        {
            WorkflowStatus.RUNNING,
            WorkflowStatus.VERIFYING,
            WorkflowStatus.PAUSED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.FAILED: frozenset(),
    WorkflowStatus.COMPLETED: frozenset(),
}

_DEFAULT_PHASE: dict[WorkflowStatus, WorkflowPhase] = {
    WorkflowStatus.READY: WorkflowPhase.PREFLIGHT,
    WorkflowStatus.RUNNING: WorkflowPhase.IMPLEMENT,
    WorkflowStatus.VERIFYING: WorkflowPhase.VERIFY,
    WorkflowStatus.COMPLETED: WorkflowPhase.DONE,
}


def allowed_transitions(status: WorkflowStatus) -> frozenset[WorkflowStatus]:
    """Return the set of legal next statuses for a status."""
    return _ALLOWED_TRANSITIONS[status]


def transition(
    state: WorkflowState,
    new_status: WorkflowStatus,
    *,
    next_action: str | None = None,
    updated_at: str | None = None,
) -> WorkflowState:
    """Return an updated copy of state, rejecting illegal status changes.

    Phase is inferred for the main path and otherwise preserved. This function
    is deliberately side-effect free; callers persist the returned state and
    append the corresponding event through StateStore.
    """
    if not isinstance(new_status, WorkflowStatus):
        try:
            new_status = WorkflowStatus(new_status)
        except ValueError as exc:
            raise InvalidTransitionError(f"Unknown workflow status: {new_status}") from exc

    if new_status not in _ALLOWED_TRANSITIONS[state.status]:
        raise InvalidTransitionError(
            f"Transition {state.status.value} -> {new_status.value} is not allowed"
        )

    new_phase = _DEFAULT_PHASE.get(new_status, state.phase)
    return replace(
        state,
        status=new_status,
        phase=new_phase,
        updated_at=updated_at or utc_now(),
        next_action=next_action,
    )
