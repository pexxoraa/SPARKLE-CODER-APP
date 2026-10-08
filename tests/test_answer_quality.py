"""Plain-language Ask answers, real conversation history, and opt-in exact formatting."""
import tempfile
import unittest
from pathlib import Path

from sparkle_coder.agent import Agent
from sparkle_coder.answers import display_reply, explicit_format_requested, plain_discussion_text
from sparkle_coder.config import Config
from sparkle_coder.provider import Completion
from sparkle_coder.state import Session
from sparkle_coder.webapp import AppService
from sparkle_coder.workspace import Workspace


class OneReply:
    def __init__(self, text):
        self.text = text

    def complete(self, *_):
        return Completion(self.text, [], {"prompt_tokens": 4, "completion_tokens": 16})


class AnswerQualityTests(unittest.TestCase):
    def test_plain_text_removes_decoration_without_destroying_content(self):
        raw = ("# Explanation\n\n**Short answer:** Use `SQLite`.\n"
               "- [x] Already tested\n- [ ] Needs testing\n"
               "1. Check `main.py`\n2. Run it again\n\n"
               "> Why: it is simple.\n\n"
               "| Choice | Trade-off |\n| --- | --- |\n| SQLite | Local only |\n"
               "\nYou can read [docs](https://example.test/docs).")
        cleaned = plain_discussion_text(raw)
        for token in ("**", "`", "##", "| --- |", "- [ ]", "- [x]"):
            self.assertNotIn(token, cleaned)
        for expected in ("Explanation", "Short answer: Use SQLite.", "Done: Already tested",
                         "To do: Needs testing", "Step 1: Check main.py", "Step 2: Run it again",
                         "SQLite — Local only", "docs (https://example.test/docs)"):
            self.assertIn(expected, cleaned)

    def test_inline_python_identifiers_survive_markdown_cleanup(self):
        cleaned = plain_discussion_text("Use `__init__` and `_private_`, not **broken**.")
        self.assertEqual(cleaned, "Use __init__ and _private_, not broken.")

    def test_fenced_code_is_kept_exact_but_not_as_a_markdown_fence(self):
        source = "Here is an example:\n\n```python\nvalue = 2 ** 3\nprint(value)\n```"
        answer = plain_discussion_text(source)
        self.assertNotIn("```", answer)
        self.assertIn("value = 2 ** 3\nprint(value)", answer)

    def test_repeated_paragraphs_are_removed_only_when_adjacent(self):
        answer = plain_discussion_text("Check the setup.\n\nCheck the setup.\n\nThen retry.\n\nCheck the setup.")
        self.assertEqual(answer, "Check the setup.\n\nThen retry.\n\nCheck the setup.")

    def test_exact_format_when_explicitly_requested(self):
        for prompt in ("Give me JSON", "Respond in markdown", "Write Python code",
                       "show me a code snippet", "As a table", "Provide a SQL script"):
            self.assertTrue(explicit_format_requested(prompt), prompt)
        for prompt in ("Fix my Python code", "Explain why the API is slow",
                       "Improve my software architecture", "What is JSON?"):
            self.assertFalse(explicit_format_requested(prompt), prompt)
        raw = "## Result\n- **value**: `1`"
        self.assertEqual(display_reply(raw, "Write Python code"), raw)
        self.assertEqual(display_reply(raw, "Explain this result"), "Result\nvalue: 1")

    def test_agent_ask_finishes_with_plain_summary_but_preserves_model_history(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(Path(temp))
            session = Session.create(workspace, "Explain this database", [], {})
            session.state["task_mode"] = "ask"
            session.save()
            raw = "## Answer\n\n- **SQLite** needs no separate server."
            agent = Agent(workspace, session, Config(), OneReply(raw),
                          lambda _: True, emit=lambda _: None)
            self.assertEqual(agent.run(), "answered")
            self.assertEqual(session.state["summary"], "Answer\n\nSQLite needs no separate server.")
            self.assertEqual([m["content"] for m in session.state["messages"]
                              if m["role"] == "assistant"], [raw])
            self.assertEqual(session.state["visible_message_indices"], [1])
            self.assertIn("Lead with the answer", agent.context()[0]["content"])
            self.assertIn("complex choice", agent.context()[0]["content"])
            self.assertNotIn("SELECTED TASK SKILLS", agent.context()[0]["content"])

    def test_rejected_build_answers_are_not_shown_until_verification_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            app = AppService(Path(temp) / "app")
            self.addCleanup(app.close)
            project = app.data["projects"][0]
            workspace = app.project(project["id"])[1]
            session = Session.create(workspace, "Fix the failing test", [], {})
            session.state["messages"].extend([
                {"role": "assistant", "content": "**Done** and verified."},
                {"role": "user", "content": "Runtime feedback: tests failed."},
                {"role": "assistant", "content": "**Done** and verified."},
            ])
            session.save()
            displayed = app.snapshot(project["id"], session.id)["messages"]
            self.assertEqual(displayed, [{"role": "user", "content": "Fix the failing test"}])
            self.assertEqual(len(session.state["messages"]), 4)
            session.state["visible_message_indices"] = [3]
            session.state["status"] = "checked"
            session.save()
            displayed = app.snapshot(project["id"], session.id)["messages"]
            self.assertEqual(displayed, [
                {"role": "user", "content": "Fix the failing test"},
                {"role": "assistant", "content": "Done and verified."}])

    def test_legacy_saved_answers_and_tool_narration_are_cleaned_only_for_display(self):
        with tempfile.TemporaryDirectory() as temp:
            app = AppService(Path(temp) / "app")
            self.addCleanup(app.close)
            project = app.data["projects"][0]
            workspace = app.project(project["id"])[1]
            session = Session.create(workspace, "Explain trade-offs", [], {})
            session.state["task_mode"] = "ask"
            session.state["status"] = "answered"
            session.state.pop("visible_message_indices")  # Previous release history
            session.state["messages"].append({
                "role": "assistant", "content": "**Running tests**", "tool_calls": [{
                    "id": "test", "type": "function",
                    "function": {"name": "list_files", "arguments": "{}"}}]})
            session.state["messages"].append({"role": "tool", "tool_call_id": "test",
                                               "content": "private diagnostics"})
            session.state["messages"].append({"role": "assistant",
                                              "content": "## Result\n\n- **First** option\n- **Second** option"})
            session.save()
            displayed = app.snapshot(project["id"], session.id)
            self.assertEqual(displayed["messages"], [
                {"role": "user", "content": "Explain trade-offs"},
                {"role": "assistant", "content": "Result\n\nFirst option\nSecond option"}])
            self.assertIn("**Running tests**", [m["content"] for m in
                                                 Session.load(workspace, session.id).state["messages"] if
                                                 m["role"] == "assistant"])

    def test_each_turn_keeps_its_requested_format_and_user_content_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            app = AppService(Path(temp) / "app")
            self.addCleanup(app.close)
            project = app.data["projects"][0]
            workspace = app.project(project["id"])[1]
            session = Session.create(workspace, "Explain this function", [], {})
            session.state["task_mode"] = "ask"
            session.state["messages"].append({"role": "assistant", "content": "# Short\n- answer"})
            session.state["messages"].append({"role": "user", "content": "Respond in markdown"})
            session.state["user_requests"] = ["Explain this function", "Respond in markdown"]
            session.state["messages"].append({"role": "assistant", "content": "# Exact\n- **bold**"})
            session.state["visible_message_indices"] = [1, 3]
            session.save()
            displayed = app.snapshot(project["id"], session.id)["messages"]
            self.assertEqual(displayed, [
                {"role": "user", "content": "Explain this function"},
                {"role": "assistant", "content": "Short\nanswer"},
                {"role": "user", "content": "Respond in markdown"},
                {"role": "assistant", "content": "# Exact\n- **bold**"}])


if __name__ == "__main__":
    unittest.main()
