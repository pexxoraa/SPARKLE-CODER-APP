"""Milestone 6: existing-project edit reliability, focused diagnostics, context budget."""
import json
from pathlib import Path
import tempfile
import unittest

from sparkle_coder.agent import Agent
from sparkle_coder.change_intelligence import capture_source_baseline, inspect_change_impact
from sparkle_coder.config import Config
from sparkle_coder.efficiency import compact_group
from sparkle_coder.repair_focus import repair_focus
from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace


class AgentIntelligenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.workspace = Workspace(Path(folder.name))

    def write(self, path, contents="value = 1\n"):
        target = self.workspace.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)
        return target

    def agent(self, goal="Fix the existing Python application", *, requested=True):
        session = Session.create(self.workspace, goal, [], {})
        if requested:
            session.state["requested_change"] = {
                "goal": goal,
                "baseline": self.workspace.fingerprint(),
                "source_baseline": capture_source_baseline(self.workspace, goal),
                "journal_start": len(session.state["journal"]),
            }
        return Agent(self.workspace, session, Config(auto_approve=True), object(),
                     lambda _: True, emit=lambda _: None)

    def test_explicit_fix_cannot_succeed_by_creating_an_unrelated_new_file(self):
        self.write("app.py", "value = 1\n")
        agent = self.agent()
        agent.tools.execute("write_file", {"path": "unrelated.py", "content": "other = 4\n"})
        agent.tools.execute("verify", {"command": "python3 -c \"assert 2+2 == 4\""})
        passed, why = agent.verify_completion()
        self.assertFalse(passed)
        self.assertIn("pre-existing", why)
        impact = agent.tools.execute("inspect_change_impact", {})
        self.assertTrue(impact["ok"])
        self.assertTrue(impact["enforced"])
        self.assertEqual(impact["existing_modified"], [])

    def test_editing_existing_source_and_rechecking_can_complete(self):
        self.write("app.py", "value = 1\n")
        agent = self.agent()
        old = agent.tools.execute("read_file", {"path": "app.py"})
        changed = agent.tools.execute("write_file", {
            "path": "app.py", "content": "value = 2\n",
            "expected_sha256": old["sha256"]})
        self.assertTrue(changed["ok"])
        checked = agent.tools.execute("verify", {
            "command": "python3 -c \"from app import value; assert value == 2\""})
        self.assertTrue(checked["ok"], checked.get("output"))
        passed, why = agent.verify_completion()
        self.assertTrue(passed, why)
        impact = agent.tools.inspect_change_impact()
        self.assertEqual(impact["existing_modified"], ["app.py"])

    def test_add_a_new_file_request_does_not_enforce_existing_edit(self):
        self.write("app.py")
        baseline = capture_source_baseline(self.workspace, "Add a new helper.py file")
        self.assertFalse(baseline["strict"])
        impact = inspect_change_impact(self.workspace, {"source_baseline": baseline})
        self.assertFalse(impact["enforced"])

    def test_unbounded_projects_are_not_falsely_declared_exhaustive(self):
        for i in range(501):
            self.write(f"pkg/mod_{i:04d}.py")
        baseline = capture_source_baseline(self.workspace, "Fix existing Python code")
        self.assertFalse(baseline["complete"])
        self.assertEqual(baseline["reason"], "too_many_existing_source_files")
        self.assertFalse(inspect_change_impact(
            self.workspace, {"source_baseline": baseline})["enforced"])

    def test_legacy_sessions_without_baseline_remain_usable(self):
        self.write("app.py")
        impact = inspect_change_impact(self.workspace, {"baseline": "old", "goal": "Fix"})
        self.assertEqual(impact["status"], "legacy_baseline_unavailable")
        self.assertFalse(impact["enforced"])

    def test_existing_source_delete_is_detected_not_confused_with_unrelated_new_file(self):
        target = self.write("outdated.py")
        baseline = capture_source_baseline(self.workspace, "Remove outdated implementation")
        target.unlink()
        report = inspect_change_impact(self.workspace, {"source_baseline": baseline})
        self.assertEqual(report["existing_modified"], ["outdated.py"])

    def test_read_only_repair_diagnostic_prioritizes_fresh_required_failures(self):
        self.write("app.py", "value = 1\n")
        agent = self.agent(requested=False)
        fingerprint = self.workspace.fingerprint()
        agent.session.state["checks"].extend([
            {"id": "check-optional", "command": "python3 -m pytest", "cwd": ".",
             "fingerprint": fingerprint, "environment_revision": 0,
             "ok": False, "exit_code": 1, "required": False, "source": "agent",
             "output": "AssertionError: expected 1 but got 2\nFile \"app.py\", line 1"},
            {"id": "check-required", "command": "python3 -m unittest", "cwd": ".",
             "fingerprint": fingerprint, "environment_revision": 0,
             "ok": False, "exit_code": 1, "required": True, "source": "user",
             "output": "SyntaxError: bad syntax\nFile \"app.py\", line 1"},
        ])
        result = agent.tools.execute("inspect_repair_focus", {})
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "repair_needed")
        self.assertEqual(result["failures"][0]["check_id"], "check-required")
        self.assertEqual(result["failures"][0]["category"], "syntax_or_compile")
        self.assertEqual(result["failures"][0]["source_files"], ["app.py"])
        self.assertTrue(result["failures"][0]["required"])

    def test_stale_checks_cannot_produce_repair_suggestions(self):
        self.write("app.py")
        agent = self.agent(requested=False)
        agent.session.state["checks"].append({
            "id": "check-stale", "command": "pytest", "cwd": ".",
            "fingerprint": "old-project", "environment_revision": 0, "ok": False,
            "output": "SyntaxError: app.py"})
        result = repair_focus(self.workspace, agent.session.state)
        self.assertEqual(result["status"], "no_fresh_failure")
        self.assertEqual(result["failures"], [])

    def test_old_inspection_is_metadata_only_and_current_source_not_faked(self):
        group = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call-1", "type": "function",
                 "function": {"name": "read_file", "arguments": json.dumps({"path": "app.py"})}}]},
            {"role": "tool", "tool_call_id": "call-1",
             "content": json.dumps({"content": "SECRET_PAST_TEXT" * 5000,
                                    "sha256": "older"})},
        ]
        old = compact_group(group, recent=False)
        self.assertLess(len(json.dumps(old)), 420)
        self.assertIn("read_file app.py", old[0]["content"])
        self.assertNotIn("SECRET_PAST_TEXT", json.dumps(old))
        self.assertIn("SECRET_PAST_TEXT", json.dumps(group))
        recent = compact_group(group, recent=True)
        self.assertIn("SECRET_PAST_TEXT", json.dumps(recent))

    def test_effort_promotion_preserves_nonmobile_tool_filter(self):
        session = Session.create(self.workspace, "build a static website for a photo studio", [], {})
        agent = Agent(self.workspace, session, Config(auto_approve=True),
                      object(), lambda _: True, emit=lambda _: None)
        names_before = {s["function"]["name"] for s in agent.schemas}
        self.assertNotIn("probe_target_devices", names_before)
        self.assertTrue(agent.promote_effort("test"))
        names_after = {s["function"]["name"] for s in agent.schemas}
        self.assertNotIn("probe_target_devices", names_after)
        self.assertIn("inspect_change_impact", names_after)


if __name__ == "__main__":
    unittest.main()
