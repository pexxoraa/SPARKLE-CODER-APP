"""Milestone 5: truthful device inventories and real target-integration execution.

A fake Flutter executable is used only for the subprocess plumbing regression;
no test here claims to have exercised a physical device or real Flutter SDK.
"""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.agent import Agent
from sparkle_coder.config import Config
from sparkle_coder.engineering_targets import (
    parse_inventory, discover_targets, inventory_observation, resolve_integration,
)
from sparkle_coder.engineering_contracts import _target_relevant
from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace

FLUTTER_JSON = json.dumps([
    {"id": "emulator-5554", "name": "Pixel emulator",
     "targetPlatform": "android-arm64", "isSupported": True, "emulator": True},
    {"id": "offline-device", "name": "Offline mobile",
     "targetPlatform": "android-arm64", "isSupported": False},
    {"id": "chrome", "name": "Browser",
     "targetPlatform": "web-javascript", "isSupported": True},
])
ADB_TEXT = "List of devices attached\nemulator-5554\tdevice product:sdk model:phone\nQ123\toffline\nZ999\tunauthorized\n"
IOS_JSON = json.dumps({"devices": {
    "com.apple.CoreSimulator.SimRuntime.iOS-18-0": [
        {"udid": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
         "name": "iPhone Simulator", "state": "Booted", "isAvailable": True},
        {"udid": "11111111-2222-3333-4444-555555555555",
         "name": "iPhone not booted", "state": "Shutdown", "isAvailable": True},
    ],
    "com.apple.CoreSimulator.SimRuntime.tvOS-18-0": [
        {"udid": "00000000-0000-0000-0000-000000000000",
         "name": "Apple TV", "state": "Booted", "isAvailable": True},
    ],
}})


class TargetIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Workspace(Path(self.tmp.name))

    def write(self, path, content="fixture"):
        target = self.workspace.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def flutter_project(self):
        self.write("pubspec.yaml", "name: integration_example\n")
        self.write("integration_test/login_test.dart",
                   "void main() { /* test owned by user project */ }\n")

    def agent(self, *, goal="Build a Flutter mobile app", auto=True,
              approve=None, ask=False):
        session = Session.create(self.workspace, goal, [], {})
        if ask:
            session.state["task_mode"] = "ask"
        return Agent(self.workspace, session, Config(auto_approve=auto),
                     object(), approve or (lambda _: True), emit=lambda _: None)

    def probe(self, agent, output=FLUTTER_JSON, *, ok=True):
        with patch("sparkle_coder.engineering_targets.shutil.which",
                   return_value="/bin/flutter"), \
             patch.object(agent.tools.runner, "run",
                          return_value={"ok": ok, "exit_code": 0 if ok else 1,
                                        "output": output}):
            item = agent.tools.inspect_target_integrations()["probes"][0]
            response = agent.tools.execute("probe_target_devices", {"probe_id": item["id"]})
        return response

    def test_strict_mobile_inventory_parsing_ignores_browsers_and_unsupported(self):
        items = parse_inventory("flutter", FLUTTER_JSON)
        self.assertEqual(len(items), 2)
        self.assertEqual([item["ready"] for item in items], [True, False])
        self.assertTrue(all(item["platform"] == "android" for item in items))

    def test_adb_inventory_distinguishes_ready_offline_unauthorized(self):
        items = parse_inventory("android", ADB_TEXT)
        self.assertEqual([x["status"] for x in items], ["device", "offline", "unauthorized"])
        self.assertEqual(sum(int(x["ready"]) for x in items), 1)
        with self.assertRaisesRegex(ValueError, "header"):
            parse_inventory("android", "emulator-5554\tdevice\n")

    def test_core_simulator_detects_booted_ios_but_not_shut_down_devices(self):
        items = parse_inventory("ios", IOS_JSON)
        self.assertEqual(len(items), 2)
        self.assertEqual([x["ready"] for x in items], [True, False])
        self.assertTrue(all(x["platform"] == "ios" for x in items))

    def test_invalid_json_and_malicious_shell_device_ids_never_become_targets(self):
        for payload in ("{\"devices\":1}", "not json", "[] trailing"):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_inventory("flutter", payload)
        dangerous = json.dumps([
            {"id": "$(echo compromised)", "name": "hijack",
             "targetPlatform": "android-arm64", "isSupported": True}])
        self.assertEqual(parse_inventory("flutter", dangerous), [])

    def test_platformio_serial_ports_never_count_as_verified_hardware(self):
        self.write("platformio.ini", "[env:esp32]\nplatform = espressif32")
        payload = json.dumps([
            {"port": "/dev/ttyUSB0", "description": "USB serial bridge"},
            {"port": "COM5", "description": "Windows serial port"},
            {"port": "; rm -rf /", "description": "Injected port"},
        ])
        parsed = parse_inventory("platformio", payload)
        self.assertEqual(len(parsed), 2)
        self.assertTrue(all(not item["ready"] for item in parsed))
        agent = self.agent(goal="Build ESP32 firmware")
        with patch("sparkle_coder.engineering_targets.shutil.which", return_value="/bin/pio"), \
             patch.object(agent.tools.runner, "run", return_value={
                 "ok": True, "exit_code": 0, "output": payload}):
            listing = agent.tools.inspect_target_integrations()
            self.assertEqual(listing["probes"][0]["kind"], "platformio")
            result = agent.tools.execute("probe_target_devices", {"probe_id": listing["probes"][0]["id"]})
        self.assertTrue(result["ok"])
        self.assertEqual(result["ready_count"], 0)
        self.assertFalse(result["application_tested"])
        after = agent.tools.inspect_target_integrations()
        self.assertEqual(after["probes"][0]["inventory_status"], "ports_detected_unverified")
        self.assertEqual(after["integrations"], [])
        self.assertTrue(all(not target["ready"] for target in after["targets"]))

    def test_native_godot_gut_adapter_requires_plugin_and_project_tests(self):
        from sparkle_coder.engineering_adapters import discover_adapters
        self.write("games/puzzler/project.godot", "[application]\n")
        self.write("games/puzzler/addons/gut/gut_cmdln.gd", "extends SceneTree")
        found = discover_adapters(self.workspace, "Build Godot game", which=lambda _: "/bin/godot")
        self.assertFalse(any("gut_cmdln.gd" in a["command"] for a in found["adapters"]))
        self.write("games/puzzler/test/test_rules.gd", "extends GutTest\n")
        ready = discover_adapters(self.workspace, "Build Godot game", which=lambda _: "/bin/godot")
        match = next(a for a in ready["adapters"] if "gut_cmdln.gd" in a["command"])
        self.assertEqual(match["cwd"], "games/puzzler")
        self.assertEqual(match["category"], "test")
        self.assertFalse(match["availability"] == "missing_on_path")

    def test_read_only_inventory_does_not_execute_commands(self):
        self.flutter_project()
        with patch("subprocess.Popen", side_effect=AssertionError("not allowed")):
            listing = discover_targets(self.workspace, which=lambda _: "/bin/mock")
        self.assertEqual(listing["probes"][0]["kind"], "flutter")
        self.assertEqual(listing["targets"], [])
        self.assertEqual(len(listing["integrations"]), 1)
        self.assertEqual(listing["probes"][0]["inventory_status"], "not_run")

    def test_unavailable_flutter_does_not_get_probed(self):
        self.flutter_project()
        agent = self.agent()
        with patch("sparkle_coder.engineering_targets.shutil.which", return_value=None):
            listing = agent.tools.inspect_target_integrations()
            self.assertEqual(listing["probes"][0]["availability"], "missing_on_path")
            result = agent.tools.execute("probe_target_devices",
                                         {"probe_id": listing["probes"][0]["id"]})
        self.assertFalse(result["ok"])
        self.assertIn("unavailable", result["error"])

    def test_ask_mode_allows_inventory_inspection_but_no_device_operation(self):
        self.flutter_project()
        agent = self.agent(ask=True)
        listing = agent.tools.execute("inspect_target_integrations", {})
        self.assertTrue(listing["ok"])
        self.assertEqual(agent.session.state.get("target_inventories"), None)
        denied = agent.tools.execute("probe_target_devices",
                                     {"probe_id": listing["probes"][0]["id"]})
        self.assertFalse(denied["ok"])
        self.assertIn("Ask mode", denied["error"])
        self.assertEqual(agent.session.state.get("target_inventories"), None)

    def test_device_probe_denial_even_with_auto_approval(self):
        self.flutter_project()
        asked = []
        agent = self.agent(auto=True, approve=lambda command: asked.append(command) or False)
        with patch("sparkle_coder.engineering_targets.shutil.which", return_value="/bin/flutter"):
            item = agent.tools.inspect_target_integrations()["probes"][0]
            response = agent.tools.execute("probe_target_devices", {"probe_id": item["id"]})
        self.assertFalse(response["ok"])
        self.assertTrue(response["denied"])
        self.assertEqual(len(asked), 1)
        self.assertEqual(response["ready_count"], 0)
        self.assertEqual(agent.session.state["target_inventories"][-1]["denied"], True)
        self.assertEqual(agent.tools.runner.config.auto_approve, True)

    def test_probe_success_does_not_count_as_application_test(self):
        self.flutter_project()
        agent = self.agent()
        reply = self.probe(agent)
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["ready_count"], 1)
        self.assertFalse(reply["application_tested"])
        self.assertNotIn("device_id", str(reply))
        self.assertNotIn("emulator-5554", str(reply))
        self.assertEqual(agent.session.state["checks"], [])
        found = agent.tools.inspect_target_integrations()
        self.assertEqual(found["probes"][0]["inventory_status"], "ready_devices_found")
        self.assertTrue(any(t["ready"] for t in found["targets"]))
        self.assertTrue(all("device_id" not in t for t in found["targets"]))

    def test_parse_error_is_not_treated_as_success_or_ready_target(self):
        self.flutter_project()
        agent = self.agent()
        reply = self.probe(agent, output="<html>Not a flutter response</html>")
        self.assertFalse(reply["ok"])
        self.assertTrue(reply["parse_error"])
        self.assertEqual(reply["ready_count"], 0)
        self.assertEqual(agent.tools.inspect_target_integrations()["probes"][0]["inventory_status"],
                         "invalid_output")

    def test_stale_inventory_invalidated_after_source_change_and_env_revision(self):
        self.flutter_project()
        agent = self.agent()
        self.probe(agent)
        self.assertEqual(len(agent.tools.inspect_target_integrations()["targets"]), 2)
        agent.session.state["environment_revision"] = 3
        fresh = agent.tools.inspect_target_integrations()
        self.assertEqual(fresh["probes"][0]["inventory_status"], "stale")
        self.assertEqual(fresh["targets"], [])
        agent.session.state["environment_revision"] = 0
        self.write("lib/main.dart", "// changed after inventory\n")
        changed = agent.tools.inspect_target_integrations()
        self.assertEqual(changed["targets"], [])
        self.assertEqual(changed["probes"][0]["inventory_status"], "not_run")

    def test_device_observation_expires_after_five_minutes(self):
        self.flutter_project()
        agent = self.agent()
        self.probe(agent)
        self.assertTrue(agent.tools.inspect_target_integrations()["targets"])
        agent.session.state["target_inventories"][-1]["observed_at"] -= 301
        stale = agent.tools.inspect_target_integrations()
        self.assertEqual(stale["probes"][0]["inventory_status"], "stale")
        self.assertEqual(stale["targets"], [])
        self.assertFalse(stale["probes"][0]["application_tested"])

    def test_wrong_device_token_and_no_test_suite_fail_without_runner_call(self):
        self.flutter_project()
        agent = self.agent()
        self.probe(agent)
        listing = agent.tools.inspect_target_integrations()
        integration = listing["integrations"][0]
        with patch.object(agent.tools.runner, "run",
                          side_effect=AssertionError("must not call runner")):
            for token in ("device-unknown", "device-$(evil)", ""):
                with self.subTest(token=token):
                    response = agent.tools.execute("run_target_integration", {
                        "integration_id": integration["id"], "target_id": token})
                    self.assertFalse(response["ok"])
        self.write("integration_test/login_test.dart", "// still a test but changed")
        response = agent.tools.execute("run_target_integration", {
            "integration_id": integration["id"], "target_id": listing["targets"][0]["id"]})
        self.assertFalse(response["ok"])
        self.assertIn("changed", response["error"])

    def test_mocked_flutter_integration_records_fresh_real_check_id(self):
        self.flutter_project()
        approvals = []
        agent = self.agent(approve=lambda command: approvals.append(command) or True)
        self.probe(agent)
        listing = agent.tools.inspect_target_integrations()
        with patch.object(agent.tools.runner, "run", return_value={
            "ok": True, "exit_code": 0, "output": "Integration suite: all tests passed"}):
            result = agent.tools.execute("run_target_integration", {
                "integration_id": listing["integrations"][0]["id"],
                "target_id": next(t["id"] for t in listing["targets"] if t["ready"])})
        self.assertTrue(result["ok"], result.get("error"))
        self.assertTrue(result["target_application_test_passed"])
        self.assertEqual(result["test_type"], "application_integration_test")
        self.assertTrue(result["check_id"].startswith("check-"))
        self.assertEqual(agent.session.state["checks"][-1]["source"], "target-integration")
        self.assertIn("integration_test", agent.session.state["checks"][-1]["command"])
        self.assertFalse(agent.session.state.get("engineering_evidence"))
        self.assertEqual(agent.tools.runner.config.auto_approve, True)
        self.assertTrue(_target_relevant("mobile_apps", agent.session.state["checks"][-1]))

    def test_target_contract_rejects_device_enumeration_as_acceptance(self):
        for command in ("flutter devices --machine", "flutter --version",
                        "adb devices -l", "xcrun simctl list devices --json"):
            self.assertFalse(_target_relevant("mobile_apps", {
                "command": command, "source": "agent", "required": False}))
        self.assertTrue(_target_relevant("mobile_apps", {
            "command": "flutter test integration_test -d emulator-5554",
            "source": "target-integration", "required": False}))

    def test_android_connected_tests_require_single_ready_device(self):
        self.write("android/settings.gradle", "rootProject.name='app'")
        self.write("android/app/src/androidTest/java/AppTest.java", "class AppTest {}")
        agent = self.agent(goal="Build Android mobile app")
        with patch("sparkle_coder.engineering_targets.shutil.which", return_value="/bin/adb"), \
             patch.object(agent.tools.runner, "run", return_value={
                 "ok": True, "exit_code": 0, "output": ADB_TEXT}):
            candidate = next(i for i in agent.tools.inspect_target_integrations()["probes"]
                             if i["kind"] == "android")
            response = agent.tools.execute("probe_target_devices", {"probe_id": candidate["id"]})
        self.assertTrue(response["ok"])
        listing = agent.tools.inspect_target_integrations()
        self.assertEqual(len(listing["integrations"]), 1)
        target = next(t for t in listing["targets"] if t["ready"])
        command = resolve_integration(self.workspace, "local",
                                      agent.tools.runner.config.docker_image,
                                      agent.session.state, listing["integrations"][0]["id"],
                                      target["id"])
        self.assertEqual(command["command"], "gradle connectedAndroidTest")
        self.write("android/gradlew", "#!/bin/sh")
        self.write("android/gradlew.bat", "@echo off")
        # Adding wrappers changes the project fingerprint. Enumerate devices
        # again rather than reusing acceptance from the previous source state.
        with patch("sparkle_coder.engineering_targets.shutil.which", return_value="/bin/adb"), \
             patch.object(agent.tools.runner, "run", return_value={
                 "ok": True, "exit_code": 0, "output": ADB_TEXT}):
            newest = next(p for p in agent.tools.inspect_target_integrations()["probes"]
                          if p["kind"] == "android")
            self.assertTrue(agent.tools.execute("probe_target_devices",
                                                 {"probe_id": newest["id"]})["ok"])
        listing = agent.tools.inspect_target_integrations()
        target = next(t for t in listing["targets"] if t["ready"])
        with patch("sparkle_coder.engineering_targets.HOST_OS", "nt"):
            windows = resolve_integration(self.workspace, "local",
                                          agent.tools.runner.config.docker_image,
                                          agent.session.state, listing["integrations"][0]["id"],
                                          target["id"])
            self.assertEqual(windows["command"], "gradlew.bat connectedAndroidTest")
        with patch("sparkle_coder.engineering_targets.HOST_OS", "posix"):
            unix = resolve_integration(self.workspace, "local",
                                       agent.tools.runner.config.docker_image,
                                       agent.session.state, listing["integrations"][0]["id"],
                                       target["id"])
            self.assertEqual(unix["command"], "./gradlew connectedAndroidTest")
        # A second ready device makes broad connectedAndroidTest unsafe.
        obs = agent.session.state["target_inventories"][-1]
        second = dict(obs["devices"][0], token="device-second", device_id="device123")
        obs["devices"].append(second)
        obs["ready_count"] += 1
        with self.assertRaisesRegex(ValueError, "exactly one"):
            resolve_integration(self.workspace, "local",
                                agent.tools.runner.config.docker_image,
                                agent.session.state, listing["integrations"][0]["id"],
                                target["id"])

    def test_android_connected_deduplicates_same_target_from_flutter_and_adb(self):
        self.flutter_project()
        self.write("settings.gradle", "rootProject.name = 'example'")
        self.write("android/app/src/main/AndroidManifest.xml", "<manifest />")
        self.write("android/app/src/androidTest/java/AppTest.java", "class AppTest {}")
        agent = self.agent()
        with patch("sparkle_coder.engineering_targets.shutil.which", return_value="/bin/fake"):
            listing = agent.tools.inspect_target_integrations()
            kinds = {probe["kind"] for probe in listing["probes"]}
            self.assertIn("flutter", kinds)
            self.assertIn("android", kinds)
            for probe in listing["probes"]:
                output = FLUTTER_JSON if probe["kind"] == "flutter" else ADB_TEXT
                with patch.object(agent.tools.runner, "run", return_value={
                    "ok": True, "exit_code": 0, "output": output}):
                    result = agent.tools.execute("probe_target_devices",
                                                  {"probe_id": probe["id"]})
                self.assertTrue(result["ok"])
        ready = agent.tools.inspect_target_integrations()
        self.assertGreaterEqual(len([x for x in ready["targets"] if x["ready"]]), 2)
        option = next(x for x in ready["integrations"] if x["kind"] == "android_connected")
        token = next(x["id"] for x in ready["targets"]
                     if x["ready"] and x["platform"] == "android")
        chosen = resolve_integration(self.workspace, "local",
                                     agent.tools.runner.config.docker_image,
                                     agent.session.state, option["id"], token)
        self.assertEqual(chosen["command"], "gradle connectedAndroidTest")

    @unittest.skipIf(os.name == "nt", "POSIX executable shim for subprocess wiring")
    def test_actual_subprocess_path_with_simulated_flutter_binary(self):
        self.flutter_project()
        with tempfile.TemporaryDirectory() as folder:
            program = Path(folder) / "flutter"
            program.write_text("#!/bin/sh\n"
                               "if [ \"$1\" = \"devices\" ]; then\n"
                               "  printf '%s\\n' '" + FLUTTER_JSON + "'\n"
                               "elif [ \"$1\" = \"test\" ] && [ \"$2\" = \"integration_test\" ] "
                               "&& [ \"$3\" = \"-d\" ]; then\n"
                               "  echo 'simulated Flutter CLI integration passed'\n"
                               "else exit 12; fi\n")
            program.chmod(program.stat().st_mode | stat.S_IXUSR)
            approvals = []
            agent = self.agent(approve=lambda command: approvals.append(command) or True)
            with patch.dict(os.environ, {"PATH": folder + os.pathsep + os.environ.get("PATH", "")}):
                listing = agent.tools.inspect_target_integrations()
                self.assertEqual(listing["probes"][0]["availability"], "found_on_path")
                probed = agent.tools.execute("probe_target_devices", {
                    "probe_id": listing["probes"][0]["id"]})
                self.assertTrue(probed["ok"], probed.get("error"))
                second = agent.tools.inspect_target_integrations()
                target = next(t for t in second["targets"] if t["ready"])
                result = agent.tools.execute("run_target_integration", {
                    "integration_id": second["integrations"][0]["id"], "target_id": target["id"]})
            self.assertTrue(result["ok"], result.get("error") or result.get("output"))
            self.assertEqual(len(approvals), 2)
            self.assertEqual(len(agent.session.state["checks"]), 1)
            self.assertIn("simulated Flutter CLI", result["output"])
            self.assertFalse((self.workspace.root / "UNEXPECTED").exists())


if __name__ == "__main__":
    unittest.main()
