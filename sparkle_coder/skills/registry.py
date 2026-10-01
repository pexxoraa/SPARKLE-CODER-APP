"""Built-in skill metadata. Bodies stay in small markdown files and load only when selected."""

SKILL_VERSION = 3

_BUILTINS = {
    "static_web": {"file": "static_web.md", "max_chars": 2200, "priority": 90},
    "visual_design": {"file": "visual_design.md", "max_chars": 2600, "priority": 100},
    "photography_portfolio": {"file": "photography_portfolio.md", "max_chars": 2600, "priority": 120},
    "responsive_web": {"file": "responsive_web.md", "max_chars": 1800, "priority": 80},
    "frontend_quality_baseline": {"file": "frontend_quality_baseline.md", "max_chars": 2200, "priority": 95},
    "visual_qa": {"file": "visual_qa.md", "max_chars": 1800, "priority": 85},
    "asset_sourcing": {"file": "asset_sourcing.md", "max_chars": 2400, "priority": 110},
    "typography_image_strategy": {"file": "typography_image_strategy.md", "max_chars": 2200, "priority": 105},
    "saas_landing": {"file": "saas_landing.md", "max_chars": 2200, "priority": 115},
    "restaurant_hospitality": {"file": "restaurant_hospitality.md", "max_chars": 2200, "priority": 115},
    "ecommerce_storefront": {"file": "ecommerce_storefront.md", "max_chars": 2200, "priority": 115},
    "agency_portfolio": {"file": "agency_portfolio.md", "max_chars": 2200, "priority": 115},
    "real_estate": {"file": "real_estate.md", "max_chars": 2200, "priority": 115},
    "personal_portfolio": {"file": "personal_portfolio.md", "max_chars": 2200, "priority": 115},
}

def builtin_registry():
    return {name: dict(meta, id=name, source="builtin") for name, meta in _BUILTINS.items()}
