"""Built-in skill metadata. Bodies stay in small markdown files and load only when selected."""

SKILL_VERSION = 5

_BUILTINS = {
    "static_web": {"file": "static_web.md", "max_chars": 2200, "priority": 90},
    "visual_design": {"file": "visual_design.md", "max_chars": 2600, "priority": 100},
    "photography_portfolio": {"file": "photography_portfolio.md", "max_chars": 3200, "priority": 140},
    "responsive_web": {"file": "responsive_web.md", "max_chars": 1800, "priority": 80},
    "frontend_quality_baseline": {"file": "frontend_quality_baseline.md", "max_chars": 2200, "priority": 95},
    "visual_qa": {"file": "visual_qa.md", "max_chars": 3000, "priority": 135},
    "asset_sourcing": {"file": "asset_sourcing.md", "max_chars": 2400, "priority": 120},
    "typography_image_strategy": {"file": "typography_image_strategy.md", "max_chars": 2200, "priority": 92},
    "saas_landing": {"file": "saas_landing.md", "max_chars": 2400, "priority": 115},
    "restaurant_hospitality": {"file": "restaurant_hospitality.md", "max_chars": 2400, "priority": 115},
    "ecommerce_storefront": {"file": "ecommerce_storefront.md", "max_chars": 2400, "priority": 115},
    "agency_portfolio": {"file": "agency_portfolio.md", "max_chars": 2400, "priority": 115},
    "real_estate": {"file": "real_estate.md", "max_chars": 2400, "priority": 115},
    "personal_portfolio": {"file": "personal_portfolio.md", "max_chars": 2400, "priority": 115},
    "composition_mastery": {"file": "composition_mastery.md", "max_chars": 3000, "priority": 132},
    "typography_mastery": {"file": "typography_mastery.md", "max_chars": 2800, "priority": 130},
    "image_art_direction": {"file": "image_art_direction.md", "max_chars": 2800, "priority": 131},
    "portfolio_curation": {"file": "portfolio_curation.md", "max_chars": 2600, "priority": 128},
    "content_integrity": {"file": "content_integrity.md", "max_chars": 2600, "priority": 122},
    "conversion_journey": {"file": "conversion_journey.md", "max_chars": 2400, "priority": 112},
    "accessibility_mastery": {"file": "accessibility_mastery.md", "max_chars": 2600, "priority": 108},
    "interaction_polish": {"file": "interaction_polish.md", "max_chars": 2200, "priority": 88},
    "information_architecture": {"file": "information_architecture.md", "max_chars": 2400, "priority": 110},
    "forms_booking": {"file": "forms_booking.md", "max_chars": 2400, "priority": 106},
    "performance_web": {"file": "performance_web.md", "max_chars": 2200, "priority": 98},
    "luxury_branding": {"file": "luxury_branding.md", "max_chars": 2400, "priority": 116},
    "debugging_mastery": {"file": "debugging_mastery.md", "max_chars": 2600, "priority": 135},
    "testing_mastery": {"file": "testing_mastery.md", "max_chars": 2600, "priority": 125},
    "python_mastery": {"file": "python_mastery.md", "max_chars": 2600, "priority": 120},
    "javascript_typescript_mastery": {"file": "javascript_typescript_mastery.md", "max_chars": 2600, "priority": 120},
    "backend_api_mastery": {"file": "backend_api_mastery.md", "max_chars": 2800, "priority": 125},
    "database_mastery": {"file": "database_mastery.md", "max_chars": 2600, "priority": 120},
    "security_mastery": {"file": "security_mastery.md", "max_chars": 2600, "priority": 128},
    "performance_engineering": {"file": "performance_engineering.md", "max_chars": 2400, "priority": 118},
    "refactoring_mastery": {"file": "refactoring_mastery.md", "max_chars": 2400, "priority": 116},
    "deployment_mastery": {"file": "deployment_mastery.md", "max_chars": 2600, "priority": 122},
    "frontend_architecture": {"file": "frontend_architecture.md", "max_chars": 2600, "priority": 118},
    "code_review_mastery": {"file": "code_review_mastery.md", "max_chars": 2600, "priority": 124},
}

def builtin_registry():
    return {name: dict(meta, id=name, source="builtin") for name, meta in _BUILTINS.items()}
