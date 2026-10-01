"""Optional OpenAI-compatible vision review for rendered static-site screenshots."""
import base64
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

MAX_IMAGE=5_000_000

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

_OPENER=urllib.request.build_opener(_NoRedirect())

def configuration():
    base=os.environ.get('SPARKLE_VISION_BASE_URL','').rstrip('/')
    model=os.environ.get('SPARKLE_VISION_MODEL','').strip()
    key=os.environ.get('SPARKLE_VISION_API_KEY','').strip()
    if not (base and model and key): return {'available':False,'reason':'Vision reviewer is not configured on this SPARKLE host.'}
    parsed=urlsplit(base)
    local=parsed.hostname in ('127.0.0.1','localhost','::1')
    if parsed.scheme not in ('https','http') or not parsed.hostname or (parsed.scheme!='https' and not local) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return {'available':False,'reason':'Vision reviewer endpoint configuration is invalid.'}
    return {'available':True,'base_url':base,'model':model,'api_key':key}

def public_configuration():
    value=configuration();return {'available':value.get('available',False),'model':value.get('model','') if value.get('available') else '','reason':value.get('reason','')}

def _data_url(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('Rendered screenshot is unavailable.')
    data=path.read_bytes()
    if len(data)>MAX_IMAGE: raise ValueError('Rendered screenshot is too large for visual review.')
    if data[:8]!=b'\x89PNG\r\n\x1a\n': raise ValueError('Visual review only accepts rendered PNG screenshots.')
    return 'data:image/png;base64,'+base64.b64encode(data).decode('ascii')

def _parse_json(text):
    text=str(text or '').strip()
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I|re.S)
    value=json.loads(text)
    if not isinstance(value,dict) or not isinstance(value.get('findings',[]),list): raise ValueError('Vision reviewer returned an invalid result.')
    findings=[]
    for item in value.get('findings',[])[:12]:
        if not isinstance(item,dict): continue
        severity=str(item.get('severity','medium')).lower()
        if severity not in ('high','medium','low'): severity='medium'
        findings.append({'severity':severity,'category':str(item.get('category','visual'))[:80],
                         'message':str(item.get('message',''))[:500],'suggestion':str(item.get('suggestion',''))[:500]})
    return {'summary':str(value.get('summary',''))[:800],'findings':findings}

def review_rendered_page(render_paths, task='', skills=()):
    cfg=configuration()
    if not cfg.get('available'): return cfg
    images=[_data_url(path) for path in list(render_paths)[:2]]
    if not images:return {'available':False,'reason':'No rendered screenshots were available for vision review.'}
    prompt=('Review these desktop/mobile screenshots of a website as a senior web art director. Focus only on visible evidence: hierarchy, typography, spacing, image composition, contrast, responsive composition, CTA clarity, and generic-template feel. '
            'Do not invent hidden behavior. Return JSON only: {"summary":"...","findings":[{"severity":"high|medium|low","category":"...","message":"...","suggestion":"..."}]}. '
            'Keep at most 8 findings. Task: '+str(task)[:1200]+' Selected skills: '+', '.join(list(skills)[:8]))
    content=[{'type':'text','text':prompt}]+[{'type':'image_url','image_url':{'url':image}} for image in images]
    body=json.dumps({'model':cfg['model'],'messages':[{'role':'user','content':content}],'max_tokens':1200,'temperature':0.2}).encode()
    request=urllib.request.Request(cfg['base_url']+'/chat/completions',data=body,headers={'Authorization':'Bearer '+cfg['api_key'],'Content-Type':'application/json','Accept':'application/json'},method='POST')
    try:
        with _OPENER.open(request,timeout=45) as response: raw=response.read(2_000_001)
    except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError,OSError) as exc: return {'available':True,'ok':False,'error':'Vision reviewer request failed or timed out.'}
    if len(raw)>2_000_000:return {'available':True,'ok':False,'error':'Vision reviewer response was too large.'}
    try:
        payload=json.loads(raw);text=payload['choices'][0]['message']['content'];result=_parse_json(text)
    except (ValueError,KeyError,IndexError,TypeError,json.JSONDecodeError): return {'available':True,'ok':False,'error':'Vision reviewer returned an unreadable response.'}
    return {'available':True,'ok':True,'model':cfg['model'],**result}
