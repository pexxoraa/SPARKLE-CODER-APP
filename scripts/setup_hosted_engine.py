"""Configure an existing owner host and connect it to the existing Worker.

No server is purchased or created. Credentials stay in a private owner file and
are passed to Wrangler over stdin. Browser users never need this script.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.setup_cloud import save, run_wrangler, deploy_worker
from sparkle_coder.web import website_origin
from sparkle_coder.hosted import main as serve_engine

OWNER=ROOT/'gateway/.owner'
ENGINE=OWNER/'engine.json'


def https_origin(value):
    origin=website_origin(value)
    if not origin.startswith('https://'):raise ValueError('Use a public HTTPS origin without a path.')
    return origin


def read_config():
    if ENGINE.is_symlink():raise ValueError('Owner engine configuration must not be a symlink.')
    if not ENGINE.exists():raise ValueError('Run init --gateway YOUR_WORKER_URL first.')
    value=json.loads(ENGINE.read_text())
    value['gateway_url']=https_origin(value['gateway_url'])
    if not isinstance(value.get('relay_secret'),str) or len(value['relay_secret'])<43:
        raise ValueError('The engine configuration has no valid relay secret.')
    if type(value.get('max_running',1)) is not int or not 1<=value.get('max_running',1)<=3:
        raise ValueError('Use 1–3 concurrent runs.')
    return value


def initialize(gateway,max_running=1):
    gateway=https_origin(gateway)
    if ENGINE.exists():
        value=read_config()
        if value['gateway_url']!=gateway:
            raise ValueError('This host is already paired with a different Worker. Keep its owner configuration and account data together.')
    else:
        value={'gateway_url':gateway,'relay_secret':secrets.token_urlsafe(48),'image':'sparkle-coder-tools:local','max_running':max_running}
        save(ENGINE,value)
    print('Private engine configuration ready. The existing relay secret was preserved if present.')
    print('Build the Docker tools image, then run: python3 scripts/setup_hosted_engine.py serve')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('The engine address redirected. Use its final HTTPS origin; the relay secret was not forwarded.')


def check_engine(origin,secret):
    request=urllib.request.Request(origin+'/healthz',headers={'X-Sparkle-Relay':secret})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=20) as response:
        value=json.loads(response.read(8192))
    if value.get('ok') is not True or value.get('service')!='sparkle-hosted-engine' or value.get('version')!='0.8.0':
        raise ValueError('The address did not return the expected authenticated engine health check.')


def connect(origin):
    origin=https_origin(origin);engine=read_config()
    path=OWNER/'wrangler.json'
    if not path.exists():raise ValueError('Keep the existing gateway/.owner/wrangler.json from owner setup. Do not create a new database.')
    config=json.loads(path.read_text())
    deployment=OWNER/'deployment.json'
    if deployment.exists() and https_origin(json.loads(deployment.read_text())['gateway_url'])!=engine['gateway_url']:
        raise ValueError('This owner configuration points to a different Worker than the engine. No cloud changes were made.')
    binding=config['d1_databases'][0]
    if not binding.get('database_id') or binding['database_id']=='REPLACE_AFTER_DATABASE_CREATE':
        raise ValueError('Finish the existing Worker/D1 setup first.')
    # Validate the actual service before modifying any Worker configuration.
    check_engine(origin,engine['relay_secret'])
    subprocess.run(['node',str(ROOT/'scripts/build-gateway-ui.mjs')],cwd=ROOT,check=True)
    subprocess.run(['npm','test'],cwd=ROOT/'gateway',check=True)
    command=[shutil.which('npx') or 'npx','--no-install','wrangler']
    run_wrangler(command,'secret','put','ENGINE_SECRET',input_text=engine['relay_secret'])
    config.setdefault('vars',{})['ENGINE_ORIGIN']=origin
    config['main']=str(ROOT/'gateway/src/worker.mjs')
    config['assets']['directory']=str(ROOT/'gateway/public')
    binding['migrations_dir']=str(ROOT/'gateway/migrations')
    save(path,config)
    url=deploy_worker(lambda *args,**kwargs:run_wrangler(command,*args,**kwargs),config['name'])
    save(OWNER/'deployment.json',{'gateway_url':url,'admin_url':url+'/admin'})
    with urllib.request.urlopen(url+'/healthz',timeout=20) as response:
        health=json.loads(response.read(8192))
    if health.get('version')!='0.8.0' or health.get('engine_configured') is not True:
        raise ValueError('Worker deployed but the engine binding was not confirmed. Keep this configuration and retry connect.')
    print('Full cloud interface deployed: '+url)
    print('Engine health and Worker configuration verified. Open an approved account and run the smoke test in HOSTED_ENGINE.md.')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init',help='Create or reuse a private relay secret')
    init.add_argument('--gateway',required=True);init.add_argument('--max-running',type=int,choices=(1,2,3),default=1)
    start=commands.add_parser('serve',help='Run the engine on this owner host')
    start.add_argument('--port',type=int,default=8788)
    start.add_argument('--state-dir',type=Path,default=ROOT/'HOSTED_DATA')
    connection=commands.add_parser('connect',help='Verify HTTPS engine, then update the existing Worker')
    connection.add_argument('--origin',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='init':initialize(args.gateway,args.max_running)
        elif args.command=='connect':connect(args.origin)
        else:
            value=read_config()
            os.environ.update({'SPARKLE_GATEWAY_URL':value['gateway_url'],'SPARKLE_RUNNER_SECRET':value['relay_secret'],
                               'SPARKLE_RUNNER_IMAGE':value['image'],'SPARKLE_MAX_RUNS':str(value.get('max_running',1))})
            serve_engine(['--port',str(args.port),'--state-dir',str(args.state_dir)])
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        raise SystemExit('Engine setup stopped: '+str(error)) from None


if __name__=='__main__':main()
