"""Recover the existing owner pilot tunnel; run once per minute with a user timer.

No credentials are printed, no security settings are changed and no billing state
is modified. This repairs an expired temporary tunnel, not host downtime. Use a
named tunnel or stable HTTPS origin for a continuously available deployment.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import setup_hosted_engine as setup


def latest_origin(log):
    # Only URLs emitted by the owner-managed cloudflared log are considered.
    matches=re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com\b',log)
    return matches[-1] if matches else None


def healthy(origin,secret):
    if not origin:return False
    try:setup.check_engine(origin,secret);return True
    except (OSError,ValueError):return False


def recover():
    owner=setup.OWNER;engine=setup.read_config();secret=engine['relay_secret']
    status_path=owner/'tunnel-recovery.json'
    state=json.loads(status_path.read_text()) if status_path.exists() else {}
    stamp=time.time()
    def finish(status,**details):
        state.update(status=status,checked_at=stamp,**details);setup.save(status_path,state)
        print('SPARKLE tunnel: '+status,flush=True)
        return state
    # A stopped local engine cannot be repaired by repeatedly replacing tunnels.
    if not healthy('http://127.0.0.1:8788',secret):
        return finish('local engine unavailable')
    config=json.loads((owner/'wrangler.json').read_text())
    try:engine,gateway_changed=setup.sync_gateway_pairing(engine,config)
    except (OSError,ValueError,KeyError):
        return finish('gateway pairing mismatch; owner configuration needs attention')
    if gateway_changed:state['engine_restart_needed']=True
    if state.get('engine_restart_needed'):
        env={**os.environ,'XDG_RUNTIME_DIR':f'/run/user/{os.getuid()}',
             'DBUS_SESSION_BUS_ADDRESS':f'unix:path=/run/user/{os.getuid()}/bus'}
        try:
            subprocess.run(['systemctl','--user','restart','sparkle-hosted-engine.service'],
                           env=env,check=True,timeout=30)
        except (OSError,subprocess.SubprocessError):
            return finish('gateway updated; hosted engine restart failed',engine_restart_needed=True)
        for _ in range(30):
            if healthy('http://127.0.0.1:8788',secret):break
            time.sleep(1)
        else:return finish('gateway updated; hosted engine restart pending',engine_restart_needed=True)
        state['engine_restart_needed']=False;setup.save(status_path,state)
    log_path=owner/'engine-tunnel.log'
    if not log_path.exists():return finish('tunnel log unavailable')
    with log_path.open('rb') as stream:
        stream.seek(max(0,log_path.stat().st_size-262144))
        log=stream.read().decode(errors='replace')
    candidate=latest_origin(log)
    # Expired sessions can emit enough retries to push the URL out of the tail.
    if not candidate:
        with log_path.open() as stream:
            for line in stream:
                found=latest_origin(line)
                if found:candidate=found
    receipt_path=owner/'engine-deployment.json'
    receipt=json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    current=receipt.get('engine_origin') if receipt.get('deployed') is True else config.get('vars',{}).get('ENGINE_ORIGIN')
    current_ok=current and healthy(current,secret)
    if current_ok:
        return finish('healthy',failures=0)
    target=candidate if candidate and healthy(candidate,secret) else None
    if target:
        if stamp-state.get('last_connect',0)<10:return finish('waiting before reconnect')
        state['last_connect']=stamp;setup.save(status_path,state)
        try:setup.publish_origin(target)
        except (OSError,ValueError,urllib.error.URLError):
            return finish('runtime publish failed; retrying')
        (owner/'pilot-origin.txt').write_text(target);(owner/'pilot-origin.txt').chmod(0o600)
        return finish('reconnected',failures=0)
    failures=state.get('failures',0)+1
    if failures<2 or stamp-state.get('last_restart',0)<60:
        return finish('waiting for tunnel recovery',failures=failures)
    # Only restart the named service installed for this app. Keep unrelated tunnels.
    env={**os.environ,'XDG_RUNTIME_DIR':f'/run/user/{os.getuid()}',
         'DBUS_SESSION_BUS_ADDRESS':f'unix:path=/run/user/{os.getuid()}/bus'}
    subprocess.run(['systemctl','--user','restart','sparkle-engine-tunnel.service'],
                   env=env,check=True,timeout=30)
    return finish('restarting expired tunnel',failures=0,last_restart=stamp)


def main():
    # A timer and a manual recovery must not race two Worker deployments.
    setup.OWNER.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(setup.OWNER/'tunnel-recovery.lock',os.O_WRONLY|os.O_CREAT,0o600)
    with os.fdopen(fd,'w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        recover()


if __name__=='__main__':main()
