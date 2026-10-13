import json
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_orchestrator.adapters.gigacode import (
    GigaCodeAdapter,
    parse_stream_json,
)
from workflow_orchestrator.process import ProcessResult


def event(value):
    return json.dumps(value)


class GigaCodeStreamAdapterTests(unittest.TestCase):
    def test_parses_init_assistant_and_result_events(self):
        stdout = "\n".join([
            event({"type": "system", "subtype": "init", "session_id": "sess-1"}),
            event({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done"}]}}),
            event({"type": "result", "subtype": "success", "session_id": "sess-1", "is_error": False, "permission_denials": []}),
        ])
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 0, stdout, "")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "do task")
        self.assertTrue(result.ok)
        self.assertEqual(result.session_id, "sess-1")
        self.assertEqual(result.assistant_text, "Done")
        self.assertEqual([e["type"] for e in result.events], ["system", "assistant", "result"])

    def test_permission_denial_is_not_success_even_if_result_says_success(self):
        denial = {"tool_name": "write_file", "tool_input": {"file_path": "/tmp/x"}}
        stdout = event({"type": "system", "subtype": "init", "session_id": "s"}) + "\n" + event({
            "type": "result", "subtype": "success", "session_id": "s", "is_error": False,
            "permission_denials": [denial],
        })
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 0, stdout, "")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "create file")
        self.assertFalse(result.ok)
        self.assertTrue(result.needs_approval)
        self.assertEqual(result.permission_denials[0]["tool_name"], "write_file")
        self.assertIn("write_file", result.error)

    def test_empty_denials_and_result_success_are_ok(self):
        stdout = event({"type": "result", "subtype": "success", "session_id": "s", "is_error": False, "permission_denials": []})
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 0, stdout, "")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "answer")
        self.assertTrue(result.ok)
        self.assertFalse(result.needs_approval)

    def test_nonzero_exit_is_failure(self):
        stdout = event({"type": "result", "subtype": "success", "session_id": "s", "is_error": False, "permission_denials": []})
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 2, stdout, "bad")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "answer")
        self.assertFalse(result.ok)
        self.assertIn("bad", result.error)

    def test_requires_final_result_event(self):
        stdout = event({"type": "system", "subtype": "init", "session_id": "s"})
        with patch("workflow_orchestrator.adapters.gigacode.run_process", return_value=ProcessResult(("gigacode",), 0, stdout, "")):
            result = GigaCodeAdapter().run_prompt(Path.cwd(), "answer")
        self.assertFalse(result.ok)
        self.assertIn("final result", result.error)

    def test_parser_keeps_valid_events_and_reports_malformed_lines(self):
        parsed = parse_stream_json(event({"type": "system", "subtype": "init"}) + "\nnot-json\n" + event({"type": "result"}))
        self.assertEqual(len(parsed.events), 2)
        self.assertIn("Malformed", parsed.error)

    def test_command_uses_stream_json_default_mode_and_prompt(self):
        captured = {}
        def fake_run(argv, *, cwd, timeout):
            captured["argv"] = argv
            return ProcessResult(tuple(argv), 0, event({"type": "result", "subtype": "success", "is_error": False, "permission_denials": []}), "")
        with patch("workflow_orchestrator.adapters.gigacode.run_process", side_effect=fake_run):
            GigaCodeAdapter().run_prompt(Path.cwd(), "hello")
        self.assertIn("--output-format", captured["argv"])
        self.assertIn("stream-json", captured["argv"])
        self.assertIn("--approval-mode", captured["argv"])
        self.assertIn("default", captured["argv"])
        self.assertEqual(captured["argv"][2], "hello")


    def test_resume_uses_same_session_and_explicit_default_mode(self):
        captured = {}
        stdout = event({"type": "system", "subtype": "init", "session_id": "sess-1"}) + "\n" + event({
            "type": "result", "subtype": "success", "session_id": "sess-1", "is_error": False, "permission_denials": []
        })
        def fake_run(argv, *, cwd, timeout):
            captured["argv"] = argv
            return ProcessResult(tuple(argv), 0, stdout, "")
        with patch("workflow_orchestrator.adapters.gigacode.run_process", side_effect=fake_run):
            result = GigaCodeAdapter().resume_prompt(Path.cwd(), "sess-1", "continue",)
        self.assertTrue(result.ok)
        self.assertEqual(result.session_id, "sess-1")
        self.assertEqual(captured["argv"][:4], ["gigacode", "--resume", "sess-1", "-p"])
        self.assertEqual(captured["argv"][-2:], ["--approval-mode", "default"])

    def test_resume_allows_auto_edit_only_when_explicitly_requested(self):
        captured = {}
        stdout = event({"type": "result", "subtype": "success", "session_id": "s", "is_error": False, "permission_denials": []})
        def fake_run(argv, *, cwd, timeout):
            captured["argv"] = argv
            return ProcessResult(tuple(argv), 0, stdout, "")
        with patch("workflow_orchestrator.adapters.gigacode.run_process", side_effect=fake_run):
            GigaCodeAdapter().resume_prompt(Path.cwd(), "s", "continue", approval_mode="auto-edit")
        self.assertEqual(captured["argv"][-2:], ["--approval-mode", "auto-edit"])

    def test_resume_rejects_empty_session_id(self):
        with self.assertRaises(ValueError):
            GigaCodeAdapter().resume_prompt(Path.cwd(), " ", "continue")

    def test_resume_rejects_unknown_approval_mode(self):
        with self.assertRaises(ValueError):
            GigaCodeAdapter().resume_prompt(Path.cwd(), "s", "continue", approval_mode="unsafe")


if __name__ == "__main__":
    unittest.main()
