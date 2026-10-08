"""Application state and background runs for the local graphical workspace."""

import difflib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import uuid
from urllib.parse import urlsplit

from . import __version__
from .agent import Agent
from .answers import display_reply
from .change_intent import requests_code_change
from .config import Config, load_config, SPARKLE_GATEWAY_URL
from .brief import read_brief, save_brief
from .diagnostics import inspect_setup
from .efficiency import PROFILE_VERSION
from .demo import DemoProvider, calls, python_command
from .provider import NemotronClient
from .cloud import CloudAccount, distribution
from .monitor import Run, ACTIVE, session_events
from .files import UserFiles
from .site_preview import preview_site
from .media_library import import_commons_image, create_svg_graphic
from .internet import search_public_assets
from .storage import resolve_storage, relocate, migrate_legacy, retry_migration, reconnect_portable_projects
from .state import Session, now
from .explanations import check_title, explain_failure, simple_recovery
from .verification import proof_summary, replacements, active_checks
from .skills import (catalog as skill_catalog, delete_custom_skill, save_custom_skill, set_overrides)
from .vision_review import public_configuration as vision_public_configuration
from .workspace import Redactor, Workspace, clean_terminal, write_json, sha256


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        # Packaged with PyInstaller: __file__ points inside a temporary
        # extraction directory that's deleted when the app closes, so
        # PROJECTS/ and APP_DATA/ must live next to the real executable
        # instead, or every tester's data would vanish between runs.
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_app_dir() -> Path:
    return application_root() / "APP_DATA"


_BUDGET_PAUSE_PREFIXES = (
    "Model-call limit reached.",
    "Run time budget reached.",
    "Run token budget reached.",
)


def promote_budget_resume(state):
    """A resumed auto-budget task gets the standard run budget instead of looping."""
    summary = str(state.get("summary") or "")
    if state.get("status") != "paused" or not any(summary.startswith(prefix) for prefix in _BUDGET_PAUSE_PREFIXES):
        return False
    profile = state.get("task_profile")
    if isinstance(profile, dict) and profile.get("name") == "standard" and profile.get("version") == PROFILE_VERSION:
        return False
    state["task_profile"] = {"version": PROFILE_VERSION, "name": "standard"}
    return True


def legacy_app_dirs() -> tuple[Path, Path]:
    if os.name == "nt":
        parent = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        current, legacy = parent / "SparkleCoder", parent / "NemotronWorkspace"
    elif os.sys.platform == "darwin":
        parent = Path.home() / "Library" / "Application Support"
        current, legacy = parent / "SparkleCoder", parent / "NemotronWorkspace"
    else:
        parent = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        current, legacy = parent / "sparkle-coder", parent / "nemotron-workspace"
    return current, legacy


SETTINGS = ("base_url", "model", "tool_format", "execution", "max_steps", "max_seconds",
            "max_total_tokens", "max_tokens", "request_timeout", "command_timeout", "context_chars", "efficiency")
SETTINGS_SCHEMA_VERSION = 5
LEGACY_RUN_CAPS = {"max_steps": 40, "max_seconds": 1800, "max_total_tokens": 250000}


class BrowserDemo:
    """Scripted model; one real command deliberately requests browser approval."""
    def __init__(self):
        self.inner = DemoProvider()
        self.offered_command = False

    def complete(self, messages, schemas):
        if self.inner.phase == 2 and not self.offered_command:
            self.offered_command = True
            # Parse without generating a timestamp-based .pyc: rapid same-size edits
            # in this demo must not reuse bytecode from the deliberately broken file.
            script = "import ast; from pathlib import Path; ast.parse(Path('calculator.py').read_text()); print('Syntax check passed')"
            return calls(("run_command", {"command": python_command("-c", script)}))
        return self.inner.complete(messages, schemas)


class AppService:
    def __init__(self, directory: Path, provider_factory=NemotronClient):
        self.bootstrap = directory.expanduser().resolve()
        portable = self.bootstrap == default_app_dir()
        if portable:
            migrate_legacy(self.bootstrap, application_root() / "PROJECTS", legacy_app_dirs())
        self.directory = resolve_storage(self.bootstrap)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.account = CloudAccount(self.directory, distribution())
        self.settings_path = self.directory / "settings.json"
        if self.settings_path.is_symlink():
            raise ValueError("Application settings must not be a symlink.")
        defaults = {key: getattr(Config(), key) for key in SETTINGS}
        self.data = {"settings": defaults, "projects": [], "selected_project": None,
                     "settings_version": SETTINGS_SCHEMA_VERSION, "experience": "simple"}
        self.projects_directory = (application_root() / "PROJECTS" if portable and self.directory == self.bootstrap
                                   else self.directory / "PROJECTS")
        migrated = False
        if self.settings_path.exists():
            saved = json.loads(self.settings_path.read_text("utf-8"))
            migrated = reconnect_portable_projects(saved, self.projects_directory)
            self.data["settings"].update({k: v for k, v in saved.get("settings", {}).items() if k in SETTINGS})
            self.data["projects"] = saved.get("projects", [])
            self.data["selected_project"] = saved.get("selected_project")
            if saved.get("experience") in ("simple", "advanced"):
                self.data["experience"] = saved["experience"]
            if saved.get("storage_migration"):
                self.data["storage_migration"] = saved["storage_migration"]
            saved_version = saved.get("settings_version", 1)
            if type(saved_version) is not int:
                saved_version = 1
            if saved_version < 2:
                for key, legacy_value in LEGACY_RUN_CAPS.items():
                    if self.data["settings"].get(key) == legacy_value:
                        self.data["settings"][key] = None
                        migrated = True
            if saved_version < 3 and self.data["settings"].get("command_timeout") == 120:
                self.data["settings"]["command_timeout"] = None
            if saved_version < 3 and self.data["settings"].get("request_timeout") == 120:
                self.data["settings"]["request_timeout"] = 300
            if saved_version < 4:
                if self.data['settings'].get('context_chars') == 120000:
                    self.data['settings']['context_chars'] = 24000
            if saved_version < 5:
                # A prior migration cut max_tokens to 4096, which is too small to write a
                # complete file in one response. A truncated response is discarded and
                # retried, resending the whole growing context each time and multiplying
                # prompt-token usage. Restore a working ceiling for anyone left on the old
                # default value; preserve other user-selected output limits.
                if self.data['settings'].get('max_tokens') == 4096:
                    self.data['settings']['max_tokens'] = 16000
            migrated = migrated or saved_version < SETTINGS_SCHEMA_VERSION
        self.lock = threading.RLock()
        self.keys = {}
        self.connected_endpoint = None
        self.jobs = {}
        self.provider_factory = provider_factory
        self.data["projects_path"] = str(self.projects_directory)
        self.projects_directory.mkdir(parents=True, exist_ok=True)
        if migrated:
            self.save()
        if not self.data["projects"]:
            self.add_project("My project", str(self.projects_directory / "my-project"))
        else:
            available = [p for p in self.data["projects"] if Path(p["path"]).is_dir() and not p.get("migration_pending")]
            if not available:
                # Use a distinct new folder; never recreate a missing project's
                # path and silently present its empty history as recovered work.
                self.add_project("New project")
            elif self.data["selected_project"] not in {p["id"] for p in available}:
                self.data["selected_project"] = available[0]["id"]
                self.save()

    def save(self):
        # Deliberately excludes API keys and run access tokens.
        with self.lock:
            write_json(self.settings_path, self.data)

    def config(self, workspace=None):
        with self.lock:
            selected = dict(self.data["settings"])
            config = load_config(workspace.root, selected) if workspace else Config(**selected)
            config.auto_approve = False
            endpoint = config.base_url.rstrip("/")
            if endpoint in self.keys:
                config._runtime_api_key = self.keys[endpoint]
            elif urlsplit(endpoint).hostname != "integrate.api.nvidia.com":
                config._runtime_api_key = os.environ.get("LOCAL_MODEL_API_KEY", "")
            if urlsplit(endpoint).hostname != "integrate.api.nvidia.com" and config.extra_body == Config().extra_body:
                config.extra_body = {}
            if self.account.url:
                config.base_url = self.account.url + '/v1'
                config.model = 'nvidia/nemotron-3-super-120b-a12b'
                config._runtime_api_key = self.account.secret
                config._runtime_cloud = True
                config.extra_body = {}
                # The shared gateway validates an 8192-token maximum independently
                # of the personal NVIDIA endpoint's larger output setting.
                config.max_tokens = min(config.max_tokens, 8192)
                config.context_chars = min(config.context_chars, 30000)
            config.validate()
            return config

    def public_settings(self):
        config = self.config()
        return {**self.data["settings"], "base_url": config.base_url, "model": config.model,
                "cloud_gateway_url": self.account.url + '/v1' if self.account.url else SPARKLE_GATEWAY_URL, "key_configured": bool(config.api_key),
                "key_source": ("memory" if config.base_url.rstrip("/") in self.keys else "environment") if config.api_key else "none",
                "connected": self.connected_endpoint == (config.base_url, config.model)}

    def configure(self, payload):
        if self.account.url and set(payload).intersection({'base_url', 'model', 'api_key', 'clear_key', 'tool_format'}):
            raise ValueError('Your model connection is managed by the admin. Open Account to request access or credits.')
        if not isinstance(payload, dict) or set(payload) - set(SETTINGS) - {"api_key", "clear_key"}:
            raise ValueError("Invalid settings.")
        with self.lock:
            candidate = {**self.data["settings"], **{k: v for k, v in payload.items() if k in SETTINGS}}
            candidate["base_url"] = candidate["base_url"].rstrip("/")
            config = Config(**candidate)
            config.validate()
            key = payload.get("api_key", "")
            if not isinstance(key, str) or len(key) > 2000 or any(c in key for c in "\r\n"):
                raise ValueError("Invalid API key.")
            previous = self.config()
            if payload.get("clear_key"):
                self.keys[config.base_url] = ""
            elif key:
                self.keys[config.base_url] = key.strip()
            self.data["settings"] = candidate
            current = self.config()
            if (previous.base_url, previous.model, previous.api_key) != (current.base_url, current.model, current.api_key):
                self.connected_endpoint = None
            self.save()
            return self.public_settings()

    def connect(self):
        config = self.config()
        config.require_credentials()
        client = self.provider_factory(config)
        available = client.models()
        if config.model not in available:
            return {"connected": False, "models": available,
                    "message": "Endpoint reached, but this model ID was not listed. Choose a served model."}
        self.connected_endpoint = (config.base_url, config.model)
        result = {"connected": True, "models": available, "message": "AI is connected."}
        balance = (client.balance() if config.base_url.rstrip("/") == SPARKLE_GATEWAY_URL
                   and callable(getattr(client, "balance", None)) else None)
        if balance is not None:
            result["balance_tokens"] = balance.get("balance_tokens")
            result["balance_name"] = balance.get("name")
        return result

    def add_project(self, name="", path="", purpose=""):
        if not isinstance(name, str) or not isinstance(path, str) or len(name) > 100 or len(path) > 2000:
            raise ValueError("Invalid project name or path.")
        name = name.strip() or "Untitled project"
        if not isinstance(purpose, str) or len(purpose) > 2000:
            raise ValueError("Keep the project purpose under 2000 characters.")
        purpose = purpose.strip()
        if not path.strip():
            slug = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-") or "project"
            path = str(self.projects_directory / (slug + "-" + uuid.uuid4().hex[:6]))
        root = Path(path).expanduser()
        if not root.is_absolute():
            raise ValueError("Use an absolute project folder path, or leave it blank to create a project.")
        root = root.resolve()
        with self.lock:
            existing = next((p for p in self.data["projects"] if Path(p["path"]).resolve() == root), None)
            if existing and existing.get("migration_pending"):
                raise ValueError("This project is waiting to move. Choose Retry project move first.")
            workspace = Workspace(root, create=existing is None)
            if existing:
                self.data["selected_project"] = existing["id"]
                self.save()
                return existing
            if purpose:
                saved = read_brief(workspace)
                # Importing an existing folder never silently replaces its brief.
                if not saved["brief"]["purpose"]:
                    save_brief(workspace, {**saved["brief"], "purpose": purpose}, saved["revision"])
            project = {"id": uuid.uuid4().hex[:12], "name": name, "path": str(workspace.root), "created": now()}
            self.data["projects"].append(project)
            self.data["selected_project"] = project["id"]
            self.save()
            return project

    def project(self, project_id):
        with self.lock:
            project = next((p for p in self.data["projects"] if p["id"] == project_id), None)
            if not project:
                raise ValueError("Project not found.")
            if project.get("migration_pending"):
                raise ValueError("This project is waiting to move. Choose Retry project move. " + project["migration_pending"])
            return project, Workspace(Path(project["path"]), create=False)

    def delete_project(self, project_id, name, delete_files=False):
        if type(delete_files) is not bool:
            raise ValueError("Choose whether to keep or permanently delete project files.")
        with self.lock:
            project = next((p for p in self.data["projects"] if p["id"] == project_id), None)
            if project is None:
                raise ValueError("Project not found.")
            if not isinstance(name, str) or name != project["name"]:
                raise ValueError("Enter the exact project name to confirm removal.")
            if self.active(project_id):
                raise ValueError("Stop this project's running task before deleting it.")
            root = Path(project["path"])
            managed = (not root.is_symlink() and root.resolve().parent == self.projects_directory.resolve()
                       and root.resolve() != self.projects_directory.resolve())
            if delete_files and (not managed or not root.is_dir()):
                raise ValueError("Only available SPARKLE-managed project folders can be permanently deleted. Remove this project from the list and manage external files separately.")
            original = list(self.data["projects"])
            selected = self.data["selected_project"]
            quarantine = None
            if delete_files:
                quarantine = self.projects_directory / (".sparkle-deleting-" + project_id)
                if quarantine.exists() or quarantine.is_symlink():
                    raise ValueError("Previous project deletion needs owner attention.")
                root.rename(quarantine)
            self.data["projects"] = [p for p in original if p["id"] != project_id]
            if selected == project_id:
                self.data["selected_project"] = self.data["projects"][0]["id"] if self.data["projects"] else None
            try:
                self.save()
            except Exception:
                self.data["projects"] = original
                self.data["selected_project"] = selected
                if quarantine is not None:
                    quarantine.rename(root)
                raise
            if quarantine is not None:
                try:
                    shutil.rmtree(quarantine)
                except OSError:
                    return {"removed": True, "files_deleted": False,
                            "message": "Project removed from the list, but some files could not be deleted. Ask the owner to inspect the pending deletion folder."}
            return {"removed": True, "files_deleted": delete_files,
                    "message": "Project and its files deleted." if delete_files else
                               "Project removed from the list. Its files and saved tasks remain in the original folder."}

    def delete_session(self, project_id, session_id):
        with self.lock:
            if self.active(project_id):
                raise ValueError("Stop this project's running task before deleting its history.")
            _, workspace = self.project(project_id)
            with workspace.lock():
                session = Session.load(workspace, session_id)
                if session.directory.is_symlink():
                    raise ValueError("Saved task directory cannot be a symlink.")
                shutil.rmtree(session.directory)
                # The task has already been removed. A statistics failure must
                # not report a false deletion failure and tempt a second request.
                warning = ""
                metrics = workspace.state_dir / "skill-metrics.json"
                if metrics.exists() and not metrics.is_symlink():
                    try:
                        values = json.loads(metrics.read_text("utf-8"))
                        if isinstance(values, dict) and isinstance(values.get("sessions"), dict):
                            values["sessions"].pop(session_id, None)
                            write_json(metrics, values)
                    except (OSError, ValueError, TypeError):
                        warning = " Skill statistics could not be refreshed."
            return {"deleted": session_id, "message": "Saved task history deleted. Project files were not changed." + warning}

    def clear_history(self, project_id):
        with self.lock:
            if self.active(project_id):
                raise ValueError("Stop this project's running task before clearing its history.")
            _, workspace = self.project(project_id)
            directory = workspace.state_dir / "sessions"
            if directory.is_symlink():
                raise ValueError("Saved tasks folder must not be a symlink.")
            with workspace.lock():
                if not directory.exists():
                    return {"deleted": 0}
                session_ids = [p.name for p in directory.iterdir()]
                if any(not (directory / item).is_dir() for item in session_ids):
                    raise ValueError("Unexpected saved task file. Inspect it before clearing history.")
                if any(not re.fullmatch(r"[a-f0-9]{12}", item) for item in session_ids):
                    raise ValueError("Unexpected history folder. Inspect it before deleting saved tasks.")
                if any((directory / item).is_symlink() for item in session_ids):
                    raise ValueError("A saved task is a symlink. Review it before clearing history.")
                for item in session_ids:
                    shutil.rmtree(directory / item)
                warning = ""
                metrics = workspace.state_dir / "skill-metrics.json"
                if metrics.exists() and not metrics.is_symlink():
                    try:
                        write_json(metrics, {"version": 1, "sessions": {}})
                    except OSError:
                        warning = " Skill statistics could not be refreshed."
            return {"deleted": len(session_ids), "message": "Saved conversations and undo history deleted. Project files were not changed." + warning}

    def suggest_brief(self, project_id):
        _, workspace = self.project(project_id)
        saved = read_brief(workspace)
        # Project purpose is the earliest implementation goal, not whichever
        # session was updated last. Sort explicitly by creation time; existing
        # second-resolution records use a stable ID tie-break.
        history = sorted(self.history(project_id),
                         key=lambda item: (item.get("created") or "", item["id"]))
        goals = []
        for item in history:
            try:
                state = Session.load(workspace, item["id"]).state
            except (OSError, ValueError):
                continue
            # Questions in Ask mode are not implementation requirements.
            if state.get("task_mode") == "ask":
                continue
            text = item.get("goal")
            if isinstance(text, str) and text.strip() and text.strip() not in goals:
                goals.append(text.strip())
        purpose = next((goal for goal in goals if len(goal) <= 2000), "")
        requirements = [goal for goal in goals if goal != purpose and len(goal) <= 300][-19:]
        if purpose and len(purpose) <= 300:
            requirements.insert(0, purpose)
        requirements = requirements[:20]
        return {"brief": {"purpose": purpose, "requirements": requirements, "constraints": ""},
                "revision": saved["revision"], "sources": len(goals),
                "note": ("Suggestions use your saved task requests only, not AI-invented features or verified functionality. "
                         "Review and edit before saving. Existing brief fields are preserved." if goals else
                         "No saved task requests yet. Add your project purpose and requirements manually.")}

    def reconnect_project(self, project_id, path):
        if not isinstance(path, str) or not path.strip() or len(path) > 2000:
            raise ValueError("Choose the existing folder that contains your project files.")
        root = Path(path).expanduser()
        if not root.is_absolute():
            raise ValueError("Use Browse or paste the full, absolute folder path.")
        root = root.resolve()
        with self.lock:
            if self.active():
                raise ValueError("Finish or stop the active task before reconnecting a project.")
            project = next((p for p in self.data["projects"] if p["id"] == project_id), None)
            if not project:
                raise ValueError("Project not found.")
            if project.get("migration_pending"):
                raise ValueError("This project is waiting to move. Choose Retry project move first.")
            if Path(project["path"]).is_dir() and root != Path(project["path"]).resolve():
                raise ValueError("This project is already available. Refresh the app to open it.")
            if any(p["id"] != project_id and Path(p["path"]).resolve() == root for p in self.data["projects"]):
                raise ValueError("That folder is already listed as another project. Select that project instead.")
            workspace = Workspace(root, create=False)
            with workspace.lock():
                original = project["path"]
                previous_selected = self.data["selected_project"]
                previous_paths = project.get("previous_paths")
                if str(root) != original:
                    project["previous_paths"] = list(dict.fromkeys((previous_paths or []) + [original]))
                project["path"] = str(root)
                self.data["selected_project"] = project_id
                try:
                    self.save()
                except Exception:
                    project["path"] = original
                    if previous_paths is None:
                        project.pop("previous_paths", None)
                    else:
                        project["previous_paths"] = previous_paths
                    self.data["selected_project"] = previous_selected
                    raise
            return {**project, "available": True}

    def active(self, project_id=None):
        with self.lock:
            return next((job for job in self.jobs.values()
                         if job.status in ACTIVE and
                         (project_id is None or job.project_id == project_id)), None)

    def active_jobs(self):
        with self.lock:
            return [job for job in self.jobs.values() if job.status in ACTIVE]

    def _repair_orphaned_session(self, session):
        if session.state.get("status") != "running":
            return session
        # Another project's active run must not mask an orphaned session.
        if any(job.session_id == session.id for job in self.active_jobs()):
            return session
        session.state["status"] = "interrupted"
        session.state["summary"] = "The coding engine restarted while this task was active. Work is saved; resume to continue."
        session.state["recovery"] = None
        session.save()
        return session

    def state(self):
        with self.lock:
            selected = self.data["selected_project"]
            jobs = self.active_jobs()
            job = next((entry for entry in jobs if entry.project_id == selected), None)
            return {"version": __version__, "projects": [
                        {**p, "available": Path(p["path"]).is_dir() and not p.get("migration_pending", False),
                         "managed": (not Path(p["path"]).is_symlink() and
                                     Path(p["path"]).resolve().parent == self.projects_directory.resolve())}
                        for p in self.data["projects"]],
                    "experience": self.data["experience"],
                    "selected_project": self.data["selected_project"],
                    "settings": self.public_settings(), "active_run": job.public() if job else None,
                    "active_runs": [{"id": entry.id, "project_id": entry.project_id, "status": entry.status}
                                    for entry in jobs],
                    "account": dict(self.account.cached),
                    "storage": {"path": str(self.directory), "projects_path": str(self.projects_directory),
                                "migration": self.data.get("storage_migration")}}

    def experience(self, value):
        if value not in ("simple", "advanced"):
            raise ValueError("Choose the simple or advanced view.")
        with self.lock:
            self.data["experience"] = value
            self.save()
        return {"experience": value}

    def project_context(self, project_id, payload=None):
        with self.lock:
            _, workspace = self.project(project_id)
            redactor = Redactor((self.config(workspace).api_key,))
            if payload is None:
                return redactor.value(read_brief(workspace))
            if not isinstance(payload, dict) or set(payload) != {"brief", "revision"}:
                raise ValueError("Provide the brief and its current revision.")
            if self.active(project_id):
                raise ValueError("Finish or stop this project's running task before changing its brief.")
            with workspace.lock():
                return save_brief(workspace, redactor.value(payload["brief"]), payload["revision"])

    def setup(self, project_id):
        _, workspace = self.project(project_id)
        config = self.config(workspace)
        report = inspect_setup(workspace, config,
                               self.connected_endpoint == (config.base_url, config.model))
        return Redactor((config.api_key,)).value(report)

    def project_skills(self, project_id):
        _, workspace = self.project(project_id)
        result = skill_catalog(workspace)
        result["vision"] = vision_public_configuration()
        return result

    def configure_project_skills(self, project_id, payload):
        if not isinstance(payload, dict):
            raise ValueError("Expected skill settings object.")
        if self.active(project_id):
            raise ValueError("Finish or stop this project's running task before changing its skills.")
        _, workspace = self.project(project_id)
        action = payload.get("action")
        if action == "save_custom":
            save_custom_skill(workspace, payload.get("id"), payload.get("title"), payload.get("triggers", []), payload.get("body"))
        elif action == "delete_custom":
            delete_custom_skill(workspace, payload.get("id"))
        elif action == "overrides":
            set_overrides(workspace, payload.get("enabled", []), payload.get("disabled", []), payload.get("vision_review", False))
        else:
            raise ValueError("Unknown skill settings action.")
        return self.project_skills(project_id)

    def snapshot(self, project_id, session_id, include_events=True):
        _, workspace = self.project(project_id)
        session = self._repair_orphaned_session(Session.load(workspace, session_id))
        state = session.state
        # A saved result may be opened after a manual edit or file import. Do
        # not label that evidence current just because the task has not resumed.
        if (state.get("verification_fingerprint") and state["status"] != "running"
                and workspace.fingerprint() != state["verification_fingerprint"]):
            state["verification_fingerprint"] = None
        user_requests = set(state.get("user_requests", [state["goal"]]))
        messages = []
        latest_request = state.get("goal", "")
        visible = state.get("visible_message_indices")
        accepted = set(visible) if isinstance(visible, list) else None
        for index, message in enumerate(state["messages"]):
            if message.get("role") == "user" and message.get("content") in user_requests:
                latest_request = message["content"]
                messages.append({"role": "user", "content": latest_request})
            elif (message.get("role") == "assistant" and message.get("content")
                  and not message.get("tool_calls")
                  and (accepted is None or index in accepted)):
                # An unverified completion proposal isn't a result. Retain it
                # internally for continuity and diagnostics, not as a user reply.
                # Older sessions have no visibility index and stay readable.
                messages.append({"role": "assistant", "content":
                                 display_reply(message["content"], latest_request)})
        recovery = state.get("recovery")
        if state["status"] in ("needs_input", "blocked", "unverified") and not (recovery or {}).get("title"):
            recovery = simple_recovery(state, state.get("summary", ""), (recovery or {}).get("action", "checks"))
        required = set(state["required_checks"])
        retired = {key: revision for key, revision in replacements(state).items()
                   if not any(c["key"] == key and (c.get("required") or c["command"] in required)
                              for c in state["checks"])}
        active_ids = {c["id"] for c in active_checks(state)}
        checks = [{**check, "label": check.get("label") or check_title(check["command"]),
                   "active": check["id"] in active_ids, "superseded": check["key"] in retired,
                   "correction_reason": retired.get(check["key"], {}).get("reason", ""),
                   "explanation": explain_failure(check) if not check["ok"] else None}
                  for check in state["checks"][-60:]]
        return {key: state.get(key) for key in
                ("id", "goal", "status", "created", "updated", "plan", "usage", "summary", "model", "undone", "task_mode", "recovery",
                 "project_brief", "requirements", "setup", "repair_history", "skills")} | {
            "messages": messages, "actions": state["actions"][-100:], "checks": checks,
            "recovery": recovery, "proof": proof_summary(state), "delivery": state.get("delivery", {}),
            "check_revisions": state.get("check_revisions", []),
            "changed_files": sorted({r["path"] for r in state["journal"]}),
            "required_checks": state["required_checks"],
            "events": session_events(session) if include_events else [],
        }

    def history(self, project_id):
        _, workspace = self.project(project_id)
        directory = workspace.state_dir / "sessions"
        if directory.is_symlink():
            raise ValueError("Session directory must not be a symlink.")
        result = []
        for path in directory.glob("*/state.json"):
            try:
                session = self._repair_orphaned_session(Session.load(workspace, path.parent.name))
                state = session.state
                result.append({k: state.get(k) for k in ("id", "goal", "status", "created", "updated", "undone")})
            except (OSError, ValueError):
                continue
        return sorted(result, key=lambda x: x["updated"], reverse=True)[:100]

    def changes(self, project_id, session_id):
        _, workspace = self.project(project_id)
        session = Session.load(workspace, session_id)
        first = {}
        for record in session.state["journal"]:
            first.setdefault(record["path"], record)
        changes = []
        for name, record in first.items():
            before = ""
            if record["backup"]:
                if not re.fullmatch(r"before-\d+\.bin", record["backup"]):
                    raise ValueError("Invalid backup entry.")
                backup = session.directory / record["backup"]
                if backup.is_symlink():
                    raise ValueError("Backup must not be a symlink.")
                before = backup.read_bytes()[:200000].decode("utf-8", errors="replace")
            path = workspace.path(name)
            after = path.read_bytes()[:200000].decode("utf-8", errors="replace") if path.exists() else ""
            lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                             fromfile="before/" + name, tofile="after/" + name, lineterm=""))
            changes.append({"path": name, "added": sum(l.startswith("+") and not l.startswith("+++") for l in lines),
                            "removed": sum(l.startswith("-") and not l.startswith("---") for l in lines),
                            "diff": "\n".join(lines)[:40000], "truncated": len("\n".join(lines)) > 40000})
        return Redactor((self.config().api_key,)).value(changes)

    def start(self, project_id, goal, verify=None, session_id=None, demo=False, review_edits=False, task_mode=None):
        if task_mode not in (None, "build", "ask"):
            raise ValueError("Task mode must be build or ask.")
        if type(review_edits) is not bool:
            raise ValueError("Review edits must be true or false.")
        if not isinstance(goal, str) or len(goal) > 48000 or len(goal.encode("utf-8")) > 131072 or not goal.strip() and not session_id:
            raise ValueError("Describe a task using at most 48,000 characters (128 KiB of text). Your prompt was not shortened. Split longer instructions into follow-up messages or a project brief.")
        verify = verify or []
        if not isinstance(verify, list) or len(verify) > 20 or any(
                not isinstance(c, str) or not c.strip() or len(c) > 10000 for c in verify):
            raise ValueError("Use at most 20 nonempty verification commands.")
        project, workspace = self.project(project_id)
        config = self.config(workspace)
        if demo:
            config.model = "OFFLINE-SCRIPTED-DEMO"
            config.execution = "local"
            config.max_steps = 15
            verify = [python_command("-m", "unittest", "discover", "-s", "tests", "-v")]
        else:
            config.require_credentials()
        goal = Redactor((config.api_key,)).text(goal)
        with self.lock:
            if not any(p["id"] == project_id for p in self.data["projects"]):
                raise ValueError("Project was removed. Select an available project before starting a task.")
            if self.active(project_id):
                raise ValueError("A task is already running in this project. Switch to another project or wait.")
            if len(self.active_jobs()) >= 2:
                raise ValueError("Two projects are already running. Wait for one to finish before starting another.")
            job = Run(project_id, "demo" if demo else "nemotron", config.api_key)
            self.jobs[job.id] = job
            self.data["selected_project"] = project_id
            self.save()
            admission = getattr(self, "run_admission", None)
            if admission is not None:
                try:
                    admission.enqueue(job)
                except Exception:
                    self.jobs.pop(job.id, None)
                    raise

            def work():
                session = None
                admitted = False
                try:
                    if admission is not None:
                        admitted = admission.wait(job)
                        if not admitted:
                            with job.lock:
                                job.finish("interrupted", "Stopped while queued. No model call was started.")
                            return
                    with workspace.lock():
                        if session_id:
                            session = Session.load(workspace, session_id)
                            if session.state.get("undone"):
                                raise ValueError("This task was undone. Start a new task.")
                            session.repair_interrupted_calls()
                            if not goal.strip():
                                promote_budget_resume(session.state)
                            if goal.strip():
                                session.state["messages"].append({"role": "user", "content": goal})
                                session.state.setdefault("user_requests", [session.state["goal"]]).append(goal)
                                # A follow-up can widen a previously tiny task; recalculate its budget/tool profile.
                                session.state.pop("task_profile", None)
                            session.state["required_checks"] = list(dict.fromkeys(session.state["required_checks"] + verify))
                            session.state["model"] = config.public_info()
                            session.save()
                        else:
                            session = Session.create(workspace, goal, verify, config.public_info())
                        intended_mode = task_mode or session.state.get("task_mode", "build")
                        # The browser retains Ask mode from an earlier explanation.
                        # An explicit code-change follow-up must never become a read-only chat.
                        if goal.strip() and requests_code_change(goal):
                            intended_mode = "build"
                        session.state["task_mode"] = intended_mode
                        if goal.strip() and intended_mode == "build" and requests_code_change(goal):
                            session.state["requested_change"] = {
                                "goal": goal,
                                "baseline": workspace.fingerprint(),
                                "journal_start": len(session.state["journal"]),
                            }
                        elif goal.strip():
                            session.state.pop("requested_change", None)
                        session.state["previous_workspaces"] = list(dict.fromkeys(
                            session.state.get("previous_workspaces", []) + project.get("previous_paths", [])))
                        session.save()
                        with job.lock:
                            job.bind(session)
                            job.status = "running"
                        provider = BrowserDemo() if demo else self.provider_factory(config)
                        status = Agent(workspace, session, config, provider, job.approve,
                                       emit=job.emit, should_stop=job.stop.is_set, observe=job.record,
                                       checkpoint=job.checkpoint,
                                       approve_edit=job.approve_edit if review_edits else None).run()
                    # Publish completion only after releasing the project lock.
                    # Otherwise an export that follows a "checked" status can
                    # intermittently fail with HTTP 400 on Windows.
                    with job.lock:
                        job.finish(status, session.state.get("summary", ""))
                except Exception as exc:
                    with job.lock:
                        job.error = clean_terminal(Redactor((config.api_key,)).text(str(exc)))
                        if session is not None:
                            session.state.update({"status": "needs_input", "summary": job.error,
                                "recovery": simple_recovery(session.state, job.error, "retry")})
                            try:
                                session.save()
                            except (OSError, ValueError):
                                job.error += " Recovery status could not be saved; check the device folder permissions and free space."
                        job.emit(job.error)
                        job.finish("needs_input", job.error)
                finally:
                    if admission is not None:
                        if admitted:
                            admission.release(job)
                        else:
                            admission.discard(job)

            job.thread = threading.Thread(target=work, name="nemotron-task", daemon=True)
            try:
                job.thread.start()
            except Exception:
                if admission is not None:
                    admission.discard(job)
                self.jobs.pop(job.id, None)
                raise
            for old_id in list(self.jobs):
                if len(self.jobs) <= 30:
                    break
                if self.jobs[old_id] is not job and not self.jobs[old_id].thread.is_alive():
                    del self.jobs[old_id]
            return job.public()

    def demo(self):
        with self.lock:
            if self.active():
                raise ValueError("Finish or stop the current task before running the demo.")
            project = self.add_project("Demo · calculator", "")
            job = self.start(project["id"], "Build a calculator and verify its behavior.", demo=True)
            return {"project": project, "run": job}

    def job(self, run_id):
        with self.lock:
            if run_id not in self.jobs:
                raise ValueError("Run not found. Its saved session is still available in history.")
            return self.jobs[run_id]

    def site_preview(self, project_id, entry="index.html"):
        _, workspace = self.project(project_id)
        return preview_site(UserFiles(workspace.root), entry)

    def image_search(self, project_id, query):
        self.project(project_id)
        return search_public_assets(query, limit=6)

    def image_action(self, project_id, operation, payload):
        payload=payload or {}
        with self.lock:
            if self.active(project_id):
                raise ValueError("Stop this project's running task before importing or creating media.")
            _, workspace=self.project(project_id)
            with workspace.lock():
                if operation=="import":
                    return import_commons_image(workspace,payload.get("query",""),payload.get("url",""))
                if operation=="create":
                    return create_svg_graphic(workspace,payload.get("title",""),
                                              payload.get("style","soft"),payload.get("primary","#376f58"),
                                              payload.get("secondary","#e6eedc"))
                raise ValueError("Unknown media action.")

    def file_action(self, project_id, operation, body=None):
        body = body or {}
        with self.lock:
            # Export is read-only. Let users download a best-effort snapshot
            # even during a long-running agent; the agent holds workspace.lock
            # for the full run, so acquiring it here would fail or block.
            if operation == "download-project":
                _, workspace = self.project(project_id)
                if self.active(project_id):
                    return UserFiles(workspace.root).archive()
                with workspace.lock():
                    return UserFiles(workspace.root).archive()
            if self.active(project_id):
                raise ValueError("Finish or stop this project's running task before editing or importing files.")
            project, workspace = self.project(project_id)
            files = UserFiles(workspace.root)
            with workspace.lock():
                if operation in {'save-file','delete-file'}:
                    path=body.get('path')
                    content=body.get('content','')
                    if not isinstance(content,str) or len(content.encode('utf-8'))>200000:
                        raise ValueError('Manual text edits support complete files up to 200 KB.')
                    target=workspace.path(path)
                    expected=body.get('expected_sha256')
                    if target.exists():
                        if target.stat().st_size>200000:
                            raise ValueError('Manual text edits support complete files up to 200 KB.')
                        if expected is None or expected!=sha256(target.read_bytes()):
                            raise ValueError('File changed or hash was omitted. Reopen the latest file before saving.')
                    elif expected is not None or operation=='delete-file':
                        raise ValueError('The expected file no longer exists.')
                    session=Session.create(workspace,'Manual '+('edit: ' if operation=='save-file' else 'delete: ')+path,[],self.config(workspace).public_info())
                    result=session.mutate(path,content.encode('utf-8') if operation=='save-file' else None,expected)
                    session.state.update({'status':'unverified','summary':'Manual file change saved. Review or undo it in run history.'})
                    session.save()
                    return {**result,'path':path,'session_id':session.id}
                if operation == "import":
                    return files.import_file(body.get("path"), body.get("data"))
                if operation == "duplicate":
                    return files.duplicate(body.get("source"), body.get("destination"))
                if operation == "export-folder":
                    return files.export_folder(body.get("path"), project["name"])
                raise ValueError("Unknown file operation.")

    def storage(self, path):
        with self.lock:
            if self.active():
                raise ValueError("Finish or stop the active task before switching data folders.")
            result = relocate(self, path)
            self.account.path = self.directory / 'device-account.json'
            return result

    def retry_project_migration(self):
        with self.lock:
            if self.active():
                raise ValueError("Finish or stop the active task before moving projects.")
            return retry_migration(self)

    def export_report(self, project_id, session_id):
        snapshot = self.snapshot(project_id, session_id)
        recovery = snapshot.get("recovery") or {}
        summary = recovery.get("what_happened") or snapshot.get("summary") or "Task has not finished."
        lines = ["# Task report", "", snapshot["goal"], "", "Status: " + snapshot["status"], "",
                 summary]
        if recovery:
            lines += ["", recovery.get("meaning", ""), "", recovery.get("next_step", "")]
        delivery = snapshot.get("delivery", {})
        if delivery.get("how_to_use"):
            lines += ["", "## How to use it", ""]
            lines += [f"{index}. {step}" for index, step in enumerate(delivery["how_to_use"], 1)]
        if delivery.get("limitations"):
            lines += ["", "## Still to check or finish", ""] + ["- " + text for text in delivery["limitations"]]
        proof = snapshot["proof"]
        if proof["requirements"]:
            lines += ["", "## Your requirements", ""]
            lines += ["- " + item["text"] + ": " + item["status"] for item in proof["requirements"]]
        if snapshot.get("repair_history"):
            lines += ["", "## What SPARKLE investigated", ""]
            for item in snapshot["repair_history"]:
                lines += ["- " + item["what_happened"], "  " + item["next_step"],
                          "  Source files inspected: " + (", ".join(item["files"]) or "None found.")]
        lines += ["", f"Recorded checks: {proof['passed']} of {proof['total']} current checks passed.",
                  proof["note"], "", "## File-tool changes", ""]
        lines += ["- " + path for path in snapshot["changed_files"]]
        lines += ["", "## Checks", ""]
        for check in snapshot["checks"]:
            label = "CORRECTED" if check["superseded"] else "RECORDED PASS" if check["ok"] else "NEEDS ATTENTION"
            lines += [label + ": " + check["label"], ""]
            if check["superseded"]:
                lines += ["Reason: " + check["correction_reason"], ""]
            elif check["explanation"]:
                lines += [check["explanation"]["what_happened"], ""]
            lines += ["<details><summary>Technical details</summary>", "", "```text", check["command"],
                      check.get("output", ""), "```", "", "</details>", ""]
        lines += ["## Recent activity", "", "The recent activity excerpt contains up to 200 events.", ""]
        for event in snapshot["events"]:
            lines.append(event.get("at", "") + " " + event.get("kind", "") + " " +
                         str(event.get("text") or event.get("output") or event.get("command") or event.get("path") or ""))
        return Redactor(tuple(self.keys.values())).text("\n".join(lines)).encode("utf-8")

    def export_logs(self, project_id, session_id):
        _, workspace = self.project(project_id)
        session = Session.load(workspace, session_id)
        chunks, total = [], 0
        for path in sorted(session.directory.glob("run-*.jsonl"), key=lambda p: p.stat().st_mtime):
            if path.is_symlink():
                raise ValueError("Run logs must not be symlinks.")
            data = path.read_bytes()
            total += len(data)
            if total > 20 * 1024 * 1024:
                raise ValueError("Logs exceed 20 MiB. Open the project folder to copy its session logs directly.")
            chunks.append(data)
        return Redactor(tuple(self.keys.values())).text(b"".join(chunks).decode("utf-8")).encode("utf-8")

    def undo(self, project_id, session_id, apply=False):
        with self.lock:
            if self.active():
                raise ValueError("Stop the running task before undoing files.")
            _, workspace = self.project(project_id)
            with workspace.lock():
                session = Session.load(workspace, session_id)
                paths = [r["path"] for r in session.undo_preview()]
                if apply:
                    session.undo()
                return {"paths": paths, "applied": apply}

    def close(self):
        pending = [job for job in list(self.jobs.values()) if job.thread and job.thread.is_alive()]
        for job in pending:
            job.cancel()
        # Give foreground commands time to terminate before the GUI process exits.
        # In-flight model requests cannot execute actions once cancellation is set.
        for job in pending:
            if job.thread is not threading.current_thread():
                job.thread.join(timeout=3)
        self.keys.clear()
