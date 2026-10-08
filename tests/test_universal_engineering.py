"""Milestone 1B contract tests: truthful detection across all 14 engineering domains."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.agent import Agent
from sparkle_coder.config import Config
from sparkle_coder.diagnostics import inspect_setup
from sparkle_coder.engineering import DOMAIN_IDS, DOMAINS, detect_domains, detect_toolchains, inspect_engineering
from sparkle_coder.skills import select_skills
from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace


CASES = {
    "web_frontend": ("Implement a responsive web frontend", "index.html"),
    "backend_apis": ("Build a REST API", "backend/routes/items.py"),
    "mobile_apps": ("Develop a Flutter mobile app", "pubspec.yaml"),
    "desktop_apps": ("Build a Tauri desktop application", "src-tauri/tauri.conf.json"),
    "game_development": ("Develop a Godot game", "project.godot"),
    "ai_ml": ("Train a machine learning model", "training/train.py"),
    "data_engineering": ("Implement an ETL data pipeline", "dbt_project.yml"),
    "database_engineering": ("Repair PostgreSQL schema migrations", "migrations/001.sql"),
    "cloud_devops": ("Provision Kubernetes infrastructure", "Dockerfile"),
    "systems_programming": ("Build a Rust library", "Cargo.toml"),
    "embedded_iot": ("Develop ESP32 embedded firmware", "platformio.ini"),
    "cybersecurity": ("Perform an OWASP security audit", "security/policy.yml"),
    "distributed_systems": ("Debug distributed system consensus", "proto/peer.proto"),
    "automation_tools": ("Build a developer CLI tool", "action.yml"),
}


class UniversalEngineeringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Workspace(Path(self.temp.name))

    def add(self, relative, data=""):
        path = self.workspace.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def test_catalog_has_exactly_fourteen_distinct_domains_with_equal_contracts(self):
        self.assertEqual(len(DOMAIN_IDS), 14)
        self.assertEqual(len(set(DOMAIN_IDS)), 14)
        for identity, name, trigger, patterns, skills, acceptance in DOMAINS:
            with self.subTest(domain=identity):
                self.assertTrue(name)
                self.assertTrue(trigger)
                self.assertTrue(patterns)
                self.assertGreaterEqual(len(skills), 2)
                self.assertIn("Test", acceptance)
                self.assertIn(identity, CASES)

    def test_prompt_detection_covers_all_domains_and_not_only_web(self):
        for identity, (goal, _) in CASES.items():
            with self.subTest(domain=identity):
                domains = detect_domains(self.workspace, goal)
                self.assertEqual(domains[0]["id"], identity)
                self.assertEqual(domains[0]["source"], "request")
                self.assertEqual(domains[0]["signals"], ["task description"])

    def test_project_file_detection_covers_all_domains(self):
        for identity, (_, relative) in CASES.items():
            with self.subTest(domain=identity), tempfile.TemporaryDirectory() as directory:
                project = Workspace(Path(directory))
                path = project.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test")
                found = detect_domains(project)
                self.assertEqual(found[0]["id"], identity)
                self.assertEqual(found[0]["source"], "project_files")

    def test_explicit_firmware_intent_outweighs_existing_website(self):
        self.add("index.html", "<html></html>")
        self.add("platformio.ini", "[env]")
        result = detect_domains(self.workspace, "Fix ESP32 firmware and run board tests")
        self.assertEqual(result[0]["id"], "embedded_iot")
        self.assertNotIn("web_frontend", [x["id"] for x in result])

    def test_unrelated_python_or_package_files_do_not_invent_ai_web_support(self):
        self.add("package.json", '{"name": "cli"}')
        self.add("hello.py", "print('hello')")
        self.assertEqual(detect_domains(self.workspace), [])
        self.assertIsNone(inspect_engineering(self.workspace)["primary_domain"])

    def test_toolchain_scan_reports_found_missing_or_container_unchecked(self):
        files = ["Cargo.toml", "platformio.ini", "Dockerfile", "pubspec.yaml", "app.csproj"]
        with patch("sparkle_coder.engineering.shutil.which",
                   side_effect=lambda tool: "/fake/" + tool if tool in {"cargo", "flutter"} else None):
            local = detect_toolchains(files)
            docker = detect_toolchains(files, "docker")
        statuses = {item["tool"]: item["status"] for item in local}
        self.assertEqual(statuses["cargo"], "found_on_path")
        self.assertEqual(statuses["pio"], "missing_on_path")
        self.assertEqual(statuses["docker"], "missing_on_path")
        self.assertEqual(statuses["flutter"], "found_on_path")
        self.assertEqual(statuses["dotnet"], "missing_on_path")
        self.assertTrue(all(not item["verified"] for item in local))
        self.assertTrue(all(item["status"] == "container_unchecked" for item in docker))

    def test_inspection_does_not_execute_postinstall_or_claim_proof(self):
        self.add("package.json", json.dumps({"scripts": {
            "postinstall": "touch DANGEROUS", "test": "node test.js"}}))
        self.add("project.godot", "[application]")
        with patch("subprocess.Popen", side_effect=AssertionError("No code execution")), \
             patch("subprocess.run", side_effect=AssertionError("No code execution")):
            report = inspect_engineering(self.workspace)
        self.assertEqual(report["primary_domain"], "game_development")
        self.assertEqual(report["verification_contracts"][0]["status"], "not_verified_by_inspection")
        self.assertIn("not been run", report["note"])
        self.assertFalse((self.workspace.root / "DANGEROUS").exists())
        self.assertEqual(report["candidate_checks"][0]["command"], "npm run test")

    def test_skill_routing_uses_repo_evidence_without_web_bias(self):
        self.add("Cargo.toml", '[package]\nname="demo"\nversion="0.1.0"\n')
        session = Session.create(self.workspace, "Fix the failing project", [], {})
        agent = Agent(self.workspace, session, Config(auto_approve=True),
                      object(), lambda _: True, emit=lambda _: None)
        self.assertEqual(agent.engineering_domains[0]["id"], "systems_programming")
        self.assertIn("systems_programming", agent.skills)
        self.assertIn("debugging_mastery", agent.skills)
        self.assertNotIn("visual_qa", agent.skills)
        self.assertIn("ENGINEERING DOMAIN CONTRACT", agent.context()[0]["content"])
        self.assertIn('"engineering_domains"', json.dumps(agent.context()))
        self.assertEqual(select_skills("Fix a bug", domains=["systems_programming"])[-1],
                         "systems_programming")

    def test_read_only_engineering_tool_does_not_create_verification_evidence(self):
        self.add("project.godot", "[application]")
        session = Session.create(self.workspace, "Inspect my game", [], {})
        agent = Agent(self.workspace, session, Config(auto_approve=True),
                      object(), lambda _: True, emit=lambda _: None)
        result = agent.tools.execute("inspect_engineering", {})
        self.assertTrue(result["ok"])
        self.assertEqual(result["primary_domain"], "game_development")
        self.assertFalse(session.state["checks"])
        self.assertEqual(result["verification_contracts"][0]["status"], "not_verified_by_inspection")

    def test_setup_uses_same_bounded_domain_view(self):
        self.add("platformio.ini", "[env]")
        report = inspect_setup(self.workspace, Config())
        self.assertEqual(report["engineering"]["domains"][0]["id"], "embedded_iot")
        self.assertIn("toolchains", report["engineering"])
        self.assertIn("Read-only", report["engineering"]["note"])

    def test_scan_is_bounded_and_does_not_follow_protected_or_symlinked_files(self):
        self.add("src/readme.txt", "public")
        secret = self.workspace.state_dir / "outside.godot"
        secret.write_text("private")
        (self.workspace.root / "project.godot").symlink_to(secret)
        self.assertEqual(detect_domains(self.workspace), [])
        names = ["ordinary.txt"] * 2001
        report = inspect_engineering(self.workspace, files=names)
        self.assertTrue(report["scan_truncated"])


if __name__ == "__main__":
    unittest.main()
