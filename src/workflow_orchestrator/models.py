"""Typed models for persisted workflow state."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


STATE_SCHEMA_VERSION = 1


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp suitable for JSON persistence."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class WorkflowStatus(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    RETRY_PENDING = "RETRY_PENDING"
    PAUSED = "PAUSED"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class ApprovalMode(StrEnum):
    """Orchestrator policy for actions proposed by the executor."""

    DEFAULT = "default"
    AUTO_EDIT = "auto-edit"
    PLAN = "plan"


class WorkflowPhase(StrEnum):
    PREFLIGHT = "PREFLIGHT"
    IMPLEMENT = "IMPLEMENT"
    VERIFY = "VERIFY"
    DONE = "DONE"


@dataclass
class WorkflowState:
    """Serializable snapshot of one workflow run for one OpenSpec change."""

    change_id: str
    repository_path: str
    status: WorkflowStatus = WorkflowStatus.READY
    phase: WorkflowPhase = WorkflowPhase.PREFLIGHT
    run_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = STATE_SCHEMA_VERSION
    attempt_count: int = 0
    max_attempts: int = 2
    approval_mode: ApprovalMode = ApprovalMode.DEFAULT
    pending_approval: dict[str, Any] | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    baseline_git_head: str | None = None
    baseline_git_status: str | None = None
    gigacode_session_id: str | None = None
    last_result: dict[str, Any] | None = None
    next_action: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != STATE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported workflow state schema version: {self.schema_version}"
            )
        if not self.change_id or not self.change_id.strip():
            raise ValueError("change_id must not be empty")
        if not self.repository_path or not self.repository_path.strip():
            raise ValueError("repository_path must not be empty")
        if self.attempt_count < 0:
            raise ValueError("attempt_count must be >= 0")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if not isinstance(self.approval_mode, ApprovalMode):
            try:
                self.approval_mode = ApprovalMode(self.approval_mode)
            except (TypeError, ValueError) as exc:
                allowed = ", ".join(mode.value for mode in ApprovalMode)
                raise ValueError(f"approval_mode must be one of: {allowed}") from exc
        if self.pending_approval is not None and not isinstance(self.pending_approval, dict):
            raise ValueError("pending_approval must be a JSON object or null")

    @classmethod
    def new(
        cls,
        *,
        change_id: str,
        repository_path: str,
        max_attempts: int = 2,
        approval_mode: ApprovalMode | str = ApprovalMode.DEFAULT,
        baseline_git_head: str | None = None,
        baseline_git_status: str | None = None,
    ) -> "WorkflowState":
        """Create an initial state snapshot for a new workflow run."""
        now = utc_now()
        return cls(
            change_id=change_id,
            repository_path=repository_path,
            max_attempts=max_attempts,
            approval_mode=ApprovalMode(approval_mode),
            baseline_git_head=baseline_git_head,
            baseline_git_status=baseline_git_status,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the state into a JSON-compatible dictionary."""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "change_id": self.change_id,
            "repository_path": self.repository_path,
            "status": self.status.value,
            "phase": self.phase.value,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "approval_mode": self.approval_mode.value,
            "pending_approval": self.pending_approval,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "baseline_git_head": self.baseline_git_head,
            "baseline_git_status": self.baseline_git_status,
            "gigacode_session_id": self.gigacode_session_id,
            "last_result": self.last_result,
            "next_action": self.next_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowState":
        """Load and validate a state snapshot from decoded JSON."""
        if not isinstance(data, dict):
            raise ValueError("Workflow state must be a JSON object")
        try:
            return cls(
                schema_version=int(data["schema_version"]),
                run_id=str(data["run_id"]),
                change_id=str(data["change_id"]),
                repository_path=str(data["repository_path"]),
                status=WorkflowStatus(data["status"]),
                phase=WorkflowPhase(data["phase"]),
                attempt_count=int(data.get("attempt_count", 0)),
                max_attempts=int(data.get("max_attempts", 2)),
                approval_mode=ApprovalMode(data.get("approval_mode", ApprovalMode.DEFAULT.value)),
                pending_approval=data.get("pending_approval"),
                created_at=str(data["created_at"]),
                updated_at=str(data["updated_at"]),
                baseline_git_head=data.get("baseline_git_head"),
                baseline_git_status=data.get("baseline_git_status"),
                gigacode_session_id=data.get("gigacode_session_id"),
                last_result=data.get("last_result"),
                next_action=data.get("next_action"),
            )
        except KeyError as exc:
            raise ValueError(f"Missing required workflow state field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith(
                ("Unsupported workflow state schema version", "change_id must", "repository_path must", "attempt_count must", "max_attempts must")
            ):
                raise
            raise ValueError(f"Invalid workflow state: {exc}") from exc
