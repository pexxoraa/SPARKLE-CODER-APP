"""Deterministic, compact repair triage from fresh failed checks.

Uses recorded check results and current workspace paths. No model call, shell
command, package installation, or source mutation occurs during inspection.
Hints are hypotheses; only rerunning real verification can confirm repairs.
"""
import re
from pathlib import PurePosixPath

from .verification import active_checks

SOURCE_REF = re.compile(
    r'(?:File "([^"\n]+)", line \d+)|'
    r'((?:[\w.-]+/)*[\w.-]+\.(?:py|js|jsx|ts|tsx|rs|go|java|kt|cs|dart|gd|sql)):\d+',
)
TOOLCHAIN_MARKERS = re.compile(
    r"(?:command not found|not recognized as an internal|No such file or directory|"
    r"ModuleNotFoundError|Cannot find module|package .* is not installed)", re.I,
)
ASSERTION_MARKERS = re.compile(r"(?:AssertionError|FAILED|expected .* but|assertion failed)", re.I)
SYNTAX_MARKERS = re.compile(
    r"(?:SyntaxError|IndentationError|ParseError|unexpected token|compilation error|cannot compile)", re.I,
)
ACCESS_MARKERS = re.compile(r"(?:permission denied|access is denied|unauthorized)", re.I)


def _file_refs(workspace, message):
    result = []
    for match in SOURCE_REF.finditer(str(message)[-5000:]):
        path = match.group(1) or match.group(2)
        if not path:
            continue
        # Tracebacks sometimes contain absolute workspace paths; never expose
        # paths outside the current project or follow symlinks.
        if path.startswith(str(workspace.root) + "/"):
            path = path[len(str(workspace.root)) + 1:]
        elif path.startswith("/") or ":" in path or "\\" in path:
            continue
        try:
            if workspace.path(path).is_file() and path not in result:
                result.append(path)
        except (OSError, ValueError):
            continue
        if len(result) >= 6:
            break
    return result


def _kind(output, item):
    if item.get("denied"):
        return "permission_denied", "Respect the denial. Do not replay this command."
    if item.get("timed_out"):
        return "timed_out", "Inspect whether the command waits for input, downloads data or watches files."
    if TOOLCHAIN_MARKERS.search(output):
        return "dependency_or_toolchain", "Inspect the installed toolchain and project lockfile before changing source."
    if SYNTAX_MARKERS.search(output):
        return "syntax_or_compile", "Read the referenced code and repair syntax or target compiler errors."
    if ASSERTION_MARKERS.search(output):
        return "test_assertion", "Compare test assumptions against the implementation and actual user requirements."
    if ACCESS_MARKERS.search(output):
        return "permissions", "Inspect paths and permissions; do not bypass user authorization."
    return "unknown_failure", "Read the full stored check log and reproduce the smallest failing case."


def repair_focus(workspace, state):
    """Prioritize fresh, distinct failures, favoring project-owned/required tests."""
    fingerprint = workspace.fingerprint()
    revision = state.get("environment_revision", 0)
    candidates = {}
    for check in active_checks(state):
        if check.get("ok"):
            continue
        if check.get("fingerprint") != fingerprint or check.get("environment_revision", 0) != revision:
            continue
        key = (check.get("command"), check.get("cwd", "."))
        candidates[key] = check
    failures = sorted(candidates.values(), key=lambda c: (
        not bool(c.get("required") or c.get("source") == "user"),
        c.get("command", "")))
    suggestions = []
    for check in failures[:8]:
        output = check.get("output", "") or ""
        kind, advice = _kind(output, check)
        files = _file_refs(workspace, output)
        suggestions.append({
            "check_id": check.get("id"),
            "command": str(check.get("command", ""))[:300],
            "cwd": check.get("cwd", "."),
            "category": kind,
            "source_files": files,
            "next_action": advice,
            "exit_code": check.get("exit_code"),
            "required": bool(check.get("required")),
        })
    return {
        "version": 1, "failures": suggestions,
        "fresh_failures": len(failures),
        "status": "repair_needed" if failures else "no_fresh_failure",
        "note": ("Read the current referenced files, implement a focused repair, "
                 "then rerun the relevant check. This diagnostic never replaces "
                 "a passing check and never changes user requirements."),
    }
