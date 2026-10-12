import unittest

from workflow_orchestrator.models import WorkflowPhase, WorkflowState, WorkflowStatus
from workflow_orchestrator.state_machine import InvalidTransitionError, allowed_transitions, transition


class WorkflowStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.state = WorkflowState.new(
            change_id="add-loyalty-feature",
            repository_path="/tmp/sample-project",
            baseline_git_head="abc123",
            baseline_git_status="",
        )

    def test_ready_to_running_enters_implementation_phase(self):
        updated = transition(self.state, WorkflowStatus.RUNNING, next_action="Wait for agent result")
        self.assertEqual(updated.status, WorkflowStatus.RUNNING)
        self.assertEqual(updated.phase, WorkflowPhase.IMPLEMENT)
        self.assertEqual(updated.next_action, "Wait for agent result")
        self.assertEqual(self.state.status, WorkflowStatus.READY, "transition must not mutate the original state")

    def test_running_to_verifying_enters_verify_phase(self):
        running = transition(self.state, WorkflowStatus.RUNNING)
        verifying = transition(running, WorkflowStatus.VERIFYING)
        self.assertEqual(verifying.phase, WorkflowPhase.VERIFY)

    def test_verifying_to_completed_enters_done_phase(self):
        running = transition(self.state, WorkflowStatus.RUNNING)
        verifying = transition(running, WorkflowStatus.VERIFYING)
        completed = transition(verifying, WorkflowStatus.COMPLETED)
        self.assertEqual(completed.phase, WorkflowPhase.DONE)

    def test_invalid_transition_is_rejected(self):
        with self.assertRaises(InvalidTransitionError):
            transition(self.state, WorkflowStatus.COMPLETED)

    def test_completed_is_terminal(self):
        completed = self.state
        completed.status = WorkflowStatus.COMPLETED
        with self.assertRaises(InvalidTransitionError):
            transition(completed, WorkflowStatus.RUNNING)

    def test_allowed_transitions_are_available(self):
        self.assertIn(WorkflowStatus.RUNNING, allowed_transitions(WorkflowStatus.READY))
        self.assertEqual(allowed_transitions(WorkflowStatus.FAILED), frozenset())


if __name__ == "__main__":
    unittest.main()
