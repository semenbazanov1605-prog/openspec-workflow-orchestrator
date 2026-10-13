import json
import tempfile
import unittest
from pathlib import Path

from workflow_orchestrator.models import WorkflowState, WorkflowStatus
from workflow_orchestrator.state_machine import transition
from workflow_orchestrator.state_store import StateStore, StateStoreError


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.store = StateStore(self.root)
        self.state = WorkflowState.new(
            change_id="add-loyalty-feature",
            repository_path=str(self.root),
            baseline_git_head="abc123",
            baseline_git_status="",
        )

    def test_create_and_load_round_trip(self):
        self.store.create(self.state)
        loaded = self.store.load(self.state.change_id)
        self.assertEqual(loaded.to_dict(), self.state.to_dict())
        self.assertTrue(self.store.state_path(self.state.change_id).is_file())

    def test_create_refuses_to_overwrite_existing_state(self):
        self.store.create(self.state)
        with self.assertRaises(StateStoreError):
            self.store.create(self.state)

    def test_save_updates_state_and_appends_event(self):
        self.store.create(self.state)
        running = transition(self.state, WorkflowStatus.RUNNING)
        self.store.save(running, event_type="phase_started", details={"worker": "gigacode"})

        loaded = self.store.load(self.state.change_id)
        self.assertEqual(loaded.status, WorkflowStatus.RUNNING)
        events = self.store.read_events(self.state.change_id)
        self.assertEqual([event["event_type"] for event in events], ["run_created", "phase_started"])
        self.assertEqual(events[-1]["details"]["worker"], "gigacode")

    def test_load_missing_state_has_clear_error(self):
        with self.assertRaisesRegex(StateStoreError, "No saved workflow state"):
            self.store.load("missing-change")

    def test_invalid_state_json_has_clear_error(self):
        path = self.store.state_path(self.state.change_id)
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(StateStoreError, "Invalid workflow state"):
            self.store.load(self.state.change_id)

    def test_change_id_cannot_escape_runs_directory(self):
        for invalid in ("../outside", "with/slash", "with\\backslash", "", "."):
            with self.subTest(change_id=invalid):
                with self.assertRaises(ValueError):
                    self.store.state_path(invalid)

    def test_invalid_event_line_is_reported(self):
        path = self.store.events_path(self.state.change_id)
        path.parent.mkdir(parents=True)
        path.write_text('{"event_type":"ok"}\nnot-json\n', encoding="utf-8")
        with self.assertRaisesRegex(StateStoreError, "Invalid event JSON"):
            self.store.read_events(self.state.change_id)

    def test_state_file_is_valid_json_with_schema_version(self):
        self.store.create(self.state)
        data = json.loads(self.store.state_path(self.state.change_id).read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["change_id"], self.state.change_id)
        self.assertEqual(data["approval_mode"], "default")
        self.assertIsNone(data["pending_approval"])

    def test_legacy_state_without_approval_fields_loads_with_safe_defaults(self):
        legacy = self.state.to_dict()
        legacy.pop("approval_mode")
        legacy.pop("pending_approval")
        loaded = type(self.state).from_dict(legacy)
        self.assertEqual(loaded.approval_mode.value, "default")
        self.assertIsNone(loaded.pending_approval)


if __name__ == "__main__":
    unittest.main()
