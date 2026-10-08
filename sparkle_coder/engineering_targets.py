"""Read-only target discovery and explicitly approved, observed device integration.

Target inventories come from *executed* tools, not names in a manifest. A
connected device or booted simulator does not prove application correctness.
Only a runnable project-owned integration suite can claim integration evidence.
No emulator boot, APK installation, device flashing or cloud deployment happens
during discovery.
"""
import hashlib
import json
from pathlib import PurePosixPath
import re
import shutil

from .python_runtime import shell_command

IDENTITY = re.compile(r"^[a-zA-Z0-9._:-]{1,128}$")
INVENTORY_COMMANDS = {
    "flutter": ("flutter devices --machine", "Flutter mobile device enumeration"),
    "android": ("adb devices -l", "Android Debug Bridge connected device enumeration"),
    "ios": ("xcrun simctl list devices --json", "Apple Simulator iOS device enumeration"),
    "platformio": ("pio device list --json-output",
                   "Enumerate serial ports only; this does not identify or validate firmware hardware"),
}
TOOLS = {"flutter": "flutter", "android": "adb", "ios": "xcrun", "platformio": "pio"}
DOMAIN = "mobile_apps"
VERSION = 1


def _opaque(prefix, *args):
    return prefix + hashlib.sha256("\0".join(map(str, args)).encode()).hexdigest()[:20]


def _clean(value, limit=100):
    return " ".join(str(value or "").split())[:limit]


def _valid_id(value):
    return isinstance(value, str) and bool(IDENTITY.fullmatch(value))


def parse_inventory(kind, output):
    """Strict, bounded parsing; malformed data must never become 'ready'."""
    if not isinstance(output, str) or len(output) > 48000:
        raise ValueError("Device enumeration output is missing or too large.")
    found = []
    if kind == "flutter":
        try:
            items = json.loads(output)
        except (ValueError, TypeError) as exc:
            raise ValueError("Flutter did not return valid machine-readable JSON.") from exc
        if not isinstance(items, list):
            raise ValueError("Flutter inventory must be a JSON array.")
        for item in items[:50]:
            if not isinstance(item, dict) or not _valid_id(item.get("id")):
                continue
            platform = str(item.get("targetPlatform", "")).lower()
            if "android" not in platform and "ios" not in platform:
                continue
            ready = item.get("isSupported") is True
            found.append({"device_id": item["id"], "name": _clean(item.get("name", "Mobile device")),
                          "platform": "ios" if "ios" in platform else "android",
                          "kind": "emulator" if item.get("emulator") is True else "device",
                          "status": "connected" if ready else "unsupported", "ready": ready})
    elif kind == "android":
        lines = output.replace("\r\n", "\n").splitlines()
        if not lines or lines[0].strip() != "List of devices attached":
            raise ValueError("ADB inventory is missing its expected header.")
        for line in lines[1:51]:
            columns = line.split()
            if len(columns) < 2 or not _valid_id(columns[0]):
                continue
            status = columns[1]
            if status not in ("device", "offline", "unauthorized", "recovery", "sideload"):
                continue
            identifier = columns[0]
            found.append({"device_id": identifier, "name": "Android " + (
                          "emulator" if identifier.startswith("emulator-") else "device"),
                          "platform": "android", "kind": "emulator" if identifier.startswith("emulator-")
                          else "device", "status": status, "ready": status == "device"})
    elif kind == "platformio":
        try:
            items = json.loads(output)
        except (ValueError, TypeError) as exc:
            raise ValueError("PlatformIO did not return valid JSON serial ports.") from exc
        if not isinstance(items, list):
            raise ValueError("PlatformIO ports must be a JSON array.")
        for item in items[:50]:
            if not isinstance(item, dict):
                continue
            port = item.get("port")
            if not isinstance(port, str) or not re.fullmatch(
                    r"(?:/dev/[a-zA-Z0-9._-]{1,100}|COM[0-9]{1,3})", port):
                continue
            found.append({"device_id": port, "name": _clean(item.get("description") or
                          "Unidentified serial port"), "platform": "embedded",
                          "kind": "serial_port", "status": "port_detected_unverified",
                          "ready": False})
    elif kind == "ios":
        try:
            data = json.loads(output)
        except (ValueError, TypeError) as exc:
            raise ValueError("simctl did not return valid JSON.") from exc
        versions = data.get("devices") if isinstance(data, dict) else None
        if not isinstance(versions, dict):
            raise ValueError("simctl inventory has no devices map.")
        for version, items in list(versions.items())[:30]:
            if "ios" not in str(version).lower() or not isinstance(items, list):
                continue
            for item in items[:30]:
                if not isinstance(item, dict) or not _valid_id(item.get("udid")):
                    continue
                booted = item.get("state") == "Booted" and item.get("isAvailable") is not False
                found.append({"device_id": item["udid"], "name": _clean(item.get("name", "iOS Simulator")),
                              "platform": "ios", "kind": "simulator",
                              "status": _clean(item.get("state", "Unknown"), 30),
                              "ready": booted})
    else:
        raise ValueError("Unsupported target inventory kind.")
    seen, result = set(), []
    for item in found:
        if item["device_id"] not in seen:
            seen.add(item["device_id"])
            result.append(item)
    return result[:40]


def _roots(files):
    """Use only bounded, relevant project manifests and never infer from a prompt."""
    result = {}
    for name in files[:2000]:
        path = PurePosixPath(name)
        if len(path.parts) > 8:
            continue
        if path.name == "platformio.ini" and len(path.parts) <= 5:
            result.setdefault(str(path.parent), set()).add("platformio")
        if path.name == "pubspec.yaml" and len(path.parts) <= 5:
            result.setdefault(str(path.parent), set()).add("flutter")
        if path.name == "AndroidManifest.xml" and "android" in path.parts:
            # Android Flutter modules usually contain app/src/main/AndroidManifest;
            # keep a project root at the directory just above android/.
            at = path.parts.index("android")
            result.setdefault(str(PurePosixPath(*path.parts[:at])) if at else ".", set()).add("android")
        if path.name in ("settings.gradle", "settings.gradle.kts"):
            result.setdefault(str(path.parent), set()).add("android")
        if path.name == "project.pbxproj" and path.parent.name.endswith(".xcodeproj"):
            xcode = path.parent.parent
            if xcode.name == "ios":
                xcode = xcode.parent
            result.setdefault(str(xcode), set()).add("ios")
    return result


def discover_targets(workspace, execution="local", *, docker_image="", files=None,
                     state=None, which=None):
    """Read-only target candidates and last fresh observed inventory, if any."""
    files = (workspace.files(limit=2001) if files is None else files)[:2000]
    which = which or shutil.which
    fingerprint = workspace.fingerprint()
    revision = state.get("environment_revision", 0) if isinstance(state, dict) else 0
    records = state.get("target_inventories", []) if isinstance(state, dict) else []
    if not isinstance(records, list):
        records = []
    latest = {o.get("id"): o for o in records[-20:]
              if isinstance(o, dict) and isinstance(o.get("id"), str)}
    probes, targets, integrations = [], [], []
    for root, kinds in sorted(_roots(files).items()):
        # The same Flutter module can have a native Android and iOS target.
        for kind in sorted(kinds):
            cmd, description = INVENTORY_COMMANDS[kind]
            identity = _opaque("target-", fingerprint, execution, docker_image, root, cmd)
            availability = ("container_unchecked" if execution == "docker" else
                            "found_on_path" if which(TOOLS[kind]) else "missing_on_path")
            previous = latest.get(identity)
            fresh = (previous is not None and previous.get("fingerprint") == fingerprint and
                     previous.get("environment_revision", 0) == revision and
                     previous.get("execution") == execution and
                     previous.get("docker_image") == docker_image)
            entry = {"id": identity, "kind": kind, "cwd": root, "command": cmd,
                     "description": description, "availability": availability,
                     "inventory_status": (
                         "not_run" if previous is None else "stale" if not fresh else
                         "permission_denied" if previous.get("denied") else
                         "command_failed" if not previous.get("command_ok") else
                         "invalid_output" if previous.get("parse_error") else
                         "ready_devices_found" if previous.get("ready_count", 0) else
                         "ports_detected_unverified" if kind == "platformio" and
                         previous.get("devices") else "no_ready_devices"),
                     "ready_count": previous.get("ready_count", 0) if fresh else 0,
                     "application_tested": False}
            probes.append(entry)
            if fresh and previous.get("command_ok") and not previous.get("parse_error"):
                for device in previous.get("devices", [])[:40]:
                    if not isinstance(device, dict):
                        continue
                    # Do not expose serial numbers in inspection; only an opaque
                    # identifier is supplied to subsequently approved test tools.
                    targets.append({"id": device["token"], "probe_id": identity, "cwd": root,
                                    "platform": device["platform"], "kind": device["kind"],
                                    "name": device["name"], "status": device["status"],
                                    "ready": bool(device["ready"]), "application_tested": False})

        prefix = "" if root == "." else root + "/"
        if "flutter" in kinds and any(path.startswith(prefix + "integration_test/")
                                      and path.endswith("_test.dart") for path in files):
            integrations.append({"id": _opaque("integration-", fingerprint, execution, docker_image,
                                               root, "flutter_integration"),
                                 "kind": "flutter_integration", "cwd": root,
                                 "description": "Run real Flutter integration_test suite on one selected connected mobile target",
                                 "requires_device": True, "requires_user_approval": True,
                                 "build_and_app_test": True})
        if "android" in kinds and any(path.startswith(prefix + "app/src/androidTest/")
                                       or path.startswith(prefix + "android/app/src/androidTest/")
                                       for path in files):
            integrations.append({"id": _opaque("integration-", fingerprint, execution, docker_image,
                                               root, "android_connected"),
                                 "kind": "android_connected", "cwd": root,
                                 "description": "Run connected Android instrumented tests (requires exactly one ready device)",
                                 "requires_device": True, "requires_user_approval": True,
                                 "build_and_app_test": True})
    return {"version": VERSION, "execution": execution,
            "probes": probes[:20], "targets": targets[:60], "integrations": integrations[:16],
            "scan_truncated": len(files) >= 2000,
            "note": ("Inventory inspection is read-only. Serial ports are not proven boards. "
                     "A connected device is not an "
                     "application test. Device enumeration and integration runs require "
                     "explicit command approval, even in automatic mode. No simulator "
                     "is booted, hardware is flashed, or cloud service is provisioned.")}


def get_probe(workspace, execution, docker_image, probe_id, *, which=None):
    if not isinstance(probe_id, str) or not probe_id.startswith("target-"):
        raise ValueError("Invalid target inventory ID.")
    listing = discover_targets(workspace, execution, docker_image=docker_image, which=which)
    item = next((p for p in listing["probes"] if p["id"] == probe_id), None)
    if item is None:
        raise ValueError("Target inventory is stale or not associated with this project.")
    if item["availability"] == "missing_on_path":
        raise ValueError("Target toolchain is unavailable on host PATH; no device was queried.")
    return item


def inventory_observation(probe, run, fingerprint, revision, execution, image):
    """Derive structured evidence; no raw tool output is retained."""
    parse_error, parsed = None, []
    if run.get("ok"):
        try:
            parsed = parse_inventory(probe["kind"], run.get("output", ""))
        except (ValueError, KeyError, TypeError) as exc:
            parse_error = str(exc)[:180]
    public = []
    for item in parsed:
        item = dict(item)
        item["token"] = _opaque("device-", probe["id"], item["device_id"])
        public.append(item)
    return {"id": probe["id"], "fingerprint": fingerprint,
            "environment_revision": revision, "execution": execution,
            "docker_image": image, "command_ok": bool(run.get("ok")),
            "denied": bool(run.get("denied")), "parse_error": parse_error,
            "devices": public[:40], "ready_count": sum(int(d["ready"]) for d in public)}


def resolve_integration(workspace, execution, docker_image, state, integration_id, token):
    listing = discover_targets(workspace, execution, docker_image=docker_image, state=state)
    if not isinstance(integration_id, str) or not integration_id.startswith("integration-"):
        raise ValueError("Invalid integration ID.")
    option = next((i for i in listing["integrations"] if i["id"] == integration_id), None)
    if option is None:
        raise ValueError("Integration is missing or project files changed.")
    if not isinstance(token, str) or not token.startswith("device-"):
        raise ValueError("Invalid device selection.")
    target = next((t for t in listing["targets"] if t["id"] == token and t["ready"]
                   and t["cwd"] == option["cwd"]), None)
    if target is None:
        raise ValueError("Device is not freshly verified as connected/booted. Probe again.")
    records = state.get("target_inventories", [])
    if not isinstance(records, list):
        raise ValueError("Saved device inventory is unavailable.")
    matching = next((obs for obs in reversed(records[-20:])
                     if isinstance(obs, dict) and obs.get("id") == target["probe_id"]), None)
    if not isinstance(matching, dict):
        raise ValueError("Saved device inventory is unavailable.")
    device = next((d for d in matching.get("devices", []) if d["token"] == token), None)
    if not device or not _valid_id(device.get("device_id")):
        raise ValueError("Device identity is no longer available.")
    identity = device["device_id"]
    if option["kind"] == "flutter_integration":
        if target["platform"] not in ("android", "ios"):
            raise ValueError("Only Android and iOS Flutter integration targets are supported.")
        argv = ["flutter", "test", "integration_test", "-d", identity]
        return {**option, "target_token": token, "command": shell_command(argv, docker=execution=="docker"),
                "target": target, "target_behavior": "application_integration_test"}
    if option["kind"] == "android_connected":
        if target["platform"] != "android" or not any(
                t["ready"] and t["platform"] == "android" and t["cwd"] == option["cwd"]
                for t in listing["targets"]):
            raise ValueError("No freshly observed Android target.")
        # Gradle connectedAndroidTest would execute on ALL connected devices,
        # including newly attached ones. Require exactly one ready device and
        # request explicit approval again for the actual test invocation.
        if sum(1 for t in listing["targets"] if t["ready"] and t["platform"] == "android"
               and t["cwd"] == option["cwd"]) != 1:
            raise ValueError("Android instrumentation requires exactly one ready connected device.")
        command = ("./gradlew connectedAndroidTest" if
                   (workspace.root / option["cwd"] / "gradlew").is_file() else
                   "gradle connectedAndroidTest")
        return {**option, "target_token": token, "command": command,
                "target": target, "target_behavior": "connected_android_instrumentation"}
    raise ValueError("Unknown integration target type.")
