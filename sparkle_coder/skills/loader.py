"""Bounded loading for task skills."""
from importlib.resources import files
from .registry import builtin_registry

def load_skill(skill_id, workspace=None):
    meta=builtin_registry().get(skill_id)
    if meta:
        text=(files("sparkle_coder.skills.builtin")/meta["file"]).read_text(encoding="utf-8").strip()
        return text[:meta["max_chars"]]
    if workspace is not None:
        from .store import custom_skill
        custom=custom_skill(workspace,skill_id)
        if custom:return custom["body"][:4000]
    raise KeyError(skill_id)

def render_skills(skill_ids, char_budget=9000, workspace=None):
    chunks=[]; used=0
    for skill_id in skill_ids:
        text=load_skill(skill_id,workspace)
        chunk=f"### SKILL: {skill_id}\n{text}"
        if chunks and used+len(chunk)>char_budget: break
        chunks.append(chunk); used+=len(chunk)
    return "\n\n".join(chunks)
