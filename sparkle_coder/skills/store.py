"""Private per-project custom skills, overrides, and aggregate skill outcomes."""
from pathlib import Path
import json
import re
from .registry import builtin_registry
from ..workspace import write_json

STORE_VERSION=1
_ID=re.compile(r'^[a-z][a-z0-9_-]{2,47}$')
_SECRET=re.compile(r'(?i)\b(?:api[_ -]?key|access[_ -]?token|secret|password|authorization|bearer)\b\s*[:=]\s*\S+')

def _store_path(workspace): return workspace.state_dir/'skills.json'
def _metrics_path(workspace): return workspace.state_dir/'skill-metrics.json'

def _default_store(): return {'version':STORE_VERSION,'custom':{},'overrides':{'enabled':[],'disabled':[],'vision_review':False}}

def load_store(workspace):
    path=_store_path(workspace)
    if path.is_symlink(): raise ValueError('Skill settings must not be a symlink.')
    if not path.exists(): return _default_store()
    try: value=json.loads(path.read_text('utf-8'))
    except json.JSONDecodeError as exc: raise ValueError('Skill settings are invalid JSON.') from exc
    if not isinstance(value,dict) or value.get('version')!=STORE_VERSION: raise ValueError('Unsupported skill settings format.')
    base=_default_store();base['custom']=value.get('custom',{}) if isinstance(value.get('custom'),dict) else {}
    raw=value.get('overrides',{}) if isinstance(value.get('overrides'),dict) else {}
    base['overrides']={'enabled':raw.get('enabled',[]) if isinstance(raw.get('enabled'),list) else [],
                       'disabled':raw.get('disabled',[]) if isinstance(raw.get('disabled'),list) else [],
                       'vision_review':raw.get('vision_review') is True}
    return base

def _save(workspace,value): write_json(_store_path(workspace),value)

def save_custom_skill(workspace, skill_id, title, triggers, body):
    skill_id=str(skill_id or '').strip().lower().replace(' ','-')
    if not _ID.fullmatch(skill_id) or skill_id in builtin_registry(): raise ValueError('Custom skill ID must be 3–48 lowercase letters/numbers/-/_ and must not replace a built-in skill.')
    title=' '.join(str(title or '').split());body=str(body or '').strip()
    if not 2<=len(title)<=80: raise ValueError('Custom skill title must contain 2–80 characters.')
    if not 20<=len(body)<=4000: raise ValueError('Custom skill body must contain 20–4000 characters.')
    if _SECRET.search(body): raise ValueError('Do not store credentials or secrets in a skill.')
    if not isinstance(triggers,list) or len(triggers)>12: raise ValueError('Use up to 12 trigger phrases.')
    clean=[]
    for value in triggers:
        value=' '.join(str(value or '').lower().split())
        if not 2<=len(value)<=80: raise ValueError('Each trigger phrase must contain 2–80 characters.')
        if _SECRET.search(value): raise ValueError('Skill triggers cannot contain credentials.')
        if value not in clean: clean.append(value)
    store=load_store(workspace);store['custom'][skill_id]={'id':skill_id,'title':title,'triggers':clean,'body':body,'source':'custom'};_save(workspace,store)
    return store['custom'][skill_id]

def delete_custom_skill(workspace, skill_id):
    store=load_store(workspace)
    if skill_id not in store['custom']: raise ValueError('Custom skill not found.')
    del store['custom'][skill_id]
    for key in ('enabled','disabled'): store['overrides'][key]=[x for x in store['overrides'][key] if x!=skill_id]
    _save(workspace,store);return {'deleted':skill_id}

def set_overrides(workspace, enabled, disabled, vision_review=False):
    store=load_store(workspace);known=set(builtin_registry())|set(store['custom'])
    if not isinstance(enabled,list) or not isinstance(disabled,list): raise ValueError('Skill overrides must be lists.')
    enabled=list(dict.fromkeys(str(x) for x in enabled));disabled=list(dict.fromkeys(str(x) for x in disabled))
    if len(enabled)>8 or len(disabled)>32: raise ValueError('Too many skill overrides.')
    unknown=(set(enabled)|set(disabled))-known
    if unknown: raise ValueError('Unknown skill override: '+', '.join(sorted(unknown)))
    if set(enabled)&set(disabled): raise ValueError('A skill cannot be both forced on and forced off.')
    if type(vision_review) is not bool: raise ValueError('vision_review must be true or false.')
    store['overrides']={'enabled':enabled,'disabled':disabled,'vision_review':vision_review};_save(workspace,store)
    return dict(store['overrides'])

def resolve_project_skills(workspace, goal, automatic, limit=8):
    store=load_store(workspace);over=store['overrides'];chosen=[x for x in automatic if x not in set(over['disabled'])]
    text=' '.join(str(goal or '').lower().split())
    for skill in store['custom'].values():
        if skill['id'] in over['disabled']: continue
        if skill.get('triggers') and any(trigger in text for trigger in skill['triggers']) and skill['id'] not in chosen: chosen.append(skill['id'])
    for skill_id in over['enabled']:
        if skill_id not in chosen: chosen.append(skill_id)
    return chosen[:max(0,min(8,int(limit)))]

def custom_skill(workspace, skill_id): return load_store(workspace)['custom'].get(skill_id)
def overrides(workspace): return dict(load_store(workspace)['overrides'])

def catalog(workspace):
    store=load_store(workspace);metrics=skill_analytics(workspace);result=[]
    for skill_id,meta in builtin_registry().items():
        result.append({'id':skill_id,'title':skill_id.replace('_',' ').title(),'source':'builtin','triggers':[], 'metrics':metrics.get(skill_id,{})})
    for skill in store['custom'].values(): result.append({k:skill[k] for k in ('id','title','source','triggers')}|{'metrics':metrics.get(skill['id'],{})})
    return {'skills':result,'overrides':dict(store['overrides'])}

def record_skill_outcome(workspace, session):
    path=_metrics_path(workspace);value={'version':1,'sessions':{}}
    if path.exists() and not path.is_symlink():
        try:
            loaded=json.loads(path.read_text('utf-8'))
            if isinstance(loaded,dict) and loaded.get('version')==1 and isinstance(loaded.get('sessions'),dict): value=loaded
        except json.JSONDecodeError: pass
    state=session.state;checks=state.get('checks',[])
    visual=[c for c in checks if str(c.get('command','')).startswith('builtin:visual-site ')]
    value['sessions'][session.id]={'skills':list(state.get('skills',[]))[:8],'status':state.get('status',''),
        'tokens':int(state.get('usage',{}).get('prompt_tokens',0))+int(state.get('usage',{}).get('completion_tokens',0)),
        'calls':int(state.get('usage',{}).get('calls',0)),'visual_pass':bool(visual and visual[-1].get('ok')),
        'visual_fail':bool(visual and not visual[-1].get('ok')),'updated':state.get('updated')}
    if len(value['sessions'])>500:
        items=sorted(value['sessions'].items(),key=lambda x:str(x[1].get('updated','')),reverse=True)[:500];value['sessions']=dict(items)
    write_json(path,value)

def skill_analytics(workspace):
    path=_metrics_path(workspace);result={}
    if path.is_symlink() or not path.exists(): return result
    try:value=json.loads(path.read_text('utf-8'))
    except json.JSONDecodeError:return result
    for record in value.get('sessions',{}).values() if isinstance(value,dict) else []:
        for skill_id in record.get('skills',[]):
            row=result.setdefault(skill_id,{'runs':0,'checked':0,'needs_input':0,'tokens':0,'model_calls':0,'visual_passes':0,'visual_failures':0})
            row['runs']+=1;row['checked']+=record.get('status')=='checked';row['needs_input']+=record.get('status')=='needs_input';row['tokens']+=int(record.get('tokens',0));row['model_calls']+=int(record.get('calls',0));row['visual_passes']+=bool(record.get('visual_pass'));row['visual_failures']+=bool(record.get('visual_fail'))
    return result
