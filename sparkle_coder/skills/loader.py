"""Bounded loading for task skills."""
from importlib.resources import files
from .registry import builtin_registry

def load_skill(skill_id):
    meta=builtin_registry().get(skill_id)
    if not meta: raise KeyError(skill_id)
    text=(files("sparkle_coder.skills.builtin")/meta["file"]).read_text(encoding="utf-8").strip()
    return text[:meta["max_chars"]]

def render_skills(skill_ids, char_budget=9000):
    chunks=[]; used=0
    for skill_id in skill_ids:
        text=load_skill(skill_id)
        chunk=f"### SKILL: {skill_id}\n{text}"
        if chunks and used+len(chunk)>char_budget: break
        chunks.append(chunk); used+=len(chunk)
    return "\n\n".join(chunks)
