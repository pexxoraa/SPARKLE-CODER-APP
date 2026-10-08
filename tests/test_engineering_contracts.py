"""Milestone 2: prove domain contracts use real, fresh, separate check evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.agent import Agent
from sparkle_coder.config import Config
from sparkle_coder.engineering import DOMAIN_IDS, detect_domains
from sparkle_coder.engineering_contracts import (
    FACETS, OBLIGATIONS, evaluate_contract, execution_plan, link_evidence,
    required_domains,
)
from sparkle_coder.python_runtime import python_command
from sparkle_coder.skills import select_skills
from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Workspace(Path(self.tmp.name))
        self.session = Session.create(self.workspace, "Build a Rust service", [], {})
        self.agent = Agent(self.workspace, self.session, Config(auto_approve=True),
                           object(), lambda _: True, emit=lambda _: None)
        self.domains = detect_domains(self.workspace, "Build a Rust service")

    def check(self, statement):
        return self.agent.tools.verify(python_command("-c", statement))["check_id"]

    def test_all_fourteen_domains_have_same_enforced_dimensions(self):
        self.assertEqual(tuple(OBLIGATIONS), DOMAIN_IDS)
        for identity in DOMAIN_IDS:
            with self.subTest(domain=identity):
                self.assertEqual(len(OBLIGATIONS[identity]), 2)
                self.assertTrue(all(OBLIGATIONS[identity]))

    def test_plan_read_only_does_not_invoke_programs(self):
        (self.workspace.root / "Cargo.toml").write_text("[package]\nname='safe'\n")
        with patch("subprocess.Popen", side_effect=AssertionError("must not run")), \
             patch("subprocess.run", side_effect=AssertionError("must not run")), \
             patch("sparkle_coder.engineering.shutil.which", return_value=None):
            plan = self.agent.tools.execute("plan_engineering", {})
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["readiness"], "needs_toolchain_setup")
        self.assertEqual(plan["verification"]["blocking"][0]["domain"], "systems_programming")
        self.assertEqual([x["phase"] for x in plan["steps"]],
                         ["inspect", "prepare", "implement", "verify", "report"])
        self.assertEqual(self.session.state["checks"], [])

    def test_missing_and_failed_evidence_cannot_fulfill_contract(self):
        report = evaluate_contract(self.workspace, self.session.state, self.domains)
        self.assertEqual(report["blocking"][0]["missing"], ["behavior", "target"])
        bad = self.check("assert False")
        with self.assertRaisesRegex(ValueError, "failed"):
            link_evidence(self.workspace, self.session.state, "systems_programming",
                          "behavior", bad, "Checks error behavior and bounds")
        self.assertEqual(self.session.state.get("engineering_evidence"), None)

    def test_two_distinct_fresh_checks_can_be_linked(self):
        a = self.check("assert 2 + 2 == 4")
        # Test contract logic without needing the Rust compiler on CI.
        with patch.object(self.agent.tools.runner, "run",
                          return_value={"ok": True, "exit_code": 0,
                                        "output": "Mocked cargo test result"}):
            b = self.agent.tools.verify("cargo test")["check_id"]
        first = self.agent.tools.execute("record_engineering_evidence", {
            "domain": "systems_programming", "facet": "behavior", "check_id": a,
            "reason": "Checks a concrete arithmetic behavior with a real executed assertion."})
        self.assertTrue(first["ok"])
        self.assertEqual(first["blocking"][0]["missing"], ["target"])
        duplicate = self.agent.tools.execute("record_engineering_evidence", {
            "domain": "systems_programming", "facet": "target", "check_id": a,
            "reason": "Repeat the same check as alleged integration evidence."})
        self.assertFalse(duplicate["ok"])
        second = self.agent.tools.execute("record_engineering_evidence", {
            "domain": "systems_programming", "facet": "target", "check_id": b,
            "reason": "Records a separate executed test while coverage still needs review."})
        self.assertTrue(second["ok"])
        self.assertEqual(second["blocking"], [])
        self.assertEqual(second["contracts"][0]["semantic_coverage"],
                         "agent_asserted_not_independently_audited")

    def test_changed_files_and_environment_invalidate_past_links(self):
        a = self.check("assert 2 + 2 == 4")
        # Test contract logic without needing the Rust compiler on CI.
        with patch.object(self.agent.tools.runner, "run",
                          return_value={"ok": True, "exit_code": 0,
                                        "output": "Mocked cargo test result"}):
            b = self.agent.tools.verify("cargo test")["check_id"]
        for facet, check in zip(FACETS, (a, b)):
            self.agent.tools.record_engineering_evidence(
                "systems_programming", facet, check, "Executed a real standalone test with explicit assertions.")
        self.assertEqual(evaluate_contract(self.workspace, self.session.state, self.domains)["blocking"], [])
        (self.workspace.root / "main.rs").write_text("fn main() { println!(\"hi\"); }\n")
        report = evaluate_contract(self.workspace, self.session.state, self.domains)
        self.assertEqual(report["blocking"][0]["missing"], ["behavior", "target"])
        with self.assertRaisesRegex(ValueError, "stale"):
            self.agent.tools.record_engineering_evidence(
                "systems_programming", "behavior", a, "Stale test must not be linked again.")
        self.assertFalse(self.agent.verify_completion()[0])

    def test_replayed_check_ids_stay_invalid_after_environment_change(self):
        a = self.check("assert 2 + 2 == 4")
        self.agent.tools.record_engineering_evidence(
            "systems_programming", "behavior", a, "Check validates one real observed behavior of the change.")
        self.session.state["environment_revision"] = self.session.state.get("environment_revision", 0) + 1
        report = evaluate_contract(self.workspace, self.session.state, self.domains)
        self.assertEqual(report["blocking"][0]["missing"], ["behavior", "target"])

    def test_ask_and_existing_efficient_web_mode_are_not_blocked(self):
        prompt = detect_domains(self.workspace, "Build a frontend website")
        self.assertEqual(required_domains(prompt, "simple_web"), [])
        self.assertEqual(required_domains(prompt, "standard", "ask"), [])
        self.assertTrue(required_domains(prompt, "standard", "build"))

    def test_unrelated_domain_evidence_cannot_be_forged(self):
        a = self.check("assert 3 >= 2")
        result = self.agent.tools.execute("record_engineering_evidence", {
            "domain": "embedded_iot", "facet": "behavior", "check_id": a,
            "reason": "This Rust service check does not establish embedded firmware behavior."})
        self.assertFalse(result["ok"])
        self.assertIn("not selected", result["error"])

    def test_inert_check_is_rejected_even_if_shell_returned_success(self):
        check = self.agent.tools.verify("true")["check_id"]
        result = self.agent.tools.execute("record_engineering_evidence", {
            "domain": "systems_programming", "facet": "behavior", "check_id": check,
            "reason": "A no-op passing command cannot validate any implementation."})
        self.assertFalse(result["ok"])
        self.assertIn("inert command", result["error"])

    def test_generic_arithmetic_check_cannot_validate_rust_target(self):
        a = self.check("assert 2 + 2 == 4")
        result = self.agent.tools.execute("record_engineering_evidence", {
            "domain": "systems_programming", "facet": "target", "check_id": a,
            "reason": "Generic arithmetic success cannot prove a Rust compiler build."})
        self.assertFalse(result["ok"])
        self.assertIn("domain build/test tool", result["error"])

    def test_recorded_links_survive_session_reload_without_false_success(self):
        check_id = self.check("assert 5 + 2 == 7")
        self.agent.tools.execute("record_engineering_evidence", {
            "domain": "systems_programming", "facet": "behavior",
            "check_id": check_id,
            "reason": "Recorded passing assertion validates one claimed behavior but not target integration."})
        restored = Session.load(self.workspace, self.session.id)
        restored_view = evaluate_contract(self.workspace, restored.state, self.domains)
        self.assertEqual(restored_view["blocking"][0]["missing"], ["target"])
        self.assertEqual(restored_view["contracts"][0]["facets"][0]["check_id"], check_id)

    def test_unknown_skill_limit_does_not_drown_out_project_domain(self):
        skills = select_skills("Fix the project", domains=["embedded_iot"], limit=5)
        self.assertIn("embedded_iot", skills)
        self.assertIn("debugging_mastery", skills)

    def test_completion_gate_applies_to_new_standard_domain_build(self):
        check = self.check("assert 7 == 7")
        self.assertFalse(self.agent.verify_completion()[0])
        self.agent.tools.record_engineering_evidence("systems_programming", "behavior", check,
             "A recorded behavioral check alone does not prove the required target build.")
        passed, message = self.agent.verify_completion()
        self.assertFalse(passed)
        self.assertIn("Engineering acceptance", message)
        self.assertIn("target", message)


if __name__ == "__main__":
    unittest.main()
