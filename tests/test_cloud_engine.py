"""Real HTTP/file/session boundaries; model responses and Docker are test doubles."""
import base64
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from sparkle_coder.demo import calls
from sparkle_coder.hosted import Tenants, HostedServer
from sparkle_coder.monitor import ACTIVE
from sparkle_coder.provider import Completion
from sparkle_coder.execution import CommandRunner


ALICE = '11111111-1111-1111-1111-111111111111'
BOB = '22222222-2222-2222-2222-222222222222'
RELAY, DEVICE = 'R' * 64, 'D' * 64


class FileProvider:
    def __init__(self, config):
        self.config, self.phase = config, 0

    def complete(self, messages, schemas):
        self.phase += 1
        if self.phase == 1:
            return calls(('write_file', {'path':'src/main.txt', 'content':'First real file'}),
                         ('write_file', {'path':'README.md', 'content':'Second real file'}))
        return calls(('request_input', {'question':'Files saved. Which feature next?', 'next_step':'Choose a feature.'}))


class CloudEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = Tenants(Path(self.tmp.name), 'https://gateway.example', RELAY,
                               provider_factory=FileProvider)
        self.server = HostedServer(('127.0.0.1', 0), self.manager)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval':0.02}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.manager.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, path, body=None, user=ALICE, headers=None):
        receipt={'id':user, 'ready':True, 'status':'active', 'device_status':'active'}
        supplied={'X-Sparkle-Relay':RELAY, 'X-Sparkle-Device':DEVICE,
                  'X-Sparkle-Account':base64.b64encode(json.dumps(receipt).encode()).decode()}
        supplied.update(headers or {})
        if body is not None:supplied['Content-Type']='application/json'
        connection=http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('GET' if body is None else 'POST', path,
                               json.dumps(body) if body is not None else None, supplied)
            response=connection.getresponse();raw=response.read()
            result=json.loads(raw) if 'application/json' in response.getheader('Content-Type','') else raw
            return response.status,result,dict(response.getheaders())
        finally:connection.close()

    def api(self, path, body=None, user=ALICE):
        status,result,_=self.request(path,body,user)
        self.assertEqual(status,200,result)
        return result

    def project(self, user=ALICE):
        state=self.api('/api/state',user=user)
        self.assertTrue(state['engine']['available'])
        return '/api/projects/'+state['selected_project']

    def wait_run(self, run_id, predicate):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            result=self.api('/api/runs/'+run_id)
            if predicate(result):return result
            time.sleep(0.015)
        self.fail('Run failed to reach expected state: '+str(result))

    def test_relay_identity_and_host_operations_are_guarded(self):
        self.assertEqual(self.request('/healthz',headers={'X-Sparkle-Relay':''})[0],403)
        self.assertTrue(self.api('/healthz')['ok'])
        for headers in ({'X-Sparkle-Relay':''},{'X-Sparkle-Device':'short'},
                        {'X-Sparkle-Account':'not base64'},
                        {'X-Sparkle-Account':base64.b64encode(b'{"id":"../../../../","ready":true}').decode()}):
            self.assertEqual(self.request('/api/state',headers=headers)[0],403)
        self.assertEqual(len(self.manager.apps),0)
        for route in ('quit','select-folder','open-folder','storage','demo','hosted-ui','account/reconnect'):
            self.assertEqual(self.request('/api/'+route,{})[0],400,route)
        self.assertEqual(self.request('/')[0],404)

    def test_accounts_have_separate_projects_and_cannot_register_host_paths(self):
        a,b=self.project(),self.project(BOB)
        self.assertNotEqual(a,b)
        self.api(a+'/import',{'path':'notes.txt','data':base64.b64encode(b'Alice only').decode()})
        self.assertEqual(self.api(b+'/files',user=BOB)['files'],[])
        self.assertEqual(self.request(a+'/file?path=notes.txt',user=BOB)[0],400)
        self.assertEqual(self.request('/api/projects',{'name':'Escape','path':self.tmp.name})[0],400)
        for path in ('../settings.json','.env','.nemotron/state.json'):
            self.assertEqual(self.request(a+'/save-file',{'path':path,'content':'blocked'})[0],400)
        self.assertEqual(self.api(a+'/file?path=notes.txt')['content'],'Alice only')

    def test_project_config_cannot_disable_docker_or_read_owner_model_credentials(self):
        prefix=self.project();app=self.manager.apps[ALICE];root=app.project(prefix.split('/')[-1])[1].root
        (root/'nemotron.toml').write_text('execution="local"\nauto_approve=true\ndocker_network=true\ndocker_image="evil"\napi_key_env="OWNER_TEST_KEY"\nrequest_timeout=1000\nmax_tokens=32000\nmax_steps=9999\n')
        with patch.dict(os.environ,{'OWNER_TEST_KEY':'must-not-be-used'}):
            config=app.config(app.project(prefix.split('/')[-1])[1])
        self.assertEqual(config.api_key,DEVICE)
        self.assertEqual(config.base_url,'https://gateway.example/v1')
        self.assertEqual(config.execution,'docker');self.assertTrue(config.auto_approve)
        self.assertFalse(config.docker_network);self.assertEqual(config.docker_image,self.manager.image)
        self.assertEqual(config.max_steps,24);self.assertEqual(config.max_tokens,8192)
        self.assertEqual(config.request_timeout,300)
        self.assertEqual(self.request('/api/settings',{'execution':'local'})[0],400)
        self.assertNotIn(DEVICE,json.dumps(self.api('/api/state')))

    def test_text_create_save_delete_history_conflicts_and_undo(self):
        p=self.project();created=self.api(p+'/save-file',{'path':'src/edit.txt','content':'original'})
        preview=self.api(p+'/file?path=src/edit.txt');self.assertEqual(len(preview['sha256']),64)
        self.assertEqual(self.request(p+'/save-file',{'path':'src/edit.txt','content':'overwrite'})[0],400)
        edited=self.api(p+'/save-file',{'path':'src/edit.txt','content':'edited','expected_sha256':preview['sha256']})
        self.assertEqual(self.request(p+'/save-file',{'path':'src/edit.txt','content':'stale','expected_sha256':preview['sha256']})[0],400)
        self.assertEqual(self.request(p+'/sessions/'+created['session_id']+'/undo',{'confirm':True})[0],400)
        self.api(p+'/sessions/'+edited['session_id']+'/undo',{'confirm':True})
        self.assertEqual(self.api(p+'/file?path=src/edit.txt')['content'],'original')
        deleted=self.api(p+'/delete-file',{'path':'src/edit.txt','expected_sha256':preview['sha256']})
        self.assertEqual(self.api(p+'/files')['files'],[])
        self.api(p+'/sessions/'+deleted['session_id']+'/undo',{'confirm':True})
        self.assertEqual(self.api(p+'/file?path=src/edit.txt')['content'],'original')
        self.assertEqual(len(self.api(p+'/sessions')['sessions']),3)

    def test_multifile_agent_edits_auto_run_history_download_report_and_undo(self):
        p=self.project();pid=p.split('/')[-1]
        run=self.api('/api/runs',{'project_id':pid,'goal':'Create two files','review_edits':True})
        done=self.wait_run(run['id'],lambda r:r['status'] not in ACTIVE)
        self.assertNotEqual(done['status'],'approval')
        self.assertEqual(set(self.api(p+'/files')['files']),{'src/main.txt','README.md'})
        saved=p+'/sessions/'+done['session_id']
        self.assertEqual(len(self.api(saved+'/changes')['changes']),2)
        self.assertEqual(self.request('/api/runs/'+run['id'],user=BOB)[0],400)
        archive=self.request(p+'/download-project')[1]
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            self.assertEqual(set(bundle.namelist()),{'src/main.txt','README.md'})
            self.assertEqual(bundle.read('src/main.txt'),b'First real file')
        self.assertIn(b'Create two files',self.request(saved+'/report')[1])
        self.assertNotIn(b'approval_requested',self.request(saved+'/logs')[1])
        self.api(saved+'/undo',{'confirm':True})
        self.assertEqual(self.api(p+'/files')['files'],[])

    def test_auto_run_and_restart_preserve_saved_work(self):
        p=self.project();pid=p.split('/')[-1]
        run=self.api('/api/runs',{'project_id':pid,'goal':'Write approved files','review_edits':True})
        done=self.wait_run(run['id'],lambda r:r['status'] not in ACTIVE)
        self.assertNotEqual(done['status'],'approval')
        self.assertTrue(self.api(p+'/files')['files'])
        # A new service process loads the same account and history, with no stored device key.
        self.manager.apps[ALICE].close();del self.manager.apps[ALICE]
        self.assertEqual(self.api('/api/state')['selected_project'],pid)
        self.assertEqual(self.api(p+'/sessions')["sessions"][0]['id'],done['session_id'])
        self.assertNotIn(DEVICE,(Path(self.tmp.name)/ALICE/'settings.json').read_text())

    def test_missing_docker_cannot_fall_back_to_host_shell(self):
        p=self.project();app=self.manager.apps[ALICE];workspace=app.project(p.split('/')[-1])[1]
        runner=CommandRunner(workspace,app.config(workspace),lambda _:True)
        with patch('sparkle_coder.execution.subprocess.Popen',side_effect=FileNotFoundError('docker absent')) as popen:
            with self.assertRaises(FileNotFoundError):runner.run('printf secret')
        # The finally block also attempts Docker container cleanup.
        self.assertTrue(all(call.args[0][0]=='docker' for call in popen.call_args_list))
        args=popen.call_args_list[0].args[0]
        self.assertEqual(args[:2],['docker','run']);self.assertIn('--read-only',args)
        self.assertEqual(args[args.index('--network')+1],'none')
        self.assertNotIn(DEVICE,' '.join(args));self.assertFalse(popen.call_args_list[0].kwargs['shell'])


if __name__=='__main__':unittest.main()
