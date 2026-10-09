"""Owner-hosted multi-account engine, reachable only through the trusted gateway.

The browser and model gateway remain on Cloudflare. This service reuses the
existing agent, sessions, approvals and file APIs; project commands always run
in Docker, without network access or host credentials.
"""
import argparse
import base64
from collections import deque
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
from urllib.parse import urlsplit

from .provider import NemotronClient
from .storage import resolve_storage
from .web import Handler, website_origin
from .webapp import AppService


class GatewayAccount:
    def __init__(self, url, secret, receipt):
        self.url, self.secret = url, secret
        self.cached = {**receipt, 'enabled': True, 'enrolled': True}


class EngineQueue:
    """Fair, bounded, credit-free admission to shared coding execution slots.

    A queued run has not started model inference. Cancelling it releases its
    reservation immediately. Only admitted runs consume the server's capacity.
    """

    def __init__(self, capacity, waiting_limit=25):
        self.capacity = capacity
        self.waiting_limit = waiting_limit
        self.condition = threading.Condition()
        self.waiting = deque()
        self.running = set()

    def enqueue(self, job):
        with self.condition:
            if len(self.waiting) >= self.waiting_limit:
                raise ValueError('The coding queue is full. Your prompt was not submitted and no model call started. Try later.')
            self.waiting.append(job)
            with job.lock:
                job.current_action = 'Waiting for a coding slot (queue position '+str(len(self.waiting))+') · no credits used'
            self.condition.notify_all()

    def wait(self, job):
        with self.condition:
            while True:
                if job.stop.is_set():
                    self.discard(job)
                    return False
                if self.waiting and self.waiting[0] is job and len(self.running) < self.capacity:
                    self.waiting.popleft()
                    self.running.add(job.id)
                    with job.lock:
                        job.current_action = 'Coding slot ready · starting saved prompt'
                    self.condition.notify_all()
                    return True
                if job in self.waiting:
                    position = self.waiting.index(job) + 1
                    with job.lock:
                        job.current_action = f'Queued for coding (position {position}) · no model calls or credits yet'
                self.condition.wait(0.25)

    def discard(self, job):
        with self.condition:
            try:
                self.waiting.remove(job)
            except ValueError:
                pass
            self.condition.notify_all()

    def release(self, job):
        with self.condition:
            self.running.discard(job.id)
            self.condition.notify_all()


class HostedAppService(AppService):
    def __init__(self, directory, gateway_url, secret, receipt, manager):
        self.tenant_root = Path(directory).resolve()
        if resolve_storage(self.tenant_root) != self.tenant_root:
            raise ValueError('Hosted account storage cannot be relocated.')
        self.gateway_url, self.manager = gateway_url, manager
        self.run_admission = manager.queue
        fresh = not (self.tenant_root/'settings.json').exists()
        self._starting = True
        super().__init__(self.tenant_root, provider_factory=manager.provider_factory)
        self._starting = False
        self.account = GatewayAccount(gateway_url, secret, receipt)
        if fresh:
            self.data['experience']='advanced'
            self.save()
        # Existing settings must never redirect an owner-hosted account elsewhere.
        if self.directory != self.tenant_root:
            raise ValueError('Hosted account storage cannot be relocated.')

    def config(self, workspace=None):
        config = super().config(workspace)
        # Enforce after reading project config; a project cannot relax these caps.
        config.execution = 'docker'
        config.auto_approve = True
        config.docker_network = False
        config.docker_image = self.manager.image
        config.base_url = self.gateway_url + '/v1'
        config.model = 'nvidia/nemotron-3-super-120b-a12b'
        config._runtime_cloud = True
        config._runtime_api_key = self.account.secret if isinstance(self.account,GatewayAccount) else ''
        config.extra_body = {}
        config.request_timeout = min(config.request_timeout,300)
        config.max_tokens = min(config.max_tokens, 8192)
        config.context_chars = min(config.context_chars, 24000)
        standard_caps={'max_steps':24,'max_seconds':900,'max_total_tokens':200000}
        for field, maximum in [*standard_caps.items(),('command_timeout',120)]:
            setattr(config,field,min(getattr(config,field) or maximum,maximum))
        # User-selected smaller caps always stop as requested. Automatic
        # continuation is limited to default managed work segments.
        config._auto_continue_cloud=all(
            getattr(config,field)==maximum and
            (self.data["settings"].get(field) is None or
             self.data["settings"].get(field)>=maximum)
            for field,maximum in standard_caps.items())
        return config

    def public_settings(self):
        result = super().public_settings()
        config = self.config()
        result.update({key:getattr(config,key) for key in ('execution','max_steps','max_seconds','max_total_tokens','command_timeout','max_tokens','context_chars')})
        result.update({'key_configured':True,'key_source':'managed','cloud_gateway_url':self.gateway_url+'/v1'})
        return result

    def add_project(self, name='', path='', purpose=''):
        if not self._starting and path:
            raise ValueError('Create a cloud project, then use Import files or Import folder.')
        if hasattr(self,'data') and len(self.data['projects']) >= 30:
            raise ValueError('This account has reached its 30-project limit.')
        return super().add_project(name,path,purpose)

    def project(self, project_id):
        project = next((p for p in self.data['projects'] if p['id']==project_id),None)
        if not project or not Path(project['path']).resolve().is_relative_to(self.tenant_root/'PROJECTS'):
            raise ValueError('Project not found in this account.')
        return super().project(project_id)

    def configure(self, payload):
        if set(payload)-{'efficiency','max_steps','max_seconds','max_total_tokens','command_timeout','max_tokens','context_chars'}:
            raise ValueError('The owner manages the model connection and execution environment.')
        return super().configure(payload)

    def state(self):
        result = super().state()
        result['engine'] = {'available':True,'mode':'cloud','execution':'docker','network':False}
        result['version'] = '0.8.0'
        return result

    def start(self, *args, **kwargs):
        if kwargs.get('demo'):
            raise ValueError('The scripted desktop demo is not a hosted task.')
        kwargs['review_edits'] = False
        with self.manager.lock:
            # Keep already-running work alive; queue additional validated tasks
            # instead of rejecting users during another member's long project.
            # Each tenant retains the existing two-project concurrent limit.
            return super().start(*args,**kwargs)

    def file_action(self, project_id, operation, body=None):
        if operation=='export-folder':
            raise ValueError('Use Download ZIP to export this cloud project.')
        return super().file_action(project_id,operation,body)

    def storage(self, path):
        raise ValueError('Cloud project storage is managed by the owner.')

    def reconnect_project(self, project_id, path):
        raise ValueError('Cloud project recovery is managed by the owner. Use Import folder for local files.')

    def retry_project_migration(self):
        raise ValueError('Cloud project storage is managed by the owner.')


class Tenants:
    def __init__(self, root, gateway_url, relay_secret, image='sparkle-coder-tools:local', max_running=3, provider_factory=NemotronClient):
        if len(relay_secret)<43 or not re.fullmatch(r'[A-Za-z0-9_-]+',relay_secret):
            raise ValueError('SPARKLE_RUNNER_SECRET must be a random base64url value of at least 43 characters.')
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.gateway_url=website_origin(gateway_url)
        self.relay_secret,self.image,self.max_running=relay_secret,image,max_running
        self.queue=EngineQueue(max_running)
        self.provider_factory=provider_factory
        if type(max_running) is not int or not 1<=max_running<=5:
            raise ValueError('Use 1–5 simultaneous coding sessions. Host Docker command slots are limited separately.')
        self.apps={};self.lock=threading.RLock()

    def get(self, identity, secret, receipt):
        if (not re.fullmatch(r'[a-f0-9-]{36}',identity) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}',secret)
                or receipt.get('id')!=identity or receipt.get('ready') is not True):
            raise ValueError('Invalid gateway account assertion.')
        with self.lock:
            if identity not in self.apps:
                if len(self.apps)>=50:
                    raise ValueError('The server has reached its 50-account limit.')
                root=self.root/identity
                if root.is_symlink():raise ValueError('Account root cannot be a symlink.')
                self.apps[identity]=HostedAppService(root,self.gateway_url,secret,receipt,self)
            app=self.apps[identity]
            app.account=GatewayAccount(self.gateway_url,secret,receipt)
            return app

    def close(self):
        for app in self.apps.values():app.close()


class HostedServer(ThreadingHTTPServer):
    daemon_threads=True
    hosted_origin=None
    def __init__(self,address,manager):
        self.manager=manager;self.tenant=threading.local()
        super().__init__(address,HostedHandler)

    @property
    def service(self):
        return self.tenant.service


class HostedHandler(Handler):
    def do_GET(self):
        if urlsplit(self.path).path=='/healthz':
            supplied=self.headers.get('X-Sparkle-Relay','')
            if not secrets.compare_digest(supplied.encode(),self.server.manager.relay_secret.encode()):
                self.send(403,{'error':'Use the account gateway.'});return
            self.send(200,{'ok':True,'service':'sparkle-hosted-engine','version':'0.8.0'});return
        super().do_GET()

    def guard(self,api=False):
        path=urlsplit(self.path).path
        if not api or not path.startswith('/api/'):
            self.send(404,{'error':'Not found.'});return False
        supplied=self.headers.get('X-Sparkle-Relay','')
        if not secrets.compare_digest(supplied.encode(),self.server.manager.relay_secret.encode()):
            self.send(403,{'error':'Use the SPARKLE account gateway.'});return False
        # Device/OS operations are never forwarded to a shared host.
        forbidden={'/api/quit','/api/open-folder','/api/select-folder','/api/storage','/api/retry-project-migration',
                   '/api/hosted-ui','/api/disconnect-hosted-ui','/api/demo','/api/account','/api/account/enroll','/api/account/login','/api/account/password','/api/account/coupon','/api/account/payment','/api/account/reconnect'}
        if path in forbidden or path.endswith(('/export-folder','/reconnect')):
            self.send(400,{'error':'Use browser import/download for files. The owner manages the cloud host.'});return False
        try:
            encoded=self.headers.get('X-Sparkle-Account','')
            if len(encoded)>4096:raise ValueError('Invalid account assertion.')
            receipt=json.loads(base64.b64decode(encoded,validate=True))
            self.server.tenant.service=self.server.manager.get(receipt['id'],self.headers.get('X-Sparkle-Device',''),receipt)
        except (ValueError,KeyError,TypeError):
            self.send(403,{'error':'Invalid account assertion.'});return False
        return True

    def do_OPTIONS(self):
        self.send(405,{'error':'Connect through the account gateway.'})


def main(argv=None):
    parser=argparse.ArgumentParser(description='Owner-hosted SPARKLE coding engine')
    parser.add_argument('--bind',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8788)
    parser.add_argument('--state-dir',type=Path,default=Path('HOSTED_DATA'))
    args=parser.parse_args(argv)
    manager=Tenants(args.state_dir,os.environ.get('SPARKLE_GATEWAY_URL',''),os.environ.get('SPARKLE_RUNNER_SECRET',''),
                    image=os.environ.get('SPARKLE_RUNNER_IMAGE','sparkle-coder-tools:local'),
                    max_running=int(os.environ.get('SPARKLE_MAX_RUNS','1')))
    # Fail closed: no fallback to executing a tester's code on the owner host.
    try:
        subprocess.run(['docker','info'],check=True,stdout=subprocess.DEVNULL,timeout=30)
        subprocess.run(['docker','image','inspect',manager.image],check=True,stdout=subprocess.DEVNULL,timeout=30)
    except (OSError,subprocess.SubprocessError):
        raise SystemExit('Docker and the tools image must be ready on the owner host. See HOSTED_ENGINE.md. No host-shell fallback is enabled.') from None
    server=HostedServer((args.bind,args.port),manager)
    print('SPARKLE hosted engine ready. Publish it through HTTPS and configure ENGINE_ORIGIN on the Worker.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();manager.close()


if __name__=='__main__':main()
