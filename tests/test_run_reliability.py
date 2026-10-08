"""Regression checks for run control, concurrency and concrete recovery."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from sparkle_coder.config import Config
from sparkle_coder.agent import Agent
from sparkle_coder.explanations import simple_recovery
from sparkle_coder.monitor import Run
from sparkle_coder.provider import Completion
from sparkle_coder.state import Session
from sparkle_coder.webapp import AppService
from sparkle_coder.workspace import Workspace


class ScriptedProvider:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = 0

    def complete(self, messages, schemas):
        self.calls += 1
        return next(self.replies)


class ReliabilityTests(unittest.TestCase):
    def test_repeated_empty_reply_stops_with_saved_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Workspace(Path(folder))
            session = Session.create(workspace, "Explain this", [], {})
            session.state["task_mode"] = "ask"
            session.save()
            config = Config(base_url="http://127.0.0.1:8000/v1", max_steps=10)
            provider = ScriptedProvider([Completion("", [], {}) for _ in range(4)])
            status = Agent(workspace, session, config, provider, lambda command: True, emit=lambda _: None).run()
            self.assertEqual(status, "needs_input")
            self.assertEqual(provider.calls, 3)
            self.assertIn("empty answers three times", session.state["technical_summary"])
            self.assertEqual(session.state["recovery"]["action"], "connection")

    def test_invalid_model_format_does_not_loop_indefinitely(self):
        from sparkle_coder.provider import ModelError
        class InvalidProvider:
            calls = 0
            def complete(self, messages, schemas):
                self.calls += 1
                raise ModelError("Invalid model response: missing choices")
        with tempfile.TemporaryDirectory() as folder:
            workspace = Workspace(Path(folder))
            session = Session.create(workspace, "Explain this", [], {})
            session.state["task_mode"] = "ask"
            session.save()
            config = Config(base_url="http://127.0.0.1:8000/v1", max_steps=10)
            provider = InvalidProvider()
            status = Agent(workspace, session, config, provider, lambda command: True, emit=lambda _: None).run()
            self.assertEqual(status, "needs_input")
            self.assertEqual(provider.calls, 3)
            self.assertEqual(session.state["recovery"]["action"], "connection")

    def test_repeated_truncated_reply_stops_with_saved_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Workspace(Path(folder))
            session = Session.create(workspace, "Explain this", [], {})
            session.state["task_mode"] = "ask"
            session.save()
            config = Config(base_url="http://127.0.0.1:8000/v1", max_steps=10)
            provider = ScriptedProvider([Completion("incomplete", [], {}, "length") for _ in range(4)])
            status = Agent(workspace, session, config, provider, lambda command: True, emit=lambda _: None).run()
            self.assertEqual(status, "needs_input")
            self.assertEqual(provider.calls, 3)
            self.assertIn("incomplete answers three times", session.state["technical_summary"])

    def test_specific_input_question_survives_recovery(self):
        state = {"input_request": {"question": "Which database should this project use?",
                                   "next_step": "Reply with SQLite or PostgreSQL."}}
        result = simple_recovery(state, "Which database?\n\nReply.", "instructions")
        self.assertEqual(result["title"], "Your answer is needed")
        self.assertEqual(result["what_happened"], state["input_request"]["question"])
        self.assertEqual(result["next_step"], state["input_request"]["next_step"])

    def test_pause_waits_at_checkpoint_and_resume_releases_once(self):
        job = Run("project", "nemotron")
        job.status = "running"
        job.pause()
        job.pause()
        self.assertEqual(job.status, "pausing")
        thread = threading.Thread(target=job.checkpoint)
        thread.start()
        for _ in range(100):
            if job.status == "paused_by_user": break
            time.sleep(.01)
        self.assertEqual(job.status, "paused_by_user")
        self.assertTrue(job.public()["pause_requested"])
        job.resume()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(job.status, "running")
        self.assertFalse(job.public()["pause_requested"])
        self.assertEqual([e["kind"] for e in job.events],
                         ["pause_requested", "paused", "resumed"])

    def test_fast_pause_then_resume_records_one_cancellation(self):
        job = Run("project", "nemotron")
        job.status = "running"
        job.pause()
        job.resume()
        self.assertEqual(job.status, "running")
        self.assertEqual([e["kind"] for e in job.events],
                         ["pause_requested", "resumed"])
        with self.assertRaisesRegex(ValueError, "not waiting"):
            job.resume()

    def test_same_command_can_be_remembered_only_by_explicit_user_choice(self):
        job = Run("project", "nemotron")
        def approve():
            return job.approve("python -m unittest")
        results = []
        thread = threading.Thread(target=lambda: results.append(approve()))
        thread.start()
        for _ in range(100):
            if job.approval:
                break
            time.sleep(.01)
        self.assertTrue(job.approval)
        approval = job.approval["id"]
        with self.assertRaisesRegex(ValueError, "true or false"):
            job.answer(approval, True, "yes")
        job.answer(approval, True, True)
        thread.join(2)
        self.assertEqual(results, [True])
        self.assertTrue(approve())
        self.assertIsNone(job.approval)
        self.assertEqual(len([e for e in job.events if e["kind"] == "approval_requested"]), 1)
        self.assertEqual(len([e for e in job.events if e["kind"] == "approval_reused"]), 1)
        self.assertNotIn("dangerous-command", job.remembered_commands)

    def test_hosted_global_capacity_counts_each_run_not_each_account(self):
        import uuid
        from sparkle_coder.hosted import Tenants
        release = threading.Event()
        entered = threading.Event()
        class WaitingProvider:
            def complete(self, messages, schemas):
                entered.set()
                if not release.wait(5): raise RuntimeError("Test provider timeout.")
                return Completion("Done.", [], {"prompt_tokens": 1, "completion_tokens": 1})
        with tempfile.TemporaryDirectory() as folder:
            manager = Tenants(Path(folder), "https://sparkle.example", "R" * 64,
                              max_running=1, provider_factory=lambda config: WaitingProvider())
            try:
                identity = str(uuid.uuid4())
                app = manager.get(identity, "x" * 64, {"id": identity, "ready": True})
                a, b = [app.add_project(label) for label in ("A", "B")]
                first = app.start(a["id"], "Inspect A", task_mode="ask")
                self.assertTrue(entered.wait(3))
                with self.assertRaisesRegex(ValueError, "server is busy"):
                    app.start(b["id"], "Inspect B", task_mode="ask")
                manager.max_running = 2
                second = app.start(b["id"], "Inspect B", task_mode="ask")
                self.assertNotEqual(first["id"], second["id"])
                manager.max_running = 2
                with self.assertRaisesRegex(ValueError, "server is busy"):
                    app.start(app.add_project("C")["id"], "Inspect C", task_mode="ask")
            finally:
                release.set()
                for service in manager.apps.values():
                    for job in service.jobs.values():
                        if job.thread: job.thread.join(timeout=5)
                manager.close()

    def test_second_project_runs_without_interrupting_first(self):
        release = threading.Event()
        entered = threading.Event()
        class WaitingProvider:
            def complete(self, messages, schemas):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test provider wait expired.")
                return Completion("Done.", [], {"prompt_tokens": 2, "completion_tokens": 1})
        with tempfile.TemporaryDirectory() as folder:
            app = AppService(Path(folder), provider_factory=lambda config: WaitingProvider())
            try:
                app.configure({"base_url": "http://127.0.0.1:8000/v1", "api_key": "test-key"})
                first, second, third = [app.add_project(label, "") for label in ("First", "Second", "Third")]
                a = app.start(first["id"], "Inspect first project", task_mode="ask")
                self.assertTrue(entered.wait(3))
                b = app.start(second["id"], "Inspect second project", task_mode="ask")
                self.assertNotEqual(a["id"], b["id"])
                self.assertEqual(len(app.active_jobs()), 2)
                self.assertEqual(app.state()["active_run"]["id"], b["id"])
                with self.assertRaisesRegex(ValueError, "this project"):
                    app.start(second["id"], "Duplicate", task_mode="ask")
                with self.assertRaisesRegex(ValueError, "Two projects"):
                    app.start(third["id"], "Third", task_mode="ask")
                with app.lock:
                    app.data["selected_project"] = first["id"]
                state = app.state()
                self.assertEqual(state["active_run"]["id"], a["id"])
                self.assertEqual(len(state["active_runs"]), 2)
            finally:
                release.set()
                for job in app.jobs.values():
                    if job.thread: job.thread.join(timeout=5)
                app.close()
