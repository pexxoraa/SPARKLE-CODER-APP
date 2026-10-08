"""Windows readers must tolerate temporary session-file sharing but never hide errors."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace


def winerror(code):
    error = PermissionError(13, "Temporary Windows file-sharing conflict")
    error.winerror = code
    return error


class SessionReadRecoveryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.workspace = Workspace(Path(folder.name))
        self.session = Session.create(self.workspace, "Build a project", [], {})
        self.session.state["summary"] = "real persisted work"
        self.session.save()
        self.path = self.session.directory / "state.json"

    def simulated_reader(self, error, attempts):
        original = Path.read_text
        calls = [0]
        def reader(path, *args, **kwargs):
            if path == self.path:
                calls[0] += 1
                if calls[0] <= attempts:
                    raise error
            return original(path, *args, **kwargs)
        return calls, reader

    def test_short_windows_sharing_error_then_valid_saved_state(self):
        calls, reader = self.simulated_reader(winerror(32), 2)
        with patch("sparkle_coder.state.IS_WINDOWS", True), \
             patch.object(Path, "read_text", reader), \
             patch("sparkle_coder.state.time.sleep") as sleep:
            restored = Session.load(self.workspace, self.session.id)
        self.assertEqual(restored.state["summary"], "real persisted work")
        self.assertEqual(calls[0], 3)
        self.assertEqual(sleep.call_count, 2)

    def test_permanent_access_denied_is_not_silently_accepted(self):
        calls, reader = self.simulated_reader(winerror(5), 10)
        with patch("sparkle_coder.state.IS_WINDOWS", True), \
             patch.object(Path, "read_text", reader), \
             patch("sparkle_coder.state.time.sleep") as sleep:
            with self.assertRaises(PermissionError):
                Session.load(self.workspace, self.session.id)
        self.assertEqual(calls[0], 6)
        self.assertEqual(sleep.call_count, 5)
        self.assertEqual(self.session.state["summary"], "real persisted work")

    def test_nonwindows_read_does_not_retry(self):
        calls, reader = self.simulated_reader(winerror(32), 2)
        with patch("sparkle_coder.state.IS_WINDOWS", False), \
             patch.object(Path, "read_text", reader), \
             patch("sparkle_coder.state.time.sleep") as sleep:
            with self.assertRaises(PermissionError):
                Session.load(self.workspace, self.session.id)
        self.assertEqual(calls[0], 1)
        sleep.assert_not_called()

    def test_unrelated_permission_error_does_not_retry(self):
        calls, reader = self.simulated_reader(winerror(87), 2)
        with patch("sparkle_coder.state.IS_WINDOWS", True), \
             patch.object(Path, "read_text", reader), \
             patch("sparkle_coder.state.time.sleep") as sleep:
            with self.assertRaises(PermissionError):
                Session.load(self.workspace, self.session.id)
        self.assertEqual(calls[0], 1)
        sleep.assert_not_called()

    def test_corrupt_json_still_fails_without_repair_or_guesswork(self):
        self.path.write_text("{ incomplete state")
        with patch("sparkle_coder.state.IS_WINDOWS", True), \
             patch("sparkle_coder.state.time.sleep") as sleep:
            with self.assertRaises(ValueError):
                Session.load(self.workspace, self.session.id)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
