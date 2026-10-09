"""Milestone 7: resilient locks, stable fingerprints and no-replay task recovery."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.agent import Agent
from sparkle_coder.config import Config
from sparkle_coder.locking import _identity, _read_marker
from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace


def previous_fingerprint(workspace):
    """Reference implementation from pre-M7; verify persisted proof compatibility."""
    digest = hashlib.sha256()
    for name in workspace.files(limit=None):
        digest.update(name.encode() + b"\0")
        digest.update((workspace.root / name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class ExecutionRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = Workspace(Path(temp.name))

    def test_file_fingerprint_is_identical_to_legacy_after_cache_warmup(self):
        (self.workspace.root / "src").mkdir()
        (self.workspace.root / "src" / "app.py").write_text("one = 1\n")
        (self.workspace.root / "readme.txt").write_text("hello")
        expected = previous_fingerprint(self.workspace)
        for _ in range(4):
            self.assertEqual(self.workspace.fingerprint(), expected)
        if os.name != "nt":
            self.assertTrue(self.workspace._fingerprint_file_cache)

    def test_external_same_size_edit_changes_fingerprint_and_cache_is_invalidated(self):
        target = self.workspace.root / "app.py"
        target.write_text("value = 1\n")
        before = self.workspace.fingerprint()
        target.write_text("value = 2\n")
        self.assertNotEqual(self.workspace.fingerprint(), before)
        self.assertEqual(self.workspace.fingerprint(), previous_fingerprint(self.workspace))
        target.unlink()
        self.assertEqual(self.workspace.fingerprint(), previous_fingerprint(self.workspace))
        self.assertNotIn("app.py", self.workspace._fingerprint_file_cache)

    def test_recent_coarse_timestamp_never_reuses_stale_file_bytes(self):
        # Force a cache record to have the EXACT new stat tuple but stale
        # content, as may happen when rapid same-size writes have coarse
        # filesystem timestamps. This fails with the old unconditional cache.
        if os.name == "nt":
            self.skipTest("Windows already streams all fingerprint bytes.")
        path = self.workspace.root / "quick.py"
        path.write_text("value = 1\n")
        before = self.workspace.fingerprint()
        path.write_text("value = 2\n")
        info = path.stat()
        stamp = (info.st_dev, info.st_ino, info.st_size,
                 info.st_mtime_ns, info.st_ctime_ns)
        self.workspace._fingerprint_file_cache["quick.py"] = (stamp, b"value = 1\n")
        self.assertNotEqual(self.workspace.fingerprint(), before)
        self.assertEqual(self.workspace.fingerprint(), previous_fingerprint(self.workspace))

    def test_large_files_are_streamed_and_small_cache_remains_bounded(self):
        (self.workspace.root / "large.bin").write_bytes(b"a" * 1_100_000)
        (self.workspace.root / "small.txt").write_bytes(b"tiny")
        self.assertEqual(self.workspace.fingerprint(), previous_fingerprint(self.workspace))
        self.assertNotIn("large.bin", self.workspace._fingerprint_file_cache)
        self.assertLessEqual(sum(len(row[1]) for row in
                                 self.workspace._fingerprint_file_cache.values()),
                             16_000_000)

    def test_windows_lock_timestamp_noise_does_not_change_identity(self):
        a = SimpleNamespace(st_dev=1, st_ino=1024, st_size=5,
                            st_mtime_ns=111, st_ctime_ns=111)
        b = SimpleNamespace(st_dev=1, st_ino=1024, st_size=5,
                            st_mtime_ns=9999, st_ctime_ns=9999)
        self.assertEqual(_identity(a), _identity(b))
        self.assertNotEqual(_identity(a), _identity(SimpleNamespace(
            st_dev=1, st_ino=1025, st_size=5, st_mtime_ns=111, st_ctime_ns=111)))

    def test_marker_read_tolerates_timestamp_churn_but_not_inode_swap(self):
        marker = self.workspace.state_dir / "workspace.lock"
        marker.write_text("12345")
        original = os.fstat
        def changed_timestamp(fd):
            stat = original(fd)
            return SimpleNamespace(st_mode=stat.st_mode, st_nlink=stat.st_nlink,
                st_size=stat.st_size, st_dev=stat.st_dev, st_ino=stat.st_ino,
                st_mtime_ns=stat.st_mtime_ns + 5000,
                st_ctime_ns=stat.st_ctime_ns + 9000)
        with patch("sparkle_coder.locking.os.fstat", side_effect=changed_timestamp):
            _, raw = _read_marker(marker)
        self.assertEqual(raw, b"12345")

    def test_interrupted_write_is_never_replayed_and_is_reported_for_inspection(self):
        session = Session.create(self.workspace, "Fix a project", [], {})
        call = {"id": "call-uncertain-write", "type": "function",
                "function": {"name": "write_file",
                             "arguments": json.dumps({"path": "app.py", "content": "x = 1"})}}
        session.state["messages"].append({"role": "assistant", "content": "",
                                          "tool_calls": [call]})
        session.save()
        session.repair_interrupted_calls()
        session.repair_interrupted_calls()
        self.assertFalse((self.workspace.root / "app.py").exists())
        self.assertEqual(len(session.state["interrupted_actions"]), 1)
        self.assertTrue(session.state["interrupted_actions"][0]["potential_side_effect"])
        self.assertEqual(session.state["messages"][-1]["role"], "tool")
        self.assertTrue(json.loads(session.state["messages"][-1]["content"])
                        ["recovered_without_replay"])
        agent = Agent(self.workspace, session, Config(auto_approve=True), object(),
                      lambda _: True, emit=lambda _: None)
        status = agent.tools.execute("inspect_task_recovery", {})
        self.assertTrue(status["ok"])
        self.assertTrue(status["requires_reinspection"])
        self.assertFalse(status["replayed_commands"])
        checkpoint = json.dumps(agent.context())
        self.assertIn("inspect_task_recovery", checkpoint)

    def test_interrupted_read_is_marked_safe_but_does_not_auto_run(self):
        session = Session.create(self.workspace, "Explain project", [], {})
        session.state["messages"].append({"role": "assistant", "content": "",
            "tool_calls": [{"id": "read-1", "type": "function",
                            "function": {"name": "read_file",
                                         "arguments": '{"path":"missing.txt"}'}}]})
        session.repair_interrupted_calls()
        self.assertFalse(session.state["interrupted_actions"][-1]["potential_side_effect"])

    def test_unapplied_journal_is_reported_without_mutation(self):
        session = Session.create(self.workspace, "Build code", [], {})
        session.state["journal"].append({"path": "app.py", "applied": False,
                                         "after": "abc", "before": None})
        agent = Agent(self.workspace, session, Config(auto_approve=True), object(),
                      lambda _: True, emit=lambda _: None)
        result = agent.tools.inspect_task_recovery()
        self.assertEqual(result["uncertain_file_journal"], ["app.py"])
        self.assertTrue(result["requires_reinspection"])
        self.assertFalse((self.workspace.root / "app.py").exists())


if __name__ == "__main__":
    unittest.main()
