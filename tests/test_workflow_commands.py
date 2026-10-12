from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow_orchestrator.models import WorkflowPhase, WorkflowStatus
from workflow_orchestrator.state_store import StateStore
from workflow_orchestrator.workflow_service import (
    WorkflowCommandError,
    get_workflow_status,
    start_workflow,
)


class WorkflowCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self._git("init")
        self._git("config", "user.email", "workflow-test@example.invalid")
        self._git("config", "user.name", "Workflow Test")
        (self.repo / "README.md").write_text("test repository\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "initial commit")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.repo, text=True,
            capture_output=True, check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def test_start_persists_ready_state_and_baseline(self) -> None:
        result = start_workflow(self.repo, "add-feature")
        self.assertTrue(result["created"])
        self.assertFalse(result["execution_started"])
        self.assertEqual(result["state"]["status"], WorkflowStatus.READY.value)
        self.assertEqual(result["state"]["phase"], WorkflowPhase.PREFLIGHT.value)
        self.assertTrue(result["baseline_worktree_clean"])
        self.assertEqual(result["state"]["baseline_git_head"], self._git("rev-parse", "HEAD"))
        loaded = StateStore(self.repo).load("add-feature")
        self.assertEqual(loaded.run_id, result["state"]["run_id"])
        self.assertEqual(StateStore(self.repo).read_events("add-feature")[-1]["event_type"], "run_created")

    def test_runtime_state_is_ignored_by_git_without_touching_tracked_gitignore(self) -> None:
        result = start_workflow(self.repo, "add-feature")
        self.assertTrue(result["created"])
        self.assertEqual(self._git("status", "--porcelain"), "")
        self.assertFalse((self.repo / ".gitignore").exists())

    def test_start_warns_about_preexisting_worktree_changes(self) -> None:
        (self.repo / "README.md").write_text("pre-existing user change\n", encoding="utf-8")
        result = start_workflow(self.repo, "add-feature")
        self.assertFalse(result["baseline_worktree_clean"])
        self.assertTrue(result["warnings"])
        self.assertIn("README.md", result["state"]["baseline_git_status"])
        # Runtime data remains excluded even when a pre-existing change exists.
        status = self._git("status", "--porcelain")
        self.assertIn("README.md", status)
        self.assertNotIn(".workflow", status)

    def test_start_refuses_to_overwrite_existing_run(self) -> None:
        start_workflow(self.repo, "add-feature")
        with self.assertRaises(WorkflowCommandError):
            start_workflow(self.repo, "add-feature")

    def test_start_rejects_invalid_change_id(self) -> None:
        with self.assertRaises(WorkflowCommandError):
            start_workflow(self.repo, "../outside")

    def test_start_requires_git_commit(self) -> None:
        empty_repo = Path(self.temp.name) / "empty"
        empty_repo.mkdir()
        subprocess.run(["git", "init"], cwd=empty_repo, check=True, capture_output=True)
        with self.assertRaises(WorkflowCommandError):
            start_workflow(empty_repo, "add-feature")

    def test_status_discovers_single_workflow_and_latest_event(self) -> None:
        start_workflow(self.repo, "add-feature")
        result = get_workflow_status(self.repo)
        self.assertEqual(result["state"]["change_id"], "add-feature")
        self.assertEqual(result["latest_event"]["event_type"], "run_created")

    def test_status_can_include_all_events(self) -> None:
        start_workflow(self.repo, "add-feature")
        result = get_workflow_status(self.repo, "add-feature", include_events=True)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["event_type"], "run_created")

    def test_status_without_runs_has_actionable_error(self) -> None:
        with self.assertRaisesRegex(WorkflowCommandError, "No workflow runs found"):
            get_workflow_status(self.repo)

    def test_status_requires_id_when_multiple_runs_exist(self) -> None:
        start_workflow(self.repo, "first-change")
        start_workflow(self.repo, "second-change")
        with self.assertRaisesRegex(WorkflowCommandError, "Multiple workflow runs exist"):
            get_workflow_status(self.repo)
        selected = get_workflow_status(self.repo, "second-change")
        self.assertEqual(selected["state"]["change_id"], "second-change")

    def test_start_rejects_zero_max_attempts(self) -> None:
        with self.assertRaisesRegex(WorkflowCommandError, "at least 1"):
            start_workflow(self.repo, "add-feature", max_attempts=0)


if __name__ == "__main__":
    unittest.main()
