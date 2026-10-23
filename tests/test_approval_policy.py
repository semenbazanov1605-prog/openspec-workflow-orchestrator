from __future__ import annotations

import unittest

from workflow_orchestrator.approval import ApprovalAction, ApprovalOutcome, evaluate_action
from workflow_orchestrator.models import ApprovalMode


class ApprovalPolicyTests(unittest.TestCase):
    def test_default_mode_allows_read_only_and_requires_approval_for_mutations(self):
        self.assertEqual(
            evaluate_action(ApprovalMode.DEFAULT, ApprovalAction.READ_ONLY).outcome,
            ApprovalOutcome.ALLOW,
        )
        for action in (ApprovalAction.FILE_EDIT, ApprovalAction.COMMAND, ApprovalAction.UNKNOWN):
            with self.subTest(action=action):
                self.assertEqual(
                    evaluate_action(ApprovalMode.DEFAULT, action).outcome,
                    ApprovalOutcome.REQUIRE_APPROVAL,
                )

    def test_auto_edit_allows_file_edits_but_not_arbitrary_commands(self):
        self.assertEqual(
            evaluate_action(ApprovalMode.AUTO_EDIT, ApprovalAction.FILE_EDIT).outcome,
            ApprovalOutcome.ALLOW,
        )
        self.assertEqual(
            evaluate_action(ApprovalMode.AUTO_EDIT, ApprovalAction.COMMAND).outcome,
            ApprovalOutcome.REQUIRE_APPROVAL,
        )
        self.assertEqual(
            evaluate_action(ApprovalMode.AUTO_EDIT, ApprovalAction.UNKNOWN).outcome,
            ApprovalOutcome.REQUIRE_APPROVAL,
        )

    def test_plan_mode_denies_mutating_or_unknown_actions(self):
        self.assertEqual(
            evaluate_action(ApprovalMode.PLAN, ApprovalAction.READ_ONLY).outcome,
            ApprovalOutcome.ALLOW,
        )
        for action in (ApprovalAction.FILE_EDIT, ApprovalAction.COMMAND, ApprovalAction.UNKNOWN):
            with self.subTest(action=action):
                self.assertEqual(
                    evaluate_action(ApprovalMode.PLAN, action).outcome,
                    ApprovalOutcome.DENY,
                )

    def test_unknown_mode_and_action_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown approval mode"):
            evaluate_action("all-powerful", ApprovalAction.FILE_EDIT)
        with self.assertRaisesRegex(ValueError, "Unknown approval action"):
            evaluate_action(ApprovalMode.DEFAULT, "delete-everything")


if __name__ == "__main__":
    unittest.main()
