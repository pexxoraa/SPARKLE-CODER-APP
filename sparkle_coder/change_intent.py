"""Identify explicit requests to modify project files, not explanatory questions."""
import re

_CHANGE = re.compile(
    r"\b(?:fix|repair|patch|refactor|implement|add|remove|delete|rename|update|"
    r"modify|change|edit|replace|redesign|improve|build|create|make|correct|"
    r"integrate|upgrade|rework|rewrite)\b", re.I)
_EXPLANATION = re.compile(
    r"^\s*(?:how\s+(?:do|can|would|should|to)\b|what\b|why\b|"
    r"explain\b|describe\b|tell\s+me\b|"
    r"can\s+you\s+(?:explain|describe|show|tell)\b|"
    r"is\s+it\b|do\s+you\b)", re.I)
_QUESTION_CHANGE = re.compile(r"\b(?:please|can\s+you|could\s+you)\s+(?:also\s+)?(?:fix|change|add|edit|implement|update|remove|modify|build|create|make)\b", re.I)


def requests_code_change(goal):
    text = str(goal or "").strip()
    if not text or not _CHANGE.search(text):
        return False
    if _EXPLANATION.search(text) and not _QUESTION_CHANGE.search(text):
        return False
    return True
