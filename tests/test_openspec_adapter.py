import json
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_orchestrator.adapters.openspec import OpenSpecAdapter
from workflow_orchestrator.process import ProcessResult


class OpenSpecAdapterTests(unittest.TestCase):
    def test_status_uses_documented_json_command(self):
        payload = {"changeName": "demo", "isComplete": False, "artifacts": []}
        with patch("workflow_orchestrator.adapters.openspec.run_process", return_value=ProcessResult(("openspec",), 0, json.dumps(payload), "")) as run:
            result = OpenSpecAdapter().status(Path.cwd(), "demo")
        self.assertTrue(result.ok)
        self.assertEqual(result.details["changeName"], "demo")
        self.assertEqual(run.call_args.args[0], ["openspec", "status", "--change", "demo", "--json"])

    def test_status_rejects_non_json_output(self):
        with patch("workflow_orchestrator.adapters.openspec.run_process", return_value=ProcessResult(("openspec",), 0, "ok", "")):
            result = OpenSpecAdapter().status(Path.cwd(), "demo")
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
