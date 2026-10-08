"""Project deletion, saved history, grounded brief drafts, and skill persistence."""
import json
from pathlib import Path
import tempfile
import unittest

from sparkle_coder.monitor import Run
from sparkle_coder.state import Session
from sparkle_coder.webapp import AppService
from sparkle_coder.workspace import Workspace, write_json
from sparkle_coder.brief import read_brief, save_brief


class ProjectManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = AppService(Path(self.tmp.name) / "app")
        self.addCleanup(self.app.close)

    def test_creation_starts_brief_without_inventing_requirements(self):
        project = self.app.add_project("My Portfolio", purpose="Showcase verified projects")
        workspace = self.app.project(project["id"])[1]
        brief = read_brief(workspace)["brief"]
        self.assertEqual(brief["purpose"], "Showcase verified projects")
        self.assertEqual(brief["requirements"], [])
        self.assertIn(project["id"], [p["id"] for p in self.app.state()["projects"]])
        self.assertTrue(next(p["managed"] for p in self.app.state()["projects"] if p["id"] == project["id"]))
        with self.assertRaisesRegex(ValueError, "under 2000"):
            self.app.add_project("Too long", purpose="x" * 2001)
        self.assertNotIn("Too long", [p["name"] for p in self.app.state()["projects"]])

    def test_unregistration_preserves_files_and_history(self):
        project = self.app.add_project("Keep work")
        workspace = self.app.project(project["id"])[1]
        source = workspace.root / "index.html"
        source.write_text("<h1>Keep this</h1>")
        session = Session.create(workspace, "Build website", [], {})
        with self.assertRaisesRegex(ValueError, "exact project name"):
            self.app.delete_project(project["id"], "Other name")
        with self.assertRaisesRegex(ValueError, "project name"):
            self.app.delete_project(project["id"], "")
        self.assertTrue(self.app.delete_project(project["id"], "Keep work")["removed"])
        self.assertTrue(source.exists())
        self.assertTrue(session.directory.exists())
        self.assertNotIn(project["id"], [p["id"] for p in self.app.state()["projects"]])

    def test_managed_permanent_delete_never_follows_other_paths(self):
        project = self.app.add_project("Delete only this")
        workspace = self.app.project(project["id"])[1]
        (workspace.root / "temporary.txt").write_text("delete")
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("must survive")
        (workspace.root / "link").symlink_to(outside)
        result = self.app.delete_project(project["id"], "Delete only this", True)
        self.assertTrue(result["files_deleted"])
        self.assertFalse(workspace.root.exists())
        self.assertEqual(outside.read_text(), "must survive")
        ext = Path(self.tmp.name) / "external"
        ext.mkdir()
        (ext / "original.txt").write_text("keep")
        project = self.app.add_project("External", str(ext))
        with self.assertRaisesRegex(ValueError, "Only available SPARKLE-managed"):
            self.app.delete_project(project["id"], "External", True)
        self.assertTrue((ext / "original.txt").exists())
        self.app.delete_project(project["id"], "External")
        self.assertTrue((ext / "original.txt").exists())

    def test_running_project_cannot_be_deleted(self):
        project = self.app.add_project("Busy")
        job = Run(project["id"], "nemotron")
        job.status = "running"
        self.app.jobs[job.id] = job
        with self.assertRaisesRegex(ValueError, "running task"):
            self.app.delete_project(project["id"], "Busy", True)
        self.assertTrue(Path(project["path"]).is_dir())
        del self.app.jobs[job.id]

    def test_single_and_bulk_history_deletion_keep_project_files(self):
        project = self.app.add_project("History")
        workspace = self.app.project(project["id"])[1]
        source = workspace.root / "keep.txt"
        source.write_text("user source")
        a = Session.create(workspace, "First conversation", [], {})
        b = Session.create(workspace, "Second conversation", [], {})
        write_json(workspace.state_dir / "skill-metrics.json",
                   {"version": 1, "sessions": {a.id: {"skills": ["visual_qa"]}, b.id: {"skills": []}}})
        self.assertEqual(self.app.delete_session(project["id"], a.id)["deleted"], a.id)
        self.assertFalse(a.directory.exists())
        self.assertTrue(b.directory.exists())
        self.assertEqual(source.read_text(), "user source")
        data = json.loads((workspace.state_dir / "skill-metrics.json").read_text())
        self.assertNotIn(a.id, data["sessions"])
        self.assertEqual(self.app.clear_history(project["id"])["deleted"], 1)
        self.assertFalse(b.directory.exists())
        self.assertEqual(self.app.history(project["id"]), [])
        self.assertEqual(source.read_text(), "user source")

    def test_unexpected_history_symlink_prevents_bulk_deletion(self):
        project = self.app.add_project("Safe cleanup")
        workspace = self.app.project(project["id"])[1]
        session = Session.create(workspace, "Save this", [], {})
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "data").write_text("important")
        (session.directory.parent / ("f" * 12)).symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.app.clear_history(project["id"])
        self.assertTrue(session.directory.exists())
        self.assertTrue((outside / "data").exists())

    def test_brief_draft_is_based_only_on_real_user_task_goals(self):
        project = self.app.add_project("Draft from my work")
        workspace = self.app.project(project["id"])[1]
        first = Session.create(workspace, "Build a contact form", [], {})
        later = Session.create(workspace, "Make the contact form keyboard accessible", [], {})
        # Creation order remains stable even when earlier tasks are revisited.
        self.assertLess(first.state["created"], later.state["created"])
        first.state["summary"] = "Reviewed the initial design later"
        first.save()
        question = Session.create(workspace, "What does Python mean?", [], {})
        question.state["task_mode"] = "ask"
        question.save()
        suggestion = self.app.suggest_brief(project["id"])
        self.assertEqual(suggestion["sources"], 2)
        self.assertEqual(suggestion["brief"]["purpose"], "Build a contact form")
        self.assertIn("Make the contact form keyboard accessible", suggestion["brief"]["requirements"])
        self.assertEqual(read_brief(workspace)["brief"]["purpose"], "")
        edited = suggestion["brief"]
        edited["requirements"].append("User-verified requirement")
        saved = save_brief(workspace, edited, suggestion["revision"])
        self.assertIn("User-verified requirement", saved["brief"]["requirements"])
        self.assertEqual(self.app.suggest_brief(project["id"])["revision"], saved["revision"])

    def test_deleted_project_id_cannot_start_work(self):
        project = self.app.add_project("Removed")
        self.app.delete_project(project["id"], "Removed")
        with self.assertRaisesRegex(ValueError, "Project"):
            self.app.project(project["id"])
