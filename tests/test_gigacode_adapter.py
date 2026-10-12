import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_orchestrator.adapters.gigacode import GigaCodeAdapter, _extract_json_object
from workflow_orchestrator.process import ProcessResult


class GigaCodeAdapterTests(unittest.TestCase):
    def test_parses_confirmed_fields(self):
        payload = {"session_id": "sess-123", "stop_reason": "end_turn", "is_error": False}
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 0, json.dumps(payload), "")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "implement change")
        self.assertTrue(result.ok)
        self.assertEqual(result.session_id, "sess-123")
        self.assertEqual(result.stop_reason, "end_turn")
        self.assertFalse(result.is_error)

    def test_nonzero_exit_is_failure_even_if_json_claims_success(self):
        payload = {"session_id": "sess-123", "stop_reason": "end_turn", "is_error": False}
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 2, json.dumps(payload), "failed")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "implement change")
        self.assertFalse(result.ok)

    def test_rejects_missing_json(self):
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 0, "done", "")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "implement change")
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)

    def test_can_extract_json_surrounded_by_text(self):
        self.assertEqual(_extract_json_object('noise\n{"session_id":"x","is_error":false}\nend'), {"session_id": "x", "is_error": False})


if __name__ == "__main__":
    unittest.main()
