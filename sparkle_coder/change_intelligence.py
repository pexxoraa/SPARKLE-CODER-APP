"""Evidence about changes to *pre-existing* project source.

A new unrelated file can change the workspace fingerprint while leaving an
existing bug untouched. For explicit fix/modify work, preserve a bounded source
baseline and require a material change to pre-existing source before completion.
When a project is too large to snapshot safely, fall back to normal checks and
report the limitation; never pretend an incomplete baseline is exhaustive.
"""
from pathlib import PurePosixPath
import hashlib
import re

SOURCE_SUFFIXES = frozenset({
    ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".html", ".htm", ".css", ".scss", ".vue", ".svelte",
    ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs",
    ".java", ".kt", ".kts", ".swift", ".dart",
    ".gd", ".lua", ".php", ".rb", ".sh", ".ps1",
    ".sql", ".tf", ".yaml", ".yml", ".json", ".toml", ".xml",
})
SOURCE_BASENAMES = frozenset({"Dockerfile", "Makefile", "CMakeLists.txt", "Cargo.lock"})
CHANGE_EXISTING_RE = re.compile(
    r"\b(?:fix(?:ing)?|debug|repair|patch|refactor|modify|modified|change|"
    r"update|correct|improve|optimi[sz]e|rework|remove|rename)\b", re.I,
)
MAX_FILES = 500
MAX_BYTES = 32 * 1024 * 1024


def _is_source(path):
    name = PurePosixPath(path).name
    return name in SOURCE_BASENAMES or PurePosixPath(path).suffix.lower() in SOURCE_SUFFIXES


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(128 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def capture_source_baseline(workspace, goal):
    """Snapshot hashes only, never source content, credentials, or generated dirs."""
    strict = bool(CHANGE_EXISTING_RE.search(str(goal or "")))
    report = {"version": 1, "strict": strict, "complete": False,
              "sources": {}, "reason": "not_applicable"}
    if not strict:
        return report
    try:
        paths = workspace.files(limit=2001)
        if len(paths) > 2000:
            report["reason"] = "workspace_scan_truncated"
            return report
        relevant = [path for path in paths if _is_source(path)]
        if len(relevant) > MAX_FILES:
            report["reason"] = "too_many_existing_source_files"
            return report
        bytes_total = 0
        for name in relevant:
            path = workspace.path(name)
            size = path.stat().st_size
            bytes_total += size
            if bytes_total > MAX_BYTES:
                report["reason"] = "source_size_limit"
                report["sources"] = {}
                return report
            report["sources"][name] = _digest(path)
    except (OSError, ValueError) as exc:
        report["sources"] = {}
        report["reason"] = "source_snapshot_failed"
        return report
    report["complete"] = True
    report["reason"] = "ready" if report["sources"] else "no_existing_source"
    return report


def inspect_change_impact(workspace, requested_change):
    """Evaluate actual modifications; avoid using project-created files as proof."""
    if not isinstance(requested_change, dict):
        return {"status": "no_explicit_change_request", "existing_modified": [],
                "existing_unchanged": [], "enforced": False}
    baseline = requested_change.get("source_baseline")
    if not isinstance(baseline, dict):
        return {"status": "legacy_baseline_unavailable", "existing_modified": [],
                "existing_unchanged": [], "enforced": False}
    sources = baseline.get("sources")
    if not isinstance(sources, dict):
        sources = {}
    enforce = bool(baseline.get("strict") and baseline.get("complete") and sources)
    modified, unchanged = [], []
    try:
        for name, old_hash in sources.items():
            if not isinstance(name, str) or not isinstance(old_hash, str):
                continue
            path = workspace.path(name)
            if not path.is_file() or _digest(path) != old_hash:
                modified.append(name)
            else:
                unchanged.append(name)
    except (OSError, ValueError):
        # Filesystem errors are not proof of a successful change.
        return {"status": "comparison_unavailable", "existing_modified": [],
                "existing_unchanged": [], "enforced": False,
                "reason": "Existing project files could not be compared safely."}
    return {
        "status": ("existing_source_modified" if modified else
                   "existing_source_unchanged" if enforce else "not_enforced"),
        "existing_modified": modified[:50],
        "existing_unchanged": unchanged[:50],
        "enforced": enforce, "tracked_existing": len(sources),
        "coverage": baseline.get("reason", "unknown"),
        "note": ("A changed or deleted pre-existing source file was observed."
                 if modified else "Creating new files alone does not satisfy an explicit fix/update request."),
    }
