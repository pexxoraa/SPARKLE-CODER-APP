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
from pathlib import Path
import shutil
import sys
import urllib.request

sys.path.insert(0,str(Path.cwd().parent/'scripts'))
from setup_cloud import ROOT, OWNER, save, run_wrangler, deploy_worker

config=json.loads((OWNER/'wrangler.json').read_text())
binding=config['d1_databases'][0]
if not binding.get('database_id') or binding['database_id']=='REPLACE_AFTER_DATABASE_CREATE':
    raise SystemExit('Owner database is not configured. Finish python scripts/setup_cloud.py first.')
# A saved owner config can contain absolute paths from a previous checkout.
# Keep its Worker/database identity and payment settings; publish this code.
config['main']=str(ROOT/'gateway/src/worker.mjs')
config['assets']['directory']=str(ROOT/'gateway/public')
binding['migrations_dir']=str(ROOT/'gateway/migrations')
save(OWNER/'wrangler.json',config)
command=[shutil.which('npx') or 'npx','--no-install','wrangler']
url=deploy_worker(lambda *args,**kwargs:run_wrangler(command,*args,**kwargs),config['name'])
save(OWNER/'deployment.json',{'gateway_url':url,'admin_url':url+'/admin'})
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
if not health.get('engine_configured'):
    print('Full cloud projects need an owner-hosted engine. Follow HOSTED_ENGINE.md to connect it.')
PY
