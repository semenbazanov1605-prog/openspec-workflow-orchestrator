from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from workflow_orchestrator.approval_service import handle_gigacode_result, record_approval_decision
from workflow_orchestrator.execution_service import (
    ExecutionCommandError,
    execute_gigacode,
    resume_gigacode,
)
from workflow_orchestrator.models import WorkflowStatus
from workflow_orchestrator.state_machine import transition
from workflow_orchestrator.state_store import StateStore
from workflow_orchestrator.workflow_service import start_workflow

PASSING_PREFLIGHT = {
    "repo": "/repo", "change_id": "feature", "overall_ok": True,
    "items": [{"name": "all_checks", "ok": True, "summary": "ok", "details": None}],
    "note": "test preflight",
}


class FakeAdapter:
    def __init__(self, result):
        self.result = result
        self.run_calls = []
        self.resume_calls = []

    def run_prompt(self, cwd, prompt):
        self.run_calls.append((cwd, prompt))
        return self.result

    def resume_prompt(self, cwd, session_id, prompt, *, approval_mode="default"):
        self.resume_calls.append((cwd, session_id, prompt, approval_mode))
        return self.result


class ExecutionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self._git("init")
        self._git("config", "user.email", "workflow-test@example.invalid")
        self._git("config", "user.name", "Workflow Test")
        (self.repo / "README.md").write_text("test\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "initial")
        self.store = StateStore(self.repo)
        self.patcher = patch("workflow_orchestrator.workflow_service.run_doctor", return_value={**PASSING_PREFLIGHT, "repo": str(self.repo)})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        start_workflow(self.repo, "feature")

    def _git(self, *args):
        proc = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)
        if proc.returncode:
            raise AssertionError(proc.stderr)

    def _denied(self):
        return SimpleNamespace(
            ok=False, is_error=False, session_id="session-123", error="permission denied",
            permission_denials=({"tool_name": "write_file", "tool_use_id": "tool-1", "tool_input": {"file_path": "src/a.py"}},),
        )

    def _success(self, session="session-123"):
        return SimpleNamespace(ok=True, is_error=False, session_id=session, error=None, permission_denials=())

    def test_run_success_moves_to_verifying_not_completed(self):
        adapter = FakeAdapter(self._success())
        result = execute_gigacode(self.repo, "feature", "Implement a feature", adapter=adapter)
        self.assertEqual(adapter.run_calls[0][1], "Implement a feature")
        self.assertEqual(result["execution"], "verification_required")
        self.assertEqual(result["state"]["status"], WorkflowStatus.VERIFYING.value)

    def test_run_permission_denial_moves_to_waiting_for_approval(self):
        adapter = FakeAdapter(self._denied())
        result = execute_gigacode(self.repo, "feature", "Create a file", adapter=adapter)
        self.assertEqual(result["execution"], "waiting_for_approval")
        self.assertEqual(result["state"]["status"], WorkflowStatus.WAITING_FOR_APPROVAL.value)
        self.assertEqual(result["state"]["gigacode_session_id"], "session-123")

    def test_run_failure_moves_to_failed(self):
        adapter = FakeAdapter(SimpleNamespace(ok=False, is_error=True, session_id="s", error="boom", permission_denials=()))
        result = execute_gigacode(self.repo, "feature", "Do work", adapter=adapter)
        self.assertEqual(result["execution"], "failed")
        self.assertEqual(result["state"]["status"], WorkflowStatus.FAILED.value)

    def test_resume_requires_recorded_approval(self):
        state = self.store.load("feature")
        self.store.save(transition(state, WorkflowStatus.RUNNING), event_type="test_running")
        handle_gigacode_result(self.repo, "feature", self._denied())
        with self.assertRaisesRegex(ExecutionCommandError, "No approval decision recorded"):
            resume_gigacode(self.repo, "feature", adapter=FakeAdapter(self._success()))

    def test_approved_resume_calls_same_session_and_verifies(self):
        state = self.store.load("feature")
        self.store.save(transition(state, WorkflowStatus.RUNNING), event_type="test_running")
        handle_gigacode_result(self.repo, "feature", self._denied())
        record_approval_decision(self.repo, "feature", decision="approve")
        adapter = FakeAdapter(self._success())
        result = resume_gigacode(self.repo, "feature", "Continue", adapter=adapter)
        self.assertEqual(adapter.resume_calls[0][1:], ("session-123", "Continue", "default"))
        self.assertEqual(result["execution"], "verification_required")
        self.assertEqual(result["state"]["status"], WorkflowStatus.VERIFYING.value)

    def test_rejected_resume_never_invokes_adapter(self):
        state = self.store.load("feature")
        self.store.save(transition(state, WorkflowStatus.RUNNING), event_type="test_running")
        handle_gigacode_result(self.repo, "feature", self._denied())
        record_approval_decision(self.repo, "feature", decision="reject")
        adapter = FakeAdapter(self._success())
        result = resume_gigacode(self.repo, "feature", adapter=adapter)
        self.assertFalse(result["resumed"])
        self.assertEqual(result["state"]["status"], WorkflowStatus.PAUSED.value)
        self.assertEqual(adapter.resume_calls, [])

    def test_repeat_denial_creates_new_pending_approval(self):
        state = self.store.load("feature")
        self.store.save(transition(state, WorkflowStatus.RUNNING), event_type="test_running")
        handle_gigacode_result(self.repo, "feature", self._denied())
        record_approval_decision(self.repo, "feature", decision="approve")
        adapter = FakeAdapter(self._denied())
        result = resume_gigacode(self.repo, "feature", adapter=adapter)
        self.assertEqual(result["execution"], "waiting_for_approval")
        self.assertEqual(result["state"]["status"], WorkflowStatus.WAITING_FOR_APPROVAL.value)
        self.assertIsNone(result["state"]["pending_approval"]["decision"])


if __name__ == "__main__":
    unittest.main()
