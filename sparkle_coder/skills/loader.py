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

def render_skills(skill_ids, char_budget=16000, workspace=None):
    """Render every selected skill within one bounded budget; never silently drop tail skills."""
    ids=list(dict.fromkeys(skill_ids or []))
    if not ids or char_budget<=0:return ""
    loaded=[]
    for skill_id in ids:
        text=load_skill(skill_id,workspace)
        header=f"### SKILL: {skill_id}\n"
        loaded.append((skill_id,header,text))
    header_cost=sum(len(header)+2 for _,header,_ in loaded)
    body_budget=max(0,char_budget-header_cost)
    share=(body_budget//len(loaded)) if loaded else 0
    chunks=[];used=0
    for _,header,text in loaded:
        body=text[:share]
        chunk=header+body
        remaining=char_budget-used
        if remaining<=len(header):break
        if len(chunk)>remaining: chunk=header+body[:max(0,remaining-len(header))]
        chunks.append(chunk);used+=len(chunk)+2
    return "\n\n".join(chunks)
