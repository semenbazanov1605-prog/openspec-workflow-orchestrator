from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_orchestrator.approval import ApprovalAction
from workflow_orchestrator.approval_service import (
    ApprovalCommandError,
    finalize_approval_decision,
    record_approval_decision,
    request_approval,
)
from workflow_orchestrator.models import ApprovalMode, WorkflowStatus
from workflow_orchestrator.state_machine import transition
from workflow_orchestrator.state_store import StateStore
from workflow_orchestrator.workflow_service import start_workflow


PASSING_PREFLIGHT = {
    "repo": "/repo",
    "change_id": "add-feature",
    "overall_ok": True,
    "items": [{"name": "all_checks", "ok": True, "summary": "ok", "details": None}],
    "note": "test preflight",
}


class ApprovalServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self._git("init")
        self._git("config", "user.email", "workflow-test@example.invalid")
        self._git("config", "user.name", "Workflow Test")
        (self.repo / "README.md").write_text("test repository\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "initial commit")
        self.store = StateStore(self.repo)
        self.preflight_patcher = patch(
            "workflow_orchestrator.workflow_service.run_doctor",
            return_value={**PASSING_PREFLIGHT, "repo": str(self.repo), "change_id": "feature"},
        )
        self.preflight_patcher.start()
        self.addCleanup(self.preflight_patcher.stop)

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.repo, text=True, capture_output=True, check=False
        )
        if result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def _create_running_state(self, *, mode: ApprovalMode = ApprovalMode.DEFAULT) -> None:
        start_workflow(self.repo, "feature", approval_mode=mode)
        state = self.store.load("feature")
        running = transition(state, WorkflowStatus.RUNNING, next_action="Executing agent")
        self.store.save(running, event_type="implementation_started")

    def test_file_edit_request_in_default_mode_persists_waiting_state(self):
        self._create_running_state()
        result = request_approval(
            self.repo,
            "feature",
            action=ApprovalAction.FILE_EDIT,
            description="Edit src/main/java/App.java",
            source="gigacode",
        )
        self.assertTrue(result["approval_required"])
        self.assertEqual(result["state"]["status"], WorkflowStatus.WAITING_FOR_APPROVAL.value)
        self.assertEqual(result["state"]["pending_approval"]["action"], "file-edit")
        self.assertIsNone(result["state"]["pending_approval"]["decision"])
        self.assertEqual(self.store.read_events("feature")[-1]["event_type"], "approval_requested")

    def test_read_only_action_does_not_pause_workflow(self):
        self._create_running_state()
        result = request_approval(
            self.repo, "feature", action=ApprovalAction.READ_ONLY, description="Inspect files"
        )
        self.assertFalse(result["approval_required"])
        self.assertEqual(result["state"]["status"], WorkflowStatus.RUNNING.value)

    def test_plan_mode_denies_file_edit_and_does_not_wait_for_approval(self):
        self._create_running_state(mode=ApprovalMode.PLAN)
        result = request_approval(
            self.repo, "feature", action=ApprovalAction.FILE_EDIT, description="Edit a file"
        )
        self.assertEqual(result["outcome"], "deny")
        self.assertEqual(result["state"]["status"], WorkflowStatus.RUNNING.value)
        self.assertIsNone(result["state"]["pending_approval"])
        self.assertEqual(self.store.read_events("feature")[-1]["event_type"], "action_denied_by_policy")

    def test_auto_edit_allows_file_edit_but_still_requires_command_approval(self):
        self._create_running_state(mode=ApprovalMode.AUTO_EDIT)
        file_result = request_approval(
            self.repo, "feature", action=ApprovalAction.FILE_EDIT, description="Edit a file"
        )
        self.assertFalse(file_result["approval_required"])
        command_result = request_approval(
            self.repo, "feature", action=ApprovalAction.COMMAND, description="Run a shell command"
        )
        self.assertTrue(command_result["approval_required"])
        self.assertEqual(command_result["state"]["status"], WorkflowStatus.WAITING_FOR_APPROVAL.value)

    def test_cannot_request_approval_when_workflow_is_not_active(self):
        start_workflow(self.repo, "feature")
        with self.assertRaisesRegex(ApprovalCommandError, "only be evaluated for a RUNNING or VERIFYING"):
            request_approval(
                self.repo, "feature", action=ApprovalAction.FILE_EDIT, description="Edit a file"
            )

    def test_records_decision_but_keeps_waiting_until_executor_consumes_it(self):
        self._create_running_state()
        request_approval(
            self.repo, "feature", action=ApprovalAction.FILE_EDIT, description="Edit a file"
        )
        result = record_approval_decision(self.repo, "feature", decision="approve", note="Expected change")
        self.assertTrue(result["recorded"])
        self.assertFalse(result["decision_delivered_to_executor"])
        self.assertEqual(result["state"]["status"], WorkflowStatus.WAITING_FOR_APPROVAL.value)
        self.assertEqual(result["state"]["pending_approval"]["decision"], "approve")

        finalized = finalize_approval_decision(self.repo, "feature")
        self.assertEqual(finalized["state"]["status"], WorkflowStatus.RUNNING.value)
        self.assertIsNone(finalized["state"]["pending_approval"])

    def test_rejected_decision_pauses_workflow_when_consumed(self):
        self._create_running_state()
        request_approval(
            self.repo, "feature", action=ApprovalAction.FILE_EDIT, description="Edit a file"
        )
        record_approval_decision(self.repo, "feature", decision="reject")
        finalized = finalize_approval_decision(self.repo, "feature")
        self.assertEqual(finalized["state"]["status"], WorkflowStatus.PAUSED.value)
        self.assertIsNone(finalized["state"]["pending_approval"])

    def test_plan_mode_cannot_approve_mutating_action(self):
        self._create_running_state(mode=ApprovalMode.DEFAULT)
        request_approval(
            self.repo, "feature", action=ApprovalAction.FILE_EDIT, description="Edit a file"
        )
        # The mode for a persisted run is fixed at creation. Rewriting this in
        # the test models a corrupted/mismatched pending request and must fail closed.
        state = self.store.load("feature")
        state.approval_mode = ApprovalMode.PLAN
        self.store.save(state, event_type="test_mode_change")
        with self.assertRaisesRegex(ApprovalCommandError, "Cannot approve this action"):
            record_approval_decision(self.repo, "feature", decision="approve")

    def test_cannot_record_second_decision(self):
        self._create_running_state()
        request_approval(
            self.repo, "feature", action=ApprovalAction.FILE_EDIT, description="Edit a file"
        )
        record_approval_decision(self.repo, "feature", decision="reject")
        with self.assertRaisesRegex(ApprovalCommandError, "already has a recorded decision"):
            record_approval_decision(self.repo, "feature", decision="approve")


if __name__ == "__main__":
    unittest.main()
