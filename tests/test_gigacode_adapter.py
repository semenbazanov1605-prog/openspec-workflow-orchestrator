import json
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_orchestrator.adapters.gigacode import GigaCodeAdapter, parse_stream_json
from workflow_orchestrator.process import ProcessResult


class GigaCodeAdapterTests(unittest.TestCase):
    def test_parses_confirmed_stream_fields(self):
        stdout = json.dumps({"type": "system", "subtype": "init", "session_id": "sess-123"}) + "\n" + json.dumps({"type": "result", "subtype": "success", "session_id": "sess-123", "is_error": False, "permission_denials": []})
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 0, stdout, "")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "implement change")
        self.assertTrue(result.ok)
        self.assertEqual(result.session_id, "sess-123")
        self.assertFalse(result.is_error)

    def test_permission_denial_is_not_success(self):
        stdout = json.dumps({"type": "result", "subtype": "success", "session_id": "sess-123", "is_error": False, "permission_denials": [{"tool_name": "write_file"}]})
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 0, stdout, "")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "implement change")
        self.assertFalse(result.ok)
        self.assertTrue(result.needs_approval)

    def test_rejects_missing_result_event(self):
        stdout = json.dumps({"type": "system", "subtype": "init", "session_id": "sess-123"})
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 0, stdout, "")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "implement change")
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)

    def test_parser_can_recover_valid_events_around_bad_line(self):
        stdout = json.dumps({"type": "system", "subtype": "init"}) + "\nnoise\n" + json.dumps({"type": "result"})
        parsed = parse_stream_json(stdout)
        self.assertEqual(len(parsed.events), 2)
        self.assertIsNotNone(parsed.error)


if __name__ == "__main__":
    unittest.main()
