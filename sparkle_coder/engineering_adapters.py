"""Project-aware, opt-in engineering verification adapters.

Catalog is read-only. Executing an advertised check goes through the regular
command runner and records actual check IDs. No project code, package scripts,
hardware, remote deployment or simulator starts during discovery.
"""
from dataclasses import dataclass
from fnmatch import fnmatch
import hashlib
import json
import re
import shutil
from pathlib import PurePosixPath

from .checks import package_manager
from .engineering import DOMAIN_IDS, detect_domains
from .python_runtime import python_argv, shell_command


@dataclass(frozen=True)
class Recipe:
    marker: str
    executable: str
    command: str
    category: str
    description: str
    script: str = ""


# Every domain has at least one native project integration. Recipes are
# conservative, finite checks; a missing recipe is NOT a passed target.
RECIPES = {
    "web_frontend": (
        Recipe("package.json", "npm", "npm run test", "test", "Project frontend tests", "test"),
        Recipe("package.json", "npm", "npm run build", "build", "Frontend production compilation", "build")),
    "backend_apis": (
        Recipe("go.mod", "go", "go test ./...", "test", "Go API tests"),
        Recipe("go.mod", "go", "go vet ./...", "static", "Go API static analysis"),
        Recipe("package.json", "npm", "npm run test", "test", "API package tests", "test"),
        Recipe("pyproject.toml", "python", "python -m pytest", "test", "Python API tests")),
    "mobile_apps": (
        Recipe("pubspec.yaml", "flutter", "flutter analyze", "static", "Flutter project analyzer"),
        Recipe("pubspec.yaml", "flutter", "flutter test", "test", "Flutter widget and app tests"),
        Recipe("build.gradle", "gradle", "gradle test", "test", "Android/JVM tests"),
        Recipe("build.gradle.kts", "gradle", "gradle test", "test", "Android/Kotlin tests")),
    "desktop_apps": (
        Recipe("Cargo.toml", "cargo", "cargo test", "test", "Desktop Rust tests"),
        Recipe("package.json", "npm", "npm run test", "test", "Electron or Tauri UI tests", "test")),
    "game_development": (
        Recipe("project.godot", "godot", "godot --headless --editor --path . --quit", "smoke",
               "Godot resource import and editor startup (not gameplay verification)"),
        Recipe("addons/gut/gut_cmdln.gd", "godot",
               "godot --headless --path . -s res://addons/gut/gut_cmdln.gd -gexit",
               "test", "Run real Godot GUT project-owned game tests")),
    "ai_ml": (
        Recipe("pyproject.toml", "python", "python -m pytest", "test", "ML project evaluation tests"),),
    "data_engineering": (
        Recipe("dbt_project.yml", "dbt", "dbt parse", "static", "dbt project and model parsing"),),
    "database_engineering": (
        Recipe("prisma/schema.prisma", "prisma", "prisma validate", "static", "Prisma database schema validation"),
        Recipe("alembic.ini", "python", "python -m pytest", "test", "Database migration and behavior tests")),
    "cloud_devops": (
        Recipe("main.tf", "terraform", "terraform validate -no-color", "static", "Terraform configuration validation"),
        Recipe("main.tf", "terraform", "terraform fmt -check -recursive", "static", "Terraform formatting without writes"),
        Recipe("compose.yaml", "docker", "docker compose config -q", "static", "Compose configuration validation"),
        Recipe("docker-compose.yml", "docker", "docker compose config -q", "static", "Compose configuration validation")),
    "systems_programming": (
        Recipe("Cargo.toml", "cargo", "cargo test", "test", "Rust target and unit tests"),
        Recipe("Cargo.toml", "cargo", "cargo fmt --all -- --check", "static", "Rust formatting verification (requires rustfmt)"),
        Recipe("CMakeLists.txt", "cmake", "cmake -S . -B build", "build", "CMake configuration and compiler detection")),
    "embedded_iot": (
        Recipe("platformio.ini", "pio", "pio run", "build", "PlatformIO target firmware build"),),
    "cybersecurity": (
        Recipe(".semgrep.yml", "semgrep", "semgrep scan --metrics=off --config .semgrep.yml .", "static",
               "Local Semgrep rule scan"),
        Recipe("bandit.yaml", "bandit", "bandit -r . -c bandit.yaml", "static", "Bandit Python security scan")),
    "distributed_systems": (
        Recipe("go.mod", "go", "go test ./...", "test", "Distributed Go component tests"),
        Recipe("go.mod", "go", "go vet ./...", "static", "Distributed Go static analysis"),
        Recipe("Cargo.toml", "cargo", "cargo test", "test", "Distributed Rust component tests")),
    "automation_tools": (
        Recipe("package.json", "npm", "npm run test", "test", "Automation or CLI package tests", "test"),
        Recipe("pyproject.toml", "python", "python -m pytest", "test", "Automation or CLI Python tests")),
}
assert tuple(RECIPES) == DOMAIN_IDS


def _manifest_roots(files, marker):
    # Explicit file matches only, never basenames from outside workspace.
    matches = []
    for path in files:
        item = PurePosixPath(path)
        if len(item.parts) > 4:
            continue
        if "/" in marker:
            suffix = PurePosixPath(marker).parts
            if len(item.parts) >= len(suffix) and item.parts[-len(suffix):] == suffix:
                root = PurePosixPath(*item.parts[:-len(suffix)])
            else:
                continue
        elif item.name == marker:
            root = item.parent
        else:
            continue
        cwd = str(root)
        if cwd not in matches:
            matches.append(cwd)
    return matches[:12]


def _has_tests(files, cwd, kind):
    prefix = "" if cwd == "." else cwd + "/"
    rest = [path[len(prefix):] for path in files if path.startswith(prefix)]
    # A Python or Flutter test invocation must actually have tests to collect.
    if kind == "flutter":
        return any(p.startswith("test/") and p.endswith("_test.dart") for p in rest)
    return any((p.startswith("test_") or p.startswith("tests/") or p.endswith("_test.py"))
               and p.endswith(".py") for p in rest)


def _read_package(workspace, cwd):
    path = "package.json" if cwd == "." else cwd + "/package.json"
    try:
        data = json.loads(workspace.read(path)[0])
    except (OSError, ValueError, UnicodeError):
        return {}
    return data if isinstance(data, dict) else {}


def discover_adapters(workspace, goal="", execution="local", *, files=None, which=None):
    files = workspace.files(limit=2001) if files is None else files
    files = files[:2000]
    names = set(files)
    which = which or shutil.which
    domains = detect_domains(workspace, goal, files=files)
    fingerprint = workspace.fingerprint()
    entries, missing = [], []
    for domain in domains:
        identity = domain["id"]
        found = False
        for recipe in RECIPES[identity]:
            for cwd in _manifest_roots(files, recipe.marker):
                prefix = "" if cwd == "." else cwd + "/"
                command, tool = recipe.command, recipe.executable
                if recipe.script:
                    data = _read_package(workspace, cwd)
                    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
                    body = scripts.get(recipe.script)
                    if not isinstance(body, str) or not body.strip() or re.search(
                            r"(?i)(?:\bwatch\b|--watch\b|\bserve\b|\bdev\b|no test specified)", body):
                        continue
                    manager = package_manager(data, names, cwd)
                    command = manager + " run " + recipe.script
                    tool = manager
                if recipe.executable == "python":
                    if not _has_tests(files, cwd, "python"):
                        continue
                    if execution == "docker":
                        command, tool = "python3 -m pytest", "python3"
                    else:
                        interpreter = python_argv(workspace.root / cwd)
                        command = (shell_command([*interpreter, "-m", "pytest"])
                                   if interpreter else "python3 -m pytest")
                        tool = "python"
                if recipe.executable == "flutter" and recipe.command == "flutter test" and not _has_tests(files, cwd, "flutter"):
                    continue
                if recipe.marker == "addons/gut/gut_cmdln.gd":
                    # GUT runner without any user-owned GDScript tests would
                    # only prove the plugin launched, not a game test passed.
                    prefix = "" if cwd == "." else cwd + "/"
                    if (prefix + "project.godot" not in names or not any(
                            path.startswith(prefix) and
                            PurePosixPath(path).name.startswith("test_") and
                            path.endswith(".gd") for path in files)):
                        continue
                if recipe.marker == "main.tf" and not any(name.endswith(".tf") for name in names):
                    continue
                # Do not execute anything or claim availability inside Docker.
                available = ("container_unchecked" if execution == "docker" else
                             "found_on_path" if (
                                 (python_argv(workspace.root / cwd) if tool == "python" else which(tool))
                             ) else "missing_on_path")
                serial = "\0".join((fingerprint or "", identity, cwd, command, recipe.category))
                check_id = hashlib.sha256(serial.encode()).hexdigest()[:20]
                entries.append({"id": "adapter-" + check_id, "domain": identity,
                                "category": recipe.category, "description": recipe.description,
                                "cwd": cwd, "command": command, "tool": tool,
                                "availability": available, "source": prefix + recipe.marker,
                                "executes_project_code": True,
                                "approval": "standard_command_runner"})
                found = True
        if not found:
            missing.append({"domain": identity,
                            "reason": "No supported project manifest and finite check found. "
                                      "Use real project-owned tests or configure a toolchain; no result was assumed."})
    # Duplicate recipes from overlapping manifest candidates are harmless to
    # security but distract the agent and waste context.
    deduped = list({item["id"]: item for item in entries}.values())
    return {"version": 1, "domains": [entry["id"] for entry in domains],
            "adapters": deduped[:32], "missing_adapters": missing,
            "scan_truncated": len(files) >= 2000,
            "note": ("Listing is read-only. Running an adapter uses normal user command "
                     "approval and verification. Native hardware/emulators, service "
                     "credentials and remote deployment are not provisioned.")}


def resolve_adapter(workspace, goal, execution, adapter_id):
    if not isinstance(adapter_id, str) or not adapter_id.startswith("adapter-"):
        raise ValueError("Unknown engineering adapter ID.")
    listing = discover_adapters(workspace, goal, execution)
    adapter = next((item for item in listing["adapters"] if item["id"] == adapter_id), None)
    if not adapter:
        raise ValueError("Adapter is no longer available for these project files. Rediscover checks.")
    if adapter["availability"] == "missing_on_path":
        raise ValueError("Required local tool '" + adapter["tool"] +
                         "' is unavailable. Install and configure it, or choose a supported environment.")
    return adapter
