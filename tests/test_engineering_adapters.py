"""Milestone 3: real project-aware execution adapters and permission boundaries."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.agent import Agent
from sparkle_coder.config import Config
from sparkle_coder.engineering import DOMAIN_IDS
from sparkle_coder.engineering_adapters import RECIPES, discover_adapters, resolve_adapter
from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace


FIXTURES = {
    "web_frontend": ("Build a web frontend", "package.json"),
    "backend_apis": ("Implement REST API", "go.mod"),
    "mobile_apps": ("Develop Flutter mobile app", "pubspec.yaml"),
    "desktop_apps": ("Build desktop app", "Cargo.toml"),
    "game_development": ("Develop Godot game", "project.godot"),
    "ai_ml": ("Train a machine learning model", "pyproject.toml"),
    "data_engineering": ("Implement ETL data pipeline", "dbt_project.yml"),
    "database_engineering": ("Optimize PostgreSQL migrations", "prisma/schema.prisma"),
    "cloud_devops": ("Deploy Terraform cloud infrastructure", "main.tf"),
    "systems_programming": ("Develop Rust systems library", "Cargo.toml"),
    "embedded_iot": ("Build ESP32 firmware", "platformio.ini"),
    "cybersecurity": ("Perform a security audit", "bandit.yaml"),
    "distributed_systems": ("Debug distributed consensus", "go.mod"),
    "automation_tools": ("Build a CLI automation tool", "package.json"),
}


class EngineeringAdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Workspace(Path(temporary.name))

    def put(self, relative, body="test"):
        path = self.workspace.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        return path

    def agent(self, goal, *, auto_approve=True, approve=None, ask=False):
        session = Session.create(self.workspace, goal, [], {})
        if ask:
            session.state["task_mode"] = "ask"
        agent = Agent(self.workspace, session, Config(auto_approve=auto_approve), object(),
                      approve or (lambda _: True), emit=lambda _: None)
        return agent

    def test_catalog_has_real_native_recipe_options_for_all_fourteen_domains(self):
        self.assertEqual(tuple(RECIPES), DOMAIN_IDS)
        self.assertEqual(set(FIXTURES), set(DOMAIN_IDS))
        for domain, options in RECIPES.items():
            with self.subTest(domain=domain):
                self.assertTrue(options)
                self.assertTrue(all(item.command and item.executable and item.marker for item in options))
                self.assertFalse(any("deploy " in item.command or "apply " in item.command for item in options))

    def test_manifest_matches_14_domains_without_running_any_code(self):
        for domain, (goal, manifest) in FIXTURES.items():
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as folder:
                project = Workspace(Path(folder))
                path = project.root / manifest
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"scripts": {"test": "node -e 'process.exit(0)'",
                                                          "build": "node -e 'process.exit(0)'"}})
                                if manifest == "package.json" else "fixture")
                if domain == "ai_ml":
                    (project.root / "test_model.py").write_text("def test_model(): assert True")
                report = discover_adapters(project, goal, which=lambda _: "/bin/fake")
                self.assertIn(domain, report["domains"])
                self.assertTrue(any(item["domain"] == domain for item in report["adapters"]))
                self.assertTrue(all(item["approval"] == "standard_command_runner"
                                    for item in report["adapters"]))

    def test_zero_manifest_means_no_phantom_build_or_success(self):
        report = discover_adapters(self.workspace, "Build ESP32 firmware")
        self.assertEqual(report["adapters"], [])
        self.assertEqual(report["missing_adapters"][0]["domain"], "embedded_iot")
        self.assertIn("No supported project manifest", report["missing_adapters"][0]["reason"])

    def test_package_scripts_require_actual_declared_finite_script(self):
        self.put("package.json", json.dumps({"scripts": {"test": "node --watch test.js",
                                                          "build": "vite build"}}))
        found = discover_adapters(self.workspace, "Build a web frontend", which=lambda _: "/bin/mock")
        self.assertEqual([item["command"] for item in found["adapters"]], ["npm run build"])
        self.put("package.json", "[")
        self.assertFalse(discover_adapters(self.workspace, "Build web frontend")["adapters"])

    def test_monorepo_adapter_targets_subproject_not_workspace_root(self):
        self.put("services/engine/Cargo.toml", "[package]\nname='engine'")
        found = discover_adapters(self.workspace, "Build Rust systems library",
                                  which=lambda _: "/bin/cargo")
        self.assertEqual(found["adapters"][0]["cwd"], "services/engine")
        self.assertEqual(found["adapters"][0]["command"], "cargo test")

    def test_discovery_is_read_only_even_for_malicious_project_scripts(self):
        self.put("package.json", json.dumps({"scripts": {
            "test": "node -e 'require(\"fs\").writeFileSync(\"DO_NOT_CREATE\", \"bad\")'"}}))
        agent = self.agent("Build a web frontend")
        with patch("subprocess.Popen", side_effect=AssertionError("code must not run")):
            listed = agent.tools.execute("discover_engineering_checks", {})
        self.assertTrue(listed["ok"])
        self.assertTrue(listed["adapters"])
        self.assertFalse((self.workspace.root / "DO_NOT_CREATE").exists())
        self.assertFalse(agent.session.state["checks"])

    def test_host_missing_tool_is_honest_and_cannot_be_executed(self):
        self.put("platformio.ini", "[env:test]")
        with patch("sparkle_coder.engineering_adapters.shutil.which", return_value=None):
            listing = discover_adapters(self.workspace, "Build ESP32 firmware")
            self.assertEqual(listing["adapters"][0]["availability"], "missing_on_path")
            with self.assertRaisesRegex(ValueError, "unavailable"):
                resolve_adapter(self.workspace, "Build ESP32 firmware", "local",
                                listing["adapters"][0]["id"])

    def test_docker_toolchains_are_unchecked_not_host_proven(self):
        self.put("platformio.ini", "[env:test]")
        with patch("sparkle_coder.engineering_adapters.shutil.which",
                   side_effect=AssertionError("must not trust host")):
            listing = discover_adapters(self.workspace, "Build ESP32 firmware", "docker")
        self.assertEqual(listing["adapters"][0]["availability"], "container_unchecked")

    def test_stale_adapter_id_rejected_after_project_edits(self):
        manifest = self.put("Cargo.toml", "[package]\nname='demo'")
        with patch("sparkle_coder.engineering_adapters.shutil.which", return_value="/bin/cargo"):
            first = discover_adapters(self.workspace, "Build Rust systems library")["adapters"][0]
            manifest.write_text("[package]\nname='changed'")
            with self.assertRaisesRegex(ValueError, "no longer available"):
                resolve_adapter(self.workspace, "Build Rust systems library",
                                "local", first["id"])

    def test_efficient_static_web_tasks_can_use_native_adapters(self):
        self.put("package.json", json.dumps({"scripts": {"test": "node -e 'process.exit(0)'"}}))
        agent = self.agent("Build a simple static website")
        self.assertEqual(agent.task_profile["name"], "simple_web")
        advertised = {schema["function"]["name"] for schema in agent.schemas}
        self.assertIn("discover_engineering_checks", advertised)
        self.assertIn("run_engineering_check", advertised)

    def test_ask_mode_can_discover_but_cannot_run_commands(self):
        self.put("package.json", json.dumps({"scripts": {"test": "node -e 'process.exit(0)'"}}))
        agent = self.agent("Build web frontend", ask=True)
        listing = agent.tools.execute("discover_engineering_checks", {})
        self.assertTrue(listing["ok"])
        response = agent.tools.execute("run_engineering_check",
                                       {"adapter_id": listing["adapters"][0]["id"]})
        self.assertFalse(response["ok"])
        self.assertIn("Ask mode", response["error"])
        self.assertFalse(agent.session.state["checks"])

    @unittest.skipUnless(shutil.which("npm") and shutil.which("node"), "Node.js is not available")
    def test_real_npm_adapter_executes_test_and_records_fresh_evidence(self):
        self.put("package.json", json.dumps({"scripts": {
            "test": "node -e \"require('node:assert').strictEqual(6*7, 42)\""}}))
        agent = self.agent("Build a web frontend")
        listing = agent.tools.execute("discover_engineering_checks", {})
        target = next(item for item in listing["adapters"] if item["category"] == "test")
        result = agent.tools.execute("run_engineering_check", {"adapter_id": target["id"]})
        self.assertTrue(result["ok"], result.get("error") or result.get("output"))
        self.assertEqual(result["domain"], "web_frontend")
        self.assertTrue(result["check_id"].startswith("check-"))
        self.assertEqual(agent.session.state["checks"][-1]["source"], "engineering-adapter")
        self.assertEqual(agent.session.state["checks"][-1]["exit_code"], 0)
        self.assertFalse(agent.session.state.get("engineering_evidence"))

    @unittest.skipUnless(shutil.which("npm") and shutil.which("node"), "Node.js is not available")
    def test_denied_user_approval_prevents_external_script_execution(self):
        self.put("package.json", json.dumps({"scripts": {
            "test": "node -e \"require('node:fs').writeFileSync('DO_NOT_CREATE','oops')\""}}))
        agent = self.agent("Build web frontend", auto_approve=False, approve=lambda _: False)
        adapter = agent.tools.execute("discover_engineering_checks", {})["adapters"][0]
        result = agent.tools.execute("run_engineering_check", {"adapter_id": adapter["id"]})
        self.assertFalse(result["ok"])
        self.assertTrue(result.get("denied"))
        self.assertFalse((self.workspace.root / "DO_NOT_CREATE").exists())
        self.assertFalse(agent.session.state.get("engineering_evidence"))


if __name__ == "__main__":
    unittest.main()
