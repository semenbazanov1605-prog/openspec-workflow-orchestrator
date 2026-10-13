"""Approval policy primitives independent of a particular AI CLI protocol.

This module describes what the orchestrator should do when an executor asks
for an action. It does not itself control a live GigaCode terminal session;
that transport integration will be implemented after its actual approval
interaction is verified on the target machine.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from workflow_orchestrator.models import ApprovalMode


class ApprovalAction(StrEnum):
    """Coarse action categories understood by the orchestrator."""

    READ_ONLY = "read-only"
    FILE_EDIT = "file-edit"
    COMMAND = "command"
    UNKNOWN = "unknown"


class ApprovalOutcome(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require-approval"
    DENY = "deny"


@dataclass(frozen=True)
class ApprovalPolicyResult:
    outcome: ApprovalOutcome
    reason: str


def evaluate_action(
    mode: ApprovalMode | str,
    action: ApprovalAction | str,
) -> ApprovalPolicyResult:
    """Evaluate an action with a least-privilege approval policy.

    - ``default``: read-only actions are allowed; writes, commands and unknown
      actions require explicit human approval.
    - ``auto-edit``: read-only actions and file edits are allowed; commands and
      unknown actions still require approval. This intentionally does not
      imply blanket permission to execute arbitrary shell commands.
    - ``plan``: read-only analysis is allowed; all potentially mutating or
      unclassified actions are denied.

    The final policy decision must later be mapped to GigaCode's actual tool / 
    approval events by the live adapter.
    """
    try:
        normalized_mode = ApprovalMode(mode)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in ApprovalMode)
        raise ValueError(f"Unknown approval mode {mode!r}; choose one of: {allowed}") from exc
    try:
        normalized_action = ApprovalAction(action)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unknown approval action {action!r}") from exc

    if normalized_action is ApprovalAction.READ_ONLY:
        return ApprovalPolicyResult(ApprovalOutcome.ALLOW, "Read-only action is allowed in every mode")

    if normalized_mode is ApprovalMode.PLAN:
        return ApprovalPolicyResult(
            ApprovalOutcome.DENY,
            "Plan mode forbids changes and non-read-only actions",
        )

    if normalized_mode is ApprovalMode.AUTO_EDIT and normalized_action is ApprovalAction.FILE_EDIT:
        return ApprovalPolicyResult(
            ApprovalOutcome.ALLOW,
            "File edits are allowed by auto-edit mode; non-edit commands remain gated",
        )

    return ApprovalPolicyResult(
        ApprovalOutcome.REQUIRE_APPROVAL,
        "Human approval is required by the selected policy",
    )
