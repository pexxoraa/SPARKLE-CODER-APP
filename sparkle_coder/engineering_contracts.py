"""Domain-neutral, evidence-backed planning and enforceable completion contracts.

Check executions are facts. An agent's claim that a check covers a domain
remains a claim, not proof that the check tests the right behavior.
"""
import re
from .engineering import DOMAIN_IDS, detect_domains, detect_toolchains
from .verification import active_checks

CONTRACT_VERSION = 1
FACETS = ("behavior", "target")
OBLIGATIONS = {
    "web_frontend": ("Test interactions and accessibility", "Test responsive rendering and production assets"),
    "backend_apis": ("Exercise API contracts and authorization failures", "Verify data/service integration"),
    "mobile_apps": ("Test lifecycle, state, offline and permissions", "Build/test on requested device or simulator"),
    "desktop_apps": ("Test desktop behavior and recovery", "Verify native packaging and update/data preservation"),
    "game_development": ("Test gameplay and state transitions", "Run game engine and target-platform checks"),
    "ai_ml": ("Test inference on representative held-out cases", "Verify reproducible runtime or model compatibility"),
    "data_engineering": ("Test transformations and schema constraints", "Test pipeline replay/idempotency"),
    "database_engineering": ("Test constraints and representative queries", "Test isolated migration and recovery"),
    "cloud_devops": ("Test infrastructure config and automation", "Test dry-run/deployment plan and rollback readiness"),
    "systems_programming": ("Test behavior and failure boundaries", "Test target compiler/build and memory safety"),
    "embedded_iot": ("Test firmware safety and failure paths", "Compile for target board and test hardware/simulator interfaces"),
    "cybersecurity": ("Test trust boundaries and abuse cases", "Validate remediation with scoped tests"),
    "distributed_systems": ("Test concurrent operations and message order", "Test partition, retries and recovery integration"),
    "automation_tools": ("Test CLI inputs and exit codes", "Test integration and repeatable execution"),
}
assert tuple(OBLIGATIONS) == DOMAIN_IDS

# A target-specific claim must at least involve a relevant build/test tool.
# Custom project commands are possible through user-required checks. These
# patterns reject generic no-op/assertions but do not claim semantic proof.
TARGET_MARKERS = {
    "web_frontend": r"\b(playwright|puppeteer|chromium|vite|next|npm|pnpm|yarn|bun)\b|builtin:visual-site",
    "backend_apis": r"\b(pytest|unittest|cargo|go|gradle|mvn|dotnet|npm|pnpm|integration)\b",
    # Device enumeration and compiler version checks are NOT mobile target evidence.
    "mobile_apps": r"\bflutter\s+test\s+integration_test(?:\b|/)|\b(?:gradle|gradlew)\s+connectedAndroidTest\b|\bxcodebuild\s+test\b",
    "desktop_apps": r"\b(pyinstaller|tauri|electron|cargo|xcodebuild|dotnet|installer)\b",
    "game_development": r"\b(godot|unity|unreal|ue4|ue5|gametest)\b",
    "ai_ml": r"\b(pytest|unittest|evaluate|mlflow|torch|tensorflow|onnx)\b",
    "data_engineering": r"\b(dbt|airflow|spark|pytest|unittest|dagster)\b",
    "database_engineering": r"\b(alembic|prisma|migrate|sqlite|psql|pytest|unittest)\b",
    "cloud_devops": r"\b(terraform|tofu|kubectl|helm|wrangler|docker|checkov|cfn-lint)\b",
    "systems_programming": r"\b(cargo|rustc|ctest|cmake|gcc|clang|make|valgrind|asan)\b",
    "embedded_iot": r"\b(pio|idf\.py|arduino-cli|west|platformio|qemu)\b",
    "cybersecurity": r"\b(semgrep|bandit|zap|nuclei|trivy|pytest|unittest|audit)\b",
    "distributed_systems": r"\b(docker|pytest|unittest|toxiproxy|kafka|kind|go|cargo)\b",
    "automation_tools": r"\b(pytest|unittest|npm|pnpm|yarn|bun|shellcheck|bats|go|cargo)\b",
}
assert tuple(TARGET_MARKERS) == DOMAIN_IDS

def _target_relevant(domain, check):
    if check.get("required") or check.get("source") == "user":
        return True
    return bool(re.search(TARGET_MARKERS[domain], check.get("command", ""), re.I))



def required_domains(domains, task_profile="standard", task_mode="build"):
    # Existing efficient static-web tasks already use a dedicated visual gate.
    # Repo file heuristics alone must not silently add new hard requirements.
    if task_mode == "ask" or task_profile == "simple_web":
        return []
    return [item["id"] for item in domains if item["source"] == "request"]


def _fresh(state, check_id, fingerprint):
    # A link belongs to one actual execution, not the latest record for the
    # same command. Otherwise a rerun can silently resurrect stale coverage.
    check = (next((item for item in active_checks(state) if item.get("id") == check_id), None)
             if isinstance(check_id, str) else None)
    if not check or not fingerprint or check.get("fingerprint") != fingerprint:
        return None
    if check.get("environment_revision", 0) != state.get("environment_revision", 0):
        return None
    if not check.get("ok") or check.get("denied") or check.get("cancelled"):
        return None
    return check


def evaluate_contract(workspace, state, domains, *, task_profile="standard"):
    must = set(required_domains(domains, task_profile, state.get("task_mode", "build")))
    coverage = state.get("engineering_evidence", {})
    fingerprint = workspace.fingerprint() if coverage and state.get("checks") else None
    contracts = []
    for item in domains:
        identity = item["id"]
        declared = coverage.get(identity, {}) if isinstance(coverage, dict) else {}
        facets = []
        seen = set()
        for facet, requirement in zip(FACETS, OBLIGATIONS[identity]):
            entry = declared.get(facet, {}) if isinstance(declared, dict) else {}
            check_id = entry.get("check_id") if isinstance(entry, dict) else None
            recorded = _fresh(state, check_id, fingerprint)
            valid = bool(recorded and check_id not in seen and
                         (facet != "target" or _target_relevant(identity, recorded)))
            if valid:
                seen.add(check_id)
            facets.append({"id": facet, "requirement": requirement, "check_id": check_id,
                           "status": "check_linked_fresh" if valid else
                                     ("stale_or_failed" if check_id else "missing_evidence")})
        contracts.append({"domain": identity, "required_for_completion": identity in must,
                          "facets": facets, "passed": all(f["status"] == "check_linked_fresh" for f in facets),
                          "semantic_coverage": "agent_asserted_not_independently_audited"})
    return {"version": CONTRACT_VERSION, "contracts": contracts,
            "blocking": [{"domain": c["domain"],
                          "missing": [f["id"] for f in c["facets"] if f["status"] != "check_linked_fresh"]}
                         for c in contracts if c["required_for_completion"] and not c["passed"]],
            "note": "Check records are real; the agent's mapping of a check to a requirement is not independently audited."}


def link_evidence(workspace, state, domain, facet, check_id, reason, *, task_profile="standard"):
    if domain not in DOMAIN_IDS or facet not in FACETS:
        raise ValueError("Choose a known domain and behavior or target facet.")
    prompt = " ".join(state.get("user_requests", [state.get("goal", "")])[-2:])
    selected = detect_domains(workspace, prompt)
    if domain not in {d["id"] for d in selected}:
        raise ValueError("Domain is not selected for this task.")
    reason = " ".join(str(reason or "").split())
    if not 20 <= len(reason) <= 600:
        raise ValueError("Explain in 20–600 characters what the check actually exercises.")
    check = _fresh(state, check_id, workspace.fingerprint())
    if not check:
        raise ValueError("Check is missing, failed, stale, denied, or not executed in this session.")
    if check.get("command", "").strip() in ("true", "echo ok", "echo pass"):
        raise ValueError("An inert command is not valid acceptance evidence.")
    if facet == "target" and not _target_relevant(domain, check):
        raise ValueError("Target evidence must execute a relevant domain build/test tool or a user-required check; generic assertions are not platform verification.")
    evidence = state.get("engineering_evidence", {})
    previous = evidence.get(domain, {}) if isinstance(evidence, dict) else {}
    if not isinstance(previous, dict):
        previous = {}
    if any(f != facet and v.get("check_id") == check_id for f, v in previous.items()
           if isinstance(v, dict)):
        raise ValueError("Behavior and target evidence need separate real checks.")
    if not isinstance(evidence, dict):
        state["engineering_evidence"] = {}
    state.setdefault("engineering_evidence", {}).setdefault(domain, {})[facet] = {
        "check_id": check_id, "reason": reason}
    return evaluate_contract(workspace, state, selected, task_profile=task_profile)


def execution_plan(workspace, goal, execution="local", *, files=None, state=None, task_profile="standard"):
    """Read-only plan, never a capability or test-success claim."""
    names = workspace.files(limit=2001) if files is None else files
    domains = detect_domains(workspace, goal, files=names)
    tools = detect_toolchains(names, execution)
    missing = [t["tool"] for t in tools if t["status"] == "missing_on_path"]
    unchecked = [t["tool"] for t in tools if t["status"] == "container_unchecked"]
    return {"version": CONTRACT_VERSION, "domains": [d["id"] for d in domains],
            "execution": execution, "toolchains": tools,
            "missing_host_tools": missing, "unchecked_container_tools": unchecked,
            "readiness": ("needs_toolchain_setup" if missing else "container_unverified" if unchecked
                          else "not_executed"),
            "steps": [
                {"phase": "inspect", "action": "Map existing files, requirements, architecture and constraints"},
                {"phase": "prepare", "action": "Verify real toolchain/dependency readiness in execution environment"},
                {"phase": "implement", "action": "Make requested tracked code changes, preserving user work"},
                {"phase": "verify", "action": "Execute behavior and target checks; link separate fresh check IDs"},
                {"phase": "report", "action": "Report proven behavior and explicit untested target limitations"},
            ],
            "verification": (evaluate_contract(workspace, state, domains, task_profile=task_profile)
                             if state is not None else None),
            "note": "Read-only plan. Installed executables do not prove build/runtime capability."}
