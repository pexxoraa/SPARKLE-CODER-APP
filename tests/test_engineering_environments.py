"""Milestone 4: truthful environment readiness and approval-only setup."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.agent import Agent
from sparkle_coder.config import Config
from sparkle_coder.engineering_environments import (
    inspect_environment, resolve_environment_action, TOOL_PROBES, TARGET_PROBES,
)
from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = Workspace(Path(temp.name))

    def write(self, name, content="fixture"):
        target = self.workspace.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def agent(self, goal="Build frontend website", auto=True, approve=None, ask=False):
        session = Session.create(self.workspace, goal, [], {})
        if ask:
            session.state["task_mode"] = "ask"
        return Agent(self.workspace, session, Config(auto_approve=auto),
                     object(), approve or (lambda command: True),
                     emit=lambda *_: None)

    def npm_project(self):
        self.write("package.json", json.dumps({"name": "m4-test", "version": "1.0.0",
            "scripts": {"postinstall": "node -e \"require('fs').writeFileSync('UNSAFE', 'yes')\""}}))
        self.write("package-lock.json", json.dumps({"name": "m4-test", "version": "1.0.0",
            "lockfileVersion": 3, "requires": True,
            "packages": {"": {"name": "m4-test", "version": "1.0.0"}}}))

    def test_extended_go_rust_terraform_static_adapters_are_finite_checks(self):
        from sparkle_coder.engineering_adapters import discover_adapters
        examples = [
            ("go.mod", "Implement a REST API", "go vet ./..."),
            ("Cargo.toml", "Rust systems programming", "cargo fmt --all -- --check"),
            ("main.tf", "Terraform DevOps infrastructure", "terraform fmt -check -recursive"),
        ]
        for manifest, goal, command in examples:
            with self.subTest(manifest=manifest), tempfile.TemporaryDirectory() as directory:
                project = Workspace(Path(directory))
                (project.root / manifest).write_text("fixture")
                found = discover_adapters(project, goal, which=lambda tool: "/bin/fake")
                self.assertIn(command, [a["command"] for a in found["adapters"]])
                self.assertFalse(any(a["command"].startswith("terraform apply")
                                     for a in found["adapters"]))

    def test_read_only_inspection_never_runs_project_commands(self):
        self.npm_project()
        with patch("subprocess.Popen", side_effect=AssertionError("unwanted execution")):
            found = inspect_environment(self.workspace, "Build website",
                                        which=lambda _: "/bin/mock")
        self.assertTrue(found["probes"])
        self.assertEqual(found["dependency_setup"][0]["command"],
                         "npm ci --ignore-scripts --no-audit --no-fund")
        self.assertFalse((self.workspace.root / "UNSAFE").exists())

    def test_manifest_only_python_project_has_version_probe_and_virtualenv_setup(self):
        self.write("pyproject.toml", "[project]\nname = 'starter'\nversion = '0.1.0'")
        found = inspect_environment(self.workspace, "Implement a REST API")
        self.assertTrue(any(p["tool"] == "python" for p in found["probes"]))
        self.assertTrue(any("-m venv .venv" in s["command"] for s in found["dependency_setup"]))
        self.assertTrue(all(s["acceptance_evidence"] is False for s in found["dependency_setup"]))

    def test_docker_makes_no_host_path_capability_claim(self):
        self.write("Cargo.toml", "[package]\nname='demo'")
        self.write("Cargo.lock", "version = 3")
        with patch("sparkle_coder.engineering_environments.shutil.which",
                   side_effect=AssertionError("host not probed")):
            found = inspect_environment(self.workspace, "Build Rust systems programming",
                                        "docker", docker_image="sparkle-tools:local")
        self.assertEqual(found["dependency_setup"][0]["availability"], "container_unchecked")
        self.assertTrue(all(p["availability"] == "container_unchecked" for p in found["probes"]))

    def test_missing_host_tool_does_not_run_probe_or_setup(self):
        self.write("platformio.ini", "[env]")
        report = inspect_environment(self.workspace, "Build ESP32 firmware",
                                     which=lambda _: None)
        item = next(p for p in report["probes"] if p["tool"] == "pio")
        self.assertEqual(item["availability"], "missing_on_path")
        with patch("sparkle_coder.engineering_environments.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "not installed"):
                resolve_environment_action(self.workspace, "Build ESP32 firmware",
                                           "local", "", item["id"])

    def test_unknown_action_and_stale_workspace_ids_are_rejected(self):
        self.write("Cargo.toml", "[package]\nname='demo'")
        initial = inspect_environment(self.workspace, "Rust systems programming",
                                      which=lambda _: "/bin/fake")["probes"][0]
        self.write("Cargo.toml", "[package]\nname='different'")
        with self.assertRaisesRegex(ValueError, "stale"):
            resolve_environment_action(self.workspace, "Rust systems programming",
                                       "local", "", initial["id"])
        with self.assertRaisesRegex(ValueError, "stale"):
            resolve_environment_action(self.workspace, "Rust systems programming",
                                       "local", "", "setup-MALICIOUS")
        with self.assertRaisesRegex(ValueError, "Unknown"):
            resolve_environment_action(self.workspace, "Rust systems programming",
                                       "local", "", "MALICIOUS")

    def test_python_venv_symlink_is_never_selected_as_destination(self):
        self.write("pyproject.toml", "[project]\nname='safe'")
        with tempfile.TemporaryDirectory() as outside:
            (self.workspace.root / ".venv").symlink_to(outside, target_is_directory=True)
            found = inspect_environment(self.workspace, "Build a backend API")
            self.assertFalse(found["dependency_setup"])

    def test_ask_mode_inspects_but_never_runs_preparation_or_probes(self):
        self.npm_project()
        agent = self.agent(ask=True)
        listing = agent.tools.execute("inspect_engineering_environment", {})
        self.assertTrue(listing["ok"])
        for tool, key, item in (
            ("probe_engineering_environment", "probe_id", listing["probes"][0]),
            ("prepare_engineering_dependencies", "setup_id", listing["dependency_setup"][0]),
        ):
            reply = agent.tools.execute(tool, {key: item["id"]})
            self.assertFalse(reply["ok"])
            self.assertIn("Ask mode", reply["error"])
        self.assertEqual(agent.session.state["checks"], [])
        self.assertFalse(agent.session.state.get("engineering_probes"))

    def test_probe_is_observation_only_not_acceptance(self):
        self.write("Cargo.toml", "[package]\nname='demo'")
        agent = self.agent("Develop Rust systems programming")
        probe = agent.tools.inspect_engineering_environment()["probes"][0]
        with patch("sparkle_coder.engineering_environments.shutil.which", return_value="/bin/cargo"), \
             patch.object(agent.tools.runner, "run",
                          return_value={"ok": True, "exit_code": 0,
                                        "output": "cargo 1.90.0"}):
            observed = agent.tools.execute("probe_engineering_environment",
                                           {"probe_id": probe["id"]})
        self.assertTrue(observed["ok"])
        self.assertFalse(observed["target_verified"])
        self.assertFalse(agent.session.state["checks"])
        self.assertEqual(agent.session.state["engineering_probes"][0]["output_excerpt"], "cargo 1.90.0")

    def test_inspection_reports_observed_success_then_stale_after_setup_revision(self):
        self.write("Cargo.toml", "[package]\nname='demo'")
        agent = self.agent("Rust systems programming")
        listed = agent.tools.inspect_engineering_environment()
        self.assertEqual(listed["probes"][0]["probe_status"], "not_run")
        item = listed["probes"][0]
        with patch("sparkle_coder.engineering_environments.shutil.which", return_value="/bin/cargo"), \
             patch.object(agent.tools.runner, "run",
                          return_value={"ok": True, "exit_code": 0, "output": "cargo 1.9"}):
            agent.tools.execute("probe_engineering_environment", {"probe_id": item["id"]})
        observed = agent.tools.inspect_engineering_environment()
        self.assertEqual(observed["probes"][0]["probe_status"],
                         "command_passed_not_target_verified")
        agent.session.state["environment_revision"] = 1
        stale = agent.tools.inspect_engineering_environment()
        self.assertEqual(stale["probes"][0]["probe_status"], "stale")
        self.assertFalse(stale["probes"][0]["target_verified"])

    def test_probe_denial_not_misreported_as_ready(self):
        self.write("Cargo.toml", "[package]\nname='demo'")
        agent = self.agent("Rust systems programming", auto=False, approve=lambda _: False)
        probe = agent.tools.inspect_engineering_environment()["probes"][0]
        with patch("sparkle_coder.engineering_environments.shutil.which", return_value="/bin/cargo"):
            reply = agent.tools.execute("probe_engineering_environment", {"probe_id": probe["id"]})
        self.assertFalse(reply["ok"])
        self.assertTrue(reply["denied"])
        self.assertFalse(agent.session.state["engineering_probes"][0]["ok"])

    def test_dependency_setup_always_asks_even_if_auto_approve_enabled(self):
        self.npm_project()
        asked = []
        agent = self.agent(auto=True, approve=lambda command: asked.append(command) or False)
        setup = agent.tools.inspect_engineering_environment()["dependency_setup"][0]
        response = agent.tools.execute("prepare_engineering_dependencies", {"setup_id": setup["id"]})
        self.assertFalse(response["ok"])
        self.assertTrue(response["denied"])
        self.assertTrue(asked)
        self.assertEqual(agent.tools.runner.config.auto_approve, True)
        self.assertEqual(agent.session.state.get("environment_revision", 0), 0)
        self.assertFalse((self.workspace.root / "UNSAFE").exists())

    @unittest.skipUnless(shutil.which("npm"), "npm unavailable")
    def test_real_locked_npm_setup_ignores_lifecycle_hooks_and_invalidates_checks(self):
        self.npm_project()
        allowed = []
        agent = self.agent(auto=True, approve=lambda command: allowed.append(command) or True)
        setup = agent.tools.inspect_engineering_environment()["dependency_setup"][0]
        before = agent.session.state.get("environment_revision", 0)
        reply = agent.tools.execute("prepare_engineering_dependencies", {"setup_id": setup["id"]})
        self.assertTrue(reply["ok"], reply.get("error") or reply.get("output"))
        self.assertTrue(allowed)
        self.assertTrue(reply["acceptance_evidence"] is False)
        self.assertGreater(agent.session.state.get("environment_revision", 0), before)
        self.assertFalse((self.workspace.root / "UNSAFE").exists())
        self.assertFalse(agent.session.state["checks"])

    def test_invalid_matching_lockfile_means_no_setup_action(self):
        self.write("package.json", '{"name":"starter","packageManager":"pnpm@9.0.0"}')
        self.write("package-lock.json", "{}")
        found = inspect_environment(self.workspace, "Build frontend website")
        self.assertFalse(any(x["tool"] == "npm" for x in found["dependency_setup"]))

    def test_target_probes_explicitly_do_not_claim_hardware(self):
        self.write("pubspec.yaml", "name: mobile_app")
        report = inspect_environment(self.workspace, "Develop Flutter mobile app",
                                     which=lambda _: "/bin/fake")
        self.assertTrue(any(x["kind"] == "flutter_devices" for x in report["probes"]))
        self.assertTrue(all(x["target_verified"] is False for x in report["probes"]))

    def test_no_supported_setup_for_python_unhashed_pip_install(self):
        self.write("requirements.txt", "untrusted-lib>=1")
        result = inspect_environment(self.workspace, "Build backend REST API")
        self.assertFalse(any("pip install" in x["command"] for x in result["dependency_setup"]))
        self.assertTrue(all("venv" in x["command"] for x in result["dependency_setup"]))

    def test_different_execution_image_invalidates_probe_id(self):
        self.write("Cargo.toml", "[package]\nname='demo'")
        original = inspect_environment(self.workspace, "Rust systems programming",
                                       "docker", docker_image="old:version")["probes"][0]
        with self.assertRaisesRegex(ValueError, "stale"):
            resolve_environment_action(self.workspace, "Rust systems programming",
                                       "docker", "new:version", original["id"])


if __name__ == "__main__":
    unittest.main()
