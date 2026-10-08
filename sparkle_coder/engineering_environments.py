"""Read-only engineering environment discovery and opt-in, finite setup recipes.

Tool probes and setup actions are NEVER executed during inspection. Execution
goes through CommandRunner's existing approval, timeout, stop and isolation
policies. Probe success is *not* proof that a target device exists or a project
has built. Dependency setup is not a substitute for a passing acceptance test.
"""
import hashlib
import shutil
from pathlib import PurePosixPath

from .engineering_adapters import discover_adapters
from .python_runtime import python_argv, shell_command


# Limited to finite non-destructive version/target-list probes. Do not add
# daemon-launching, flashing, deployment, authentication or code-generation
# commands to this table.
TOOL_PROBES = {
    "npm": "npm --version",
    "pnpm": "pnpm --version",
    "yarn": "yarn --version",
    "bun": "bun --version",
    "cargo": "cargo --version",
    "go": "go version",
    "flutter": "flutter --version",
    "gradle": "gradle --version",
    "godot": "godot --headless --version",
    "dbt": "dbt --version",
    "prisma": "prisma --version",
    "terraform": "terraform version",
    "docker": "docker --version",
    "cmake": "cmake --version",
    "pio": "pio --version",
    "semgrep": "semgrep --version",
    "bandit": "bandit --version",
    "python": None,  # Resolve project interpreter without launching a frozen GUI.
    "python3": "python3 --version",
}
TARGET_PROBES = {
    "flutter": (("flutter_devices", "flutter devices --machine",
                 "Enumerate Flutter devices; an empty response is not a ready device"),),
    "cargo": (("rust_targets", "rustup target list --installed",
               "Enumerate installed Rust targets; this is not a cross-platform build"),),
    "pio": (("platformio_boards", "pio boards",
             "Enumerate supported board definitions; no hardware is connected or flashed"),),
}
PROBE_DEPENDENCIES = {"rust_targets": "rustup"}


def _id(prefix, fingerprint, execution, image, cwd, command):
    serial = "\0".join((fingerprint or "", execution, image, cwd, command))
    return prefix + hashlib.sha256(serial.encode()).hexdigest()[:20]


def _root_of(manifest):
    return str(PurePosixPath(manifest).parent)


def _project_file(names, root, filename):
    return (filename if root == "." else root + "/" + filename) in names


def _host_status(workspace, tool, root, which):
    if tool == "python":
        return "found_on_path" if python_argv(workspace.root / root) else "missing_on_path"
    return "found_on_path" if which(tool) else "missing_on_path"


def inspect_environment(workspace, goal="", execution="local", *,
                        docker_image="", files=None, which=None):
    """Inspect native toolchain and dependency lockfile signals, never execute."""
    names = workspace.files(limit=2001) if files is None else files
    names = names[:2000]
    file_set = set(names)
    which = which or shutil.which
    project = discover_adapters(workspace, goal, execution, files=names, which=which)
    fingerprint = workspace.fingerprint()
    probes, setup = [], []
    seen = set()

    def add_probe(tool, cwd, domain, adapter_id):
        if tool not in TOOL_PROBES:
            return
        version = TOOL_PROBES[tool]
        if tool == "python":
            if execution == "docker":
                version = "python3 --version"
            else:
                argv = python_argv(workspace.root / cwd)
                version = shell_command([*argv, "--version"]) if argv else "python3 --version"
        status = ("container_unchecked" if execution == "docker" else
                  _host_status(workspace, tool, cwd, which))
        command_key = (cwd, version, "version")
        if command_key not in seen:
            seen.add(command_key)
            probes.append({
                "id": _id("probe-", fingerprint, execution, docker_image, cwd, version),
                "domain": domain, "adapter_id": adapter_id, "kind": "tool_version",
                "tool": tool, "cwd": cwd, "command": version,
                "availability": status, "target_verified": False,
                "description": "Probe executable version in the chosen execution environment",
            })
        for label, command, description in TARGET_PROBES.get(tool, ()):
            dependency = PROBE_DEPENDENCIES.get(label, tool)
            extra_status = ("container_unchecked" if execution == "docker" else
                            _host_status(workspace, dependency, cwd, which))
            command_key = (cwd, command, label)
            if command_key not in seen:
                seen.add(command_key)
                probes.append({
                    "id": _id("probe-", fingerprint, execution, docker_image, cwd, command),
                    "domain": domain, "adapter_id": adapter_id, "kind": label,
                    "tool": dependency, "cwd": cwd, "command": command,
                    "availability": extra_status, "target_verified": False,
                    "description": description,
                })

    for adapter in project["adapters"]:
        add_probe(adapter["tool"], adapter["cwd"], adapter["domain"], adapter["id"])

    # Setup candidates are driven by files, NOT arbitrary package scripts or
    # prose. Commands are exact constants with no user-provided shell fragments.
    roots = sorted({_root_of(a["source"]) for a in project["adapters"]})
    for root in roots:
        choices = []
        if _project_file(file_set, root, "package.json"):
            if _project_file(file_set, root, "package-lock.json"):
                choices.append(("npm", "npm ci --ignore-scripts --no-audit --no-fund",
                                "Install locked npm dependencies without lifecycle scripts",
                                "package-lock.json"))
            if _project_file(file_set, root, "pnpm-lock.yaml"):
                choices.append(("pnpm", "pnpm install --frozen-lockfile --ignore-scripts",
                                "Install frozen pnpm dependencies without lifecycle scripts",
                                "pnpm-lock.yaml"))
        if _project_file(file_set, root, "Cargo.toml") and _project_file(file_set, root, "Cargo.lock"):
            choices.append(("cargo", "cargo fetch --locked",
                            "Fetch Rust dependencies from the existing lockfile; does not compile",
                            "Cargo.lock"))
        if _project_file(file_set, root, "go.mod") and _project_file(file_set, root, "go.sum"):
            choices.append(("go", "go mod download",
                            "Download Go modules; may update local caches or checksums",
                            "go.sum"))
        if _project_file(file_set, root, "pubspec.yaml") and _project_file(file_set, root, "pubspec.lock"):
            choices.append(("flutter", "flutter pub get",
                            "Resolve existing Flutter packages; may use network and cache",
                            "pubspec.lock"))
        if (_project_file(file_set, root, "pyproject.toml") or
            _project_file(file_set, root, "requirements.txt")):
            # Safe first step only: no automatic pip installation of unsigned,
            # unhashed arbitrary code or import-time hooks.
            venv = workspace.root / root / ".venv"
            if not venv.exists():
                if execution == "docker":
                    cmd, tool = "python3 -m venv .venv", "python3"
                else:
                    argv = python_argv(workspace.root / root)
                    cmd, tool = (shell_command([*argv, "-m", "venv", ".venv"]), "python") if argv else (
                        "python3 -m venv .venv", "python")
                choices.append((tool, cmd, "Create project-local Python virtual environment; does not install packages",
                                "pyproject.toml" if _project_file(file_set, root, "pyproject.toml") else "requirements.txt"))
        for tool, command, description, lock in choices:
            setup.append({
                "id": _id("setup-", fingerprint, execution, docker_image, root, command),
                "tool": tool, "cwd": root, "command": command, "manifest": (
                    lock if root == "." else root + "/" + lock),
                "availability": ("container_unchecked" if execution == "docker" else
                                 _host_status(workspace, tool, root, which)),
                "description": description,
                "requires_user_approval": True, "may_access_network": "venv" not in command,
                "changes_project_or_cache": True,
                "acceptance_evidence": False,
            })
    return {
        "version": 1, "execution": execution,
        "docker_image": docker_image if execution == "docker" else None,
        "probes": probes[:40], "dependency_setup": setup[:24],
        "missing_project_adapters": project["missing_adapters"],
        "scan_truncated": len(names) >= 2000,
        "note": ("Inspection is read-only. PATH presence does not prove runnable targets. "
                 "A successful version/device-list probe proves only that command ran; "
                 "an empty device list is not a validated device. Setup changes local "
                 "workspace/cache and requires normal command-runner approval. "
                 "No system toolchain installations, cloud deployments or flashing."),
    }


def resolve_environment_action(workspace, goal, execution, docker_image, action_id):
    if not isinstance(action_id, str) or not action_id.startswith(("probe-", "setup-")):
        raise ValueError("Unknown engineering environment action ID.")
    listing = inspect_environment(workspace, goal, execution, docker_image=docker_image)
    options = listing["probes"] if action_id.startswith("probe-") else listing["dependency_setup"]
    action = next((entry for entry in options if entry["id"] == action_id), None)
    if action is None:
        raise ValueError("Engineering environment action is stale or unavailable. Inspect again.")
    if action["availability"] == "missing_on_path":
        raise ValueError("Tool '" + action["tool"] +
                         "' is not installed on the host PATH. Install it explicitly; "
                         "the assistant cannot provision system executables.")
    return action
