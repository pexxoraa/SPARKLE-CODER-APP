"""Windows atomic session saves tolerate short sharing violations, not permanent errors."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace, atomic_write


def windows_permission(code):
    error = PermissionError(13, "Windows sharing/access temporarily unavailable")
    error.winerror = code
    return error


class AtomicWriteRetryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_transient_windows_sharing_errors_preserve_atomic_bytes(self):
        path = self.root / "state.json"
        path.write_bytes(b"older file")
        real_replace = os.replace
        called = []
        def flaky(source, target):
            called.append(1)
            if len(called) <= 2:
                self.assertEqual(path.read_bytes(), b"older file")
                raise windows_permission(32 if len(called) == 1 else 5)
            return real_replace(source, target)
        with patch("sparkle_coder.workspace.IS_WINDOWS", True), \
             patch("sparkle_coder.workspace.os.replace", side_effect=flaky), \
             patch("sparkle_coder.workspace.time.sleep") as sleep:
            atomic_write(path, b"new valid bytes", 0o600)
        self.assertEqual(path.read_bytes(), b"new valid bytes")
        self.assertEqual(len(called), 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertFalse(list(self.root.glob(".nemotron-tmp-*")))

    def test_permanent_windows_sharing_failure_keeps_existing_bytes(self):
        path = self.root / "state.json"
        path.write_bytes(b"safe old session")
        with patch("sparkle_coder.workspace.IS_WINDOWS", True), \
             patch("sparkle_coder.workspace.os.replace",
                   side_effect=windows_permission(33)) as replace, \
             patch("sparkle_coder.workspace.time.sleep") as pause:
            with self.assertRaises(PermissionError):
                atomic_write(path, b"cannot commit")
        self.assertEqual(replace.call_count, 6)
        self.assertEqual(pause.call_count, 5)
        self.assertEqual(path.read_bytes(), b"safe old session")
        self.assertFalse(list(self.root.glob(".nemotron-tmp-*")))

    def test_non_transient_permission_error_is_never_retried(self):
        for winerror in (None, 2, 87):
            with self.subTest(winerror=winerror):
                path = self.root / "guarded.json"
                path.write_bytes(b"original")
                error = windows_permission(winerror) if winerror else PermissionError("Denied")
                with patch("sparkle_coder.workspace.IS_WINDOWS", True), \
                     patch("sparkle_coder.workspace.os.replace",
                           side_effect=error) as replace, \
                     patch("sparkle_coder.workspace.time.sleep") as sleep:
                    with self.assertRaises(PermissionError):
                        atomic_write(path, b"proposed")
                replace.assert_called_once()
                sleep.assert_not_called()
                self.assertEqual(path.read_bytes(), b"original")

    def test_other_platforms_attempt_once(self):
        path = self.root / "state.json"
        with patch("sparkle_coder.workspace.IS_WINDOWS", False), \
             patch("sparkle_coder.workspace.os.replace",
                   side_effect=windows_permission(32)) as replace, \
             patch("sparkle_coder.workspace.time.sleep") as sleep:
            with self.assertRaises(PermissionError):
                atomic_write(path, b"data")
        replace.assert_called_once()
        sleep.assert_not_called()

    def test_session_save_roundtrip_after_transient_sharing_violation(self):
        workspace = Workspace(self.root / "project")
        session = Session.create(workspace, "Write a project", [], {})
        state_path = session.directory / "state.json"
        before = state_path.read_bytes()
        real_replace = os.replace
        count = [0]
        def flaky(source, target):
            if Path(target) == state_path and count[0] == 0:
                count[0] += 1
                raise windows_permission(5)
            return real_replace(source, target)
        session.state["summary"] = "Saved successfully"
        with patch("sparkle_coder.workspace.IS_WINDOWS", True), \
             patch("sparkle_coder.workspace.os.replace", side_effect=flaky), \
             patch("sparkle_coder.workspace.time.sleep"):
            session.save()
        self.assertEqual(count[0], 1)
        self.assertNotEqual(state_path.read_bytes(), before)
        self.assertEqual(Session.load(workspace, session.id).state["summary"], "Saved successfully")


if __name__ == "__main__":
    unittest.main()
