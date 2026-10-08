"""Milestone 8: stable, privacy-safe progress metadata across desktop and cloud."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from sparkle_coder.state import Session
from sparkle_coder.webapp import AppService
from sparkle_coder.workspace import Workspace


class WorkflowIntelligenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.workspace = Workspace(Path(folder.name))
        self.session = Session.create(self.workspace, "Improve my app", [], {})
        self.fake = SimpleNamespace(
            project=lambda _id: ({"id": "project"}, self.workspace),
            _repair_orphaned_session=lambda session: session,
        )

    def snapshot(self):
        return AppService.snapshot(self.fake, "project", self.session.id, include_events=False)

    def test_legacy_sessions_have_zero_interruption_counts(self):
        result = self.snapshot()
        self.assertEqual(result["interruption_review"], {
            "actions": 0, "possible_side_effects": 0, "uncertain_file_edits": 0,
        })
        self.assertEqual(result["messages"][0]["content"], "Improve my app")

    def test_interruption_summary_never_returns_saved_sensitive_arguments(self):
        self.session.state["interrupted_actions"] = [
            {"id": "a", "tool": "read_file", "resolved": False,
             "potential_side_effect": False, "arguments": {"secret": "PRIVATE_TOKEN_123"}},
            {"id": "b", "tool": "run_command", "resolved": False,
             "potential_side_effect": True, "command": "PRIVATE_SECRET"},
            {"id": "c", "tool": "write_file", "resolved": True,
             "potential_side_effect": True, "content": "NEVER_EXPOSE_CONTENT"},
        ]
        self.session.state["journal"] = [
            {"path": "app.py", "applied": False},
            {"path": "readme.md", "applied": True},
        ]
        self.session.save()
        report = self.snapshot()
        self.assertEqual(report["interruption_review"], {
            "actions": 2, "possible_side_effects": 1, "uncertain_file_edits": 1,
        })
        self.assertFalse(any(key in report for key in (
            "interrupted_actions", "journal", "arguments", "secret")))
        self.assertNotIn("PRIVATE_TOKEN_123", str(report))
        self.assertNotIn("PRIVATE_SECRET", str(report))
        self.assertNotIn("NEVER_EXPOSE_CONTENT", str(report))
        self.assertEqual(report["changed_files"], ["app.py", "readme.md"])

    def test_resolved_history_does_not_count_as_pending(self):
        self.session.state["interrupted_actions"] = [
            {"id": str(i), "resolved": True, "potential_side_effect": True}
            for i in range(4)
        ]
        self.session.save()
        report = self.snapshot()
        self.assertEqual(report["interruption_review"]["actions"], 0)
        self.assertEqual(report["interruption_review"]["possible_side_effects"], 0)


if __name__ == "__main__":
    unittest.main()
