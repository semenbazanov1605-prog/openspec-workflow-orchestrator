from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_orchestrator.doctor import run_doctor
from workflow_orchestrator.adapters.git import GitSnapshot
from workflow_orchestrator.adapters.openspec import CheckResult
from workflow_orchestrator.process import ProcessResult


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_fails_if_any_preflight_check_fails(self) -> None:
        with (
            patch("workflow_orchestrator.doctor._is_git_worktree", return_value=True),
            patch("workflow_orchestrator.doctor.GitAdapter.snapshot", return_value=GitSnapshot("abc", "")),
            patch("workflow_orchestrator.doctor.shutil.which", side_effect=lambda name: "/usr/bin/openspec" if name == "openspec" else None),
            patch("workflow_orchestrator.doctor.OpenSpecAdapter.version", return_value=ProcessResult(("openspec", "--version"), 0, "1.2.3", "")),
            patch("workflow_orchestrator.doctor.OpenSpecAdapter.status", return_value=CheckResult("openspec_status", True, ("openspec", "status"), "ok", {"changeName": "demo"})),
            patch("workflow_orchestrator.doctor.OpenSpecAdapter.validate", return_value=CheckResult("openspec_validate", True, ("openspec", "validate"), "ok")),
        ):
            report = run_doctor(self.repo, "demo")
        self.assertFalse(report["overall_ok"])
        self.assertFalse(next(item for item in report["items"] if item["name"] == "gigacode_cli")["ok"])

    def test_change_name_mismatch_fails_preflight(self) -> None:
        with (
            patch("workflow_orchestrator.doctor._is_git_worktree", return_value=True),
            patch("workflow_orchestrator.doctor.GitAdapter.snapshot", return_value=GitSnapshot("abc", "")),
            patch("workflow_orchestrator.doctor.shutil.which", return_value="/usr/bin/tool"),
            patch("workflow_orchestrator.doctor.OpenSpecAdapter.version", return_value=ProcessResult(("openspec", "--version"), 0, "1.2.3", "")),
            patch("workflow_orchestrator.doctor.OpenSpecAdapter.status", return_value=CheckResult("openspec_status", True, ("openspec", "status"), "ok", {"changeName": "another-change"})),
            patch("workflow_orchestrator.doctor.OpenSpecAdapter.validate", return_value=CheckResult("openspec_validate", True, ("openspec", "validate"), "ok")),
        ):
            report = run_doctor(self.repo, "demo")
        self.assertFalse(report["overall_ok"])
        status = next(item for item in report["items"] if item["name"] == "openspec_status")
        self.assertFalse(status["ok"])
        self.assertIn("expected 'demo'", status["summary"])

    def test_invalid_change_id_fails_without_invoking_openspec(self) -> None:
        with patch("workflow_orchestrator.doctor.shutil.which") as which:
            report = run_doctor(self.repo, "../escape")
        self.assertFalse(report["overall_ok"])
        which.assert_not_called()

    def test_nonexistent_repo_fails_immediately(self) -> None:
        report = run_doctor(self.repo / "missing", "demo")
        self.assertFalse(report["overall_ok"])
        self.assertEqual(report["items"][0]["name"], "repository")


if __name__ == "__main__":
    unittest.main()
