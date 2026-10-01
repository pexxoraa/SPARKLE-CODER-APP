"""Deterministic, low-token skill routing."""
import re
from .registry import builtin_registry
_WEB=re.compile(r"\b(?:website|web\s?page|landing\s?page|homepage|portfolio|html|css|frontend)\b",re.I)
_STATIC=re.compile(r"\b(?:static|landing\s?page|website|homepage|portfolio)\b",re.I)
_CREATIVE=re.compile(r"\b(?:studio|agency|portfolio|brand|creative|photograph|fashion|wedding|restaurant|luxury|artist)\w*\b",re.I)
_PHOTO=re.compile(r"\b(?:photo(?:graphy|grapher|studio)?|photographer|portrait|wedding|camera|gallery)\b",re.I)

def select_skills(goal, *, task_profile="standard", limit=6):
    text=" ".join(str(goal or "").split()); chosen=[]
    def add(name):
        if name in builtin_registry() and name not in chosen: chosen.append(name)
    if task_profile=="simple_web" or _WEB.search(text) or _STATIC.search(text):
        add("static_web")
        if _CREATIVE.search(text) or _PHOTO.search(text): add("visual_design")
        if _PHOTO.search(text): add("photography_portfolio")
        add("frontend_quality_baseline"); add("responsive_web"); add("visual_qa")
    return chosen[:max(0,limit)]
