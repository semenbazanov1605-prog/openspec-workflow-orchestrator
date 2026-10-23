import unittest
from workflow_orchestrator.adapters.git import GitSnapshot


class GitSnapshotTests(unittest.TestCase):
    def test_clean_worktree(self):
        self.assertTrue(GitSnapshot("abc", "").clean)

    def test_dirty_worktree(self):
        self.assertFalse(GitSnapshot("abc", " M src/Main.java").clean)

    def test_unknown_worktree(self):
        self.assertIsNone(GitSnapshot(None, None, "git missing").clean)


if __name__ == "__main__":
    unittest.main()
