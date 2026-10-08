"""Read-only engineering-domain detection and capability/verification planning.

Detection is evidence, not execution. Neither a filename, installed executable,
selected skill nor discovered command proves that a project works.
"""
from fnmatch import fnmatch
from pathlib import PurePosixPath
import re
import shutil

from .checks import discover_checks, package_manager


# Every domain has the same structure and acceptance standard. No web-first fallback.
# Signature globs are deliberately specific: package.json and *.py alone do not
# imply a frontend or AI product.
DOMAINS = (
    ("web_frontend", "Web frontend", r"front[- ]end|web\s?site|web\s?page|landing\s?page|browser\s+ui|react(?!\s+native)|svelte|vue\b|html\s*(?:and|/)\s*css",
     ("index.html", "*.jsx", "*.tsx", "vite.config.*", "next.config.*"),
     ("frontend_architecture", "accessibility_mastery"),
     "Test interactions, keyboard access, responsive layouts and production build."),
    ("backend_apis", "Backend and APIs", r"back[- ]end|rest\s+api|graphql|fastapi|http\s+api|webhook|server[- ]side|api\s+endpoint",
     ("*/routes/*", "*/controllers/*", "app/api/*", "openapi.yaml", "openapi.json"),
     ("backend_api_mastery", "testing_mastery"),
     "Test endpoint contracts, authentication, error paths and persistence."),
    ("mobile_apps", "Mobile applications", r"mobile\s+app|android|ios\s+app|iphone\s+app|flutter|react\s+native|swiftui|jetpack\s+compose",
     ("pubspec.yaml", "*/AndroidManifest.xml", "android/*", "ios/Runner/*", "*.xcodeproj/project.pbxproj"),
     ("mobile_app_mastery", "testing_mastery"),
     "Test lifecycle, permissions, offline transitions and target-device behavior."),
    ("desktop_apps", "Desktop applications", r"desktop\s+(?:app|application)|electron|tauri|windows\s+app|macos\s+app|linux\s+desktop",
     ("src-tauri/tauri.conf.json", "electron-builder.yml", "electron/main.*"),
     ("desktop_app_mastery", "testing_mastery"),
     "Test native startup, filesystem safety, packaging and update/data preservation."),
    ("game_development", "Game development", r"game\s+develop|video\s+game|gameplay|unity|unreal|godot|game\s+engine",
     ("project.godot", "*.unity", "*.uproject", "*.godot", "Assets/*.unity"),
     ("game_simulation", "testing_mastery"),
     "Test gameplay state, frame behavior, assets and target-platform builds."),
    ("ai_ml", "AI and machine learning", r"machine\s+learning|ai\s+(?:model|agent)|llm|neural\s+network|model\s+training|computer\s+vision|pytorch|tensorflow|rag\b",
     ("*.ipynb", "model/config.json", "training/train.py", "mlflow.yaml"),
     ("ml_engineering", "ai_evaluation"),
     "Test reproducible inference/training, data splits, evaluation and failure cases."),
    ("data_engineering", "Data engineering", r"data\s+(?:pipeline|engineering|warehouse|lake)|etl\b|elt\b|airflow|spark\s+job|dbt\b",
     ("dbt_project.yml", "dags/*.py", "airflow.cfg", "spark-submit.sh"),
     ("data_engineering", "testing_mastery"),
     "Test schema contracts, idempotency, late data and reconciliation."),
    ("database_engineering", "Database engineering", r"database\s+(?:engineering|schema|migration)|sql\s+(?:query|database)|postgres|sqlite|mysql|index\s+optimization|migration",
     ("migrations/*.sql", "prisma/schema.prisma", "schema.sql", "alembic.ini"),
     ("database_mastery", "testing_mastery"),
     "Test migrations, rollback strategy, integrity and representative query plans."),
    ("cloud_devops", "Cloud and DevOps", r"devops|ci/cd|kubernetes|terraform|cloud\s+(?:infra|architecture)|deploy(?:ment)?|docker|cloudflare|aws\s+lambda",
     ("Dockerfile", "docker-compose.yml", "compose.yaml", "*.tf", ".github/workflows/*.yml", "k8s/*.yaml"),
     ("devops_ci_cd", "deployment_mastery"),
     "Test isolated builds, deployment/rollback and configuration without exposing secrets."),
    ("systems_programming", "Systems programming", r"systems?\s+programming|operating\s+system|kernel|rust\b|c\+\+|cpp\b|memory\s+safety|low[- ]level",
     ("Cargo.toml", "CMakeLists.txt", "Makefile", "*.rs", "*.cpp"),
     ("systems_programming", "testing_mastery"),
     "Test portability, concurrency, error handling and memory safety."),
    ("embedded_iot", "Embedded systems and IoT", r"embedded|firmware|microcontroller|arduino|esp32|stm32|iot\b|sensor\s+node",
     ("platformio.ini", "idf_component.yml", "*.ino", "zephyr/module.yml"),
     ("embedded_iot", "testing_mastery"),
     "Test board/toolchain compatibility, hardware interfaces, resource limits and safe failure."),
    ("cybersecurity", "Cybersecurity", r"cybersecurity|security\s+audit|penetration\s+test|vulnerability|threat\s+model|owasp|csrf|xss",
     ("security/policy.yml", "semgrep.yml", ".semgrep.yml", "bandit.yaml"),
     ("security_mastery", "testing_mastery"),
     "Test trust boundaries, authorization, abuse cases and evidence-backed remediation."),
    ("distributed_systems", "Distributed systems", r"distributed\s+system|microservices|consensus|event[- ]driven|kafka|service\s+mesh|distributed\s+cache",
     ("proto/*.proto", "*/proto/*.proto", "kafka/*.properties"),
     ("distributed_systems", "reliability_sre"),
     "Test retries, idempotency, ordering, partitions and recovery."),
    ("automation_tools", "Automation and developer tools", r"automation|developer\s+tool|cli\b|command[- ]line\s+tool|sdk\b|code\s+generator|build\s+tool|github\s+action",
     ("action.yml", "action.yaml", "cli/__main__.py", "bin/*", "scripts/automation.*"),
     ("cli_tooling", "testing_mastery"),
     "Test command interfaces, failure codes, reproducibility and integration boundaries."),
)

VERSION = 1
DOMAIN_IDS = tuple(item[0] for item in DOMAINS)
assert len(set(DOMAIN_IDS)) == 14


def detect_domains(workspace, goal="", *, files=None):
    """Return at most three relevant domains with inspectable, bounded signals."""
    names = (workspace.files(limit=2001) if files is None else files)
    names = names[:2000]
    prompt = " ".join(str(goal or "").split())[:12000]
    detected = []
    for identity, title, expression, patterns, skills, acceptance in DOMAINS:
        requested = bool(re.search(r"\b(?:" + expression + r")\b", prompt, re.I))
        matched = [name for name in names if any(
            fnmatch(name, pattern) or fnmatch(PurePosixPath(name).name, pattern)
            for pattern in patterns)]
        if requested or matched:
            detected.append({"id": identity, "name": title,
                             "source": "request" if requested else "project_files",
                             "signals": (["task description"] if requested else []) + matched[:3],
                             "score": (10 if requested else 0) + min(3, len(matched)),
                             "skills": list(skills), "acceptance": acceptance})
    # An explicit user request takes priority. Do not let a mixed repository
    # silently turn a firmware or data task into website development.
    detected.sort(key=lambda entry: (-entry["score"], entry["id"]))
    if any(item["source"] == "request" for item in detected):
        detected = [item for item in detected if item["source"] == "request"]
    return [{key: value for key, value in item.items() if key != "score"}
            for item in detected[:3]]


def detect_toolchains(files, execution="local", *, which=None):
    """Conservative host-PATH discovery; never invokes executables/project code."""
    which = which or shutil.which
    names = set(files[:2000])
    tools = set()
    def exists(pattern):
        return any(fnmatch(name, pattern) or fnmatch(PurePosixPath(name).name, pattern) for name in names)

    if exists("package.json"):
        tools.add("node")
        # Do not inspect arbitrary package scripts or execute package managers.
        tools.add("npm")
    if exists("pyproject.toml") or exists("requirements.txt") or exists("pytest.ini"):
        tools.add("python3")
    if exists("Cargo.toml"):
        tools.add("cargo")
    if exists("go.mod"):
        tools.add("go")
    if exists("pom.xml"):
        tools.update(("java", "mvn"))
    if exists("build.gradle") or exists("build.gradle.kts"):
        tools.update(("java", "gradle"))
    if exists("*.csproj") or exists("*.sln"):
        tools.add("dotnet")
    if exists("CMakeLists.txt"):
        tools.add("cmake")
    if exists("pubspec.yaml"):
        tools.add("flutter")
    if exists("platformio.ini"):
        tools.add("pio")
    if exists("*.tf"):
        tools.add("terraform")
    if exists("Dockerfile") or exists("compose.yaml") or exists("docker-compose.yml"):
        tools.add("docker")
    if exists("project.godot"):
        tools.add("godot")
    return [{"tool": tool, "status": ("container_unchecked" if execution == "docker"
                                     else "found_on_path" if which(tool) else "missing_on_path"),
             "verified": False} for tool in sorted(tools)]


def inspect_engineering(workspace, goal="", execution="local", *, files=None):
    """Planning evidence only. Real verification remains in existing check gates."""
    names = workspace.files(limit=2001) if files is None else files
    domains = detect_domains(workspace, goal, files=names)
    tools = detect_toolchains(names, execution)
    candidates = discover_checks(workspace, execution, files=names)["checks"]
    return {
        "version": VERSION,
        "domains": domains,
        "primary_domain": domains[0]["id"] if domains else None,
        "toolchains": tools,
        "verification_contracts": [
            {"domain": d["id"], "acceptance": d["acceptance"],
             "status": "not_verified_by_inspection"} for d in domains
        ],
        "candidate_checks": candidates[:30],
        "scan_truncated": len(names) > 2000,
        "note": ("Read-only inference. Tool presence does not prove availability in the "
                 "execution environment; discovered commands have NOT been run. "
                 "Use verify and actual target-specific tests for completion."),
    }
