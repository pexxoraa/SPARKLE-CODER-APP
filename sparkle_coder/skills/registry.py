"""Built-in skill metadata. Bodies stay in small markdown files and load only when selected."""

SKILL_VERSION = 1

_BUILTINS = {
    "static_web": {"file": "static_web.md", "max_chars": 2200, "priority": 90},
    "visual_design": {"file": "visual_design.md", "max_chars": 2600, "priority": 100},
    "photography_portfolio": {"file": "photography_portfolio.md", "max_chars": 2600, "priority": 120},
    "responsive_web": {"file": "responsive_web.md", "max_chars": 1800, "priority": 80},
    "frontend_quality_baseline": {"file": "frontend_quality_baseline.md", "max_chars": 2200, "priority": 95},
    "visual_qa": {"file": "visual_qa.md", "max_chars": 1800, "priority": 85},
}

def builtin_registry():
    return {name: dict(meta, id=name, source="builtin") for name, meta in _BUILTINS.items()}
