#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/gateway"
if [[ ! -f .owner/wrangler.json ]]; then
  echo "Missing gateway/.owner/wrangler.json. Run this from your existing configured SPARKLE-CODER repository."
  exit 1
fi
echo "Installing the locked gateway dependencies..."
npm ci
node "$ROOT/scripts/build-gateway-ui.mjs"
echo "Running gateway tests..."
npm test
echo "Deploying SPARKLE CODER web/PWA..."
python3 - <<'PY'
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

sys.path.insert(0,str(Path.cwd().parent/'scripts'))
from setup_cloud import ROOT, OWNER, save, run_wrangler, deploy_worker, check_migrations, apply_migrations, database_rows

config=json.loads((OWNER/'wrangler.json').read_text())
binding=config['d1_databases'][0]
if not binding.get('database_id') or binding['database_id']=='REPLACE_AFTER_DATABASE_CREATE':
    raise SystemExit('Owner database is not configured. Finish python scripts/setup_cloud.py first.')
# A saved owner config can contain absolute paths from a previous checkout.
# Keep its Worker/database identity and payment settings; publish this code.
config['main']=str(ROOT/'gateway/src/worker.mjs')
config['assets']['directory']=str(ROOT/'gateway/public')
config['assets']['html_handling']='none'
binding['migrations_dir']=str(ROOT/'gateway/migrations')

# Temporary trycloudflare URLs can rotate independently of Worker deploys. Before
# publishing, prefer the newest authenticated healthy tunnel so the new Worker is
# never knowingly deployed with a stale ENGINE_ORIGIN.
engine_path=OWNER/'engine.json';tunnel_log=OWNER/'engine-tunnel.log'
engine=None;selected_engine_origin=None
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Engine health redirected.')
def engine_healthy(origin,secret):
    if not origin or not isinstance(secret,str) or len(secret)<43:return False
    try:
        request=urllib.request.Request(origin.rstrip('/')+'/healthz',headers={'X-Sparkle-Relay':secret})
        with urllib.request.build_opener(NoRedirect).open(request,timeout=12) as response:
            value=json.loads(response.read(8192))
        return value.get('ok') is True and value.get('service')=='sparkle-hosted-engine' and value.get('version')=='0.8.0'
    except Exception:return False
if engine_path.exists():
    engine=json.loads(engine_path.read_text())
    secret=engine.get('relay_secret','')
    candidate=None
    if tunnel_log.exists():
        with tunnel_log.open('rb') as stream:
            stream.seek(max(0,tunnel_log.stat().st_size-262144))
            matches=re.findall(rb'https://[a-z0-9-]+\.trycloudflare\.com\b',stream.read())
        if matches:candidate=matches[-1].decode()
    configured=config.get('vars',{}).get('ENGINE_ORIGIN')
    if candidate and engine_healthy(candidate,secret):selected_engine_origin=candidate
    elif configured and engine_healthy(configured,secret):selected_engine_origin=configured
    if selected_engine_origin:
        config.setdefault('vars',{})['ENGINE_ORIGIN']=selected_engine_origin
    else:
        print('Warning: no healthy hosted-engine tunnel was confirmed before deploy. The recovery timer will keep checking.',flush=True)
save(OWNER/'wrangler.json',config)
command=[shutil.which('npx') or 'npx','--no-install','wrangler']
# A Worker publish does not migrate D1. Always apply and verify pending schema
# migrations BEFORE shipping UI options that depend on the new database rules.
# This is safe to rerun: Wrangler records each applied migration in D1 history.
# On any migration failure, abort deployment without changing account balances.
print('Verifying remote Cloudflare D1 schema before Worker deployment...',flush=True)
check_migrations(ROOT/'gateway/migrations')
run=lambda *args,**kwargs:run_wrangler(command,*args,**kwargs)
apply_migrations(run,binding['database_name'])
schema=database_rows(run,binding['database_name'],
                     "SELECT sql FROM sqlite_master WHERE type='table' AND name='payments_v2'")
if len(schema)!=1:
    raise SystemExit('Remote payments table is missing. Stop deployment and inspect D1 migration history.')
payment_sql=re.sub(r'\\s+',' ',schema[0]['sql']).lower()
if not all(part in payment_sql for part in ('credits >= 1000000','credits <= 100000000',
                                             'credits % 1000000 = 0','amount_paise <= 150000')):
    raise SystemExit('Remote D1 still uses 1M-only payment limits. Stop deployment and repair the schema safely.')
print('Remote D1 accepts whole-million packages from 1M to 100M.',flush=True)
url=deploy_worker(lambda *args,**kwargs:run_wrangler(command,*args,**kwargs),config['name'])
save(OWNER/'deployment.json',{'gateway_url':url,'admin_url':url+'/admin'})

# Wrangler may return the same Worker name under a different workers.dev account
# subdomain. Synchronize only that safe same-name change, then restart the hosted
# engine so its model gateway URL changes immediately instead of a minute later.
gateway_changed=False
if engine is not None:
    worker=config.get('name','')
    def same_worker(value):
        try:host=(urlsplit(value).hostname or '').lower()
        except Exception:return False
        return bool(worker and re.fullmatch(re.escape(worker)+r'\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.workers\.dev',host))
    old_gateway=engine.get('gateway_url','')
    if old_gateway!=url:
        if not same_worker(old_gateway) or not same_worker(url):
            raise SystemExit('Deployment URL changed to a different Worker name. Hosted-engine pairing was not changed.')
        engine={**engine,'gateway_url':url};save(engine_path,engine);gateway_changed=True
    if gateway_changed and shutil.which('systemctl') and os.name!='nt':
        service_env={**os.environ,'XDG_RUNTIME_DIR':f'/run/user/{os.getuid()}',
                     'DBUS_SESSION_BUS_ADDRESS':f'unix:path=/run/user/{os.getuid()}/bus'}
        subprocess.run(['systemctl','--user','restart','sparkle-hosted-engine.service'],env=service_env,check=True,timeout=30)
        for _ in range(30):
            if engine_healthy('http://127.0.0.1:8788',engine.get('relay_secret','')):break
            time.sleep(1)
        else:raise SystemExit('Worker deployed, but the hosted engine did not restart with the new gateway URL.')
if engine is not None and selected_engine_origin:
    payload=json.dumps({'origin':selected_engine_origin}).encode()
    request=urllib.request.Request(url+'/api/internal/engine-origin',data=payload,method='POST',
        headers={'Content-Type':'application/json','X-Sparkle-Relay':engine.get('relay_secret',''),
                 'User-Agent':'SPARKLE-CODER/0.8.0','Accept':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=20) as response:
            published=json.loads(response.read(8192))
    except Exception as error:
        raise SystemExit('Worker deployed, but the runtime engine origin could not be synchronized: '+str(error)) from error
    if published.get('ok') is not True or published.get('origin')!=selected_engine_origin:
        raise SystemExit('Worker deployed, but it did not confirm the runtime engine origin.')
print('\nPublished: '+url+'\nAdmin: '+url+'/admin',flush=True)
try:
    request=urllib.request.Request(url+'/healthz',headers={
        'User-Agent':'SPARKLE-CODER/0.8.0','Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=30) as response:
        health=json.loads(response.read())
    if health.get('version')!='0.8.0' or health.get('ok') is not True:
        raise ValueError('The expected release was not returned by /healthz.')
except Exception as error:
    raise SystemExit('Deployment completed, but the live health check failed: '+str(error)+
                     '\nOpen the printed URL and check the deployment before inviting members.') from error
print('Live release 0.8.0 verified. Reload the app and admin panel to receive the update.')
if health.get('engine_configured') and engine is not None and selected_engine_origin and engine_healthy(selected_engine_origin,engine.get('relay_secret','')):
    save(OWNER/'engine-deployment.json',{'gateway_url':url,'engine_origin':selected_engine_origin,'deployed':True,'health_verified':True})
    print('Cloud engine pairing verified for this deployment.')
elif not health.get('engine_configured'):
    print('Full cloud projects need an owner-hosted engine. Follow HOSTED_ENGINE.md to connect it.')
else:
    print('Warning: Worker is deployed, but the hosted engine tunnel still needs recovery.',flush=True)
PY
