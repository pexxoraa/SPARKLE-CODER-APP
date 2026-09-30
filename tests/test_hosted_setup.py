import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import setup_hosted_engine as setup


class HostedSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.owner=self.root/'gateway/.owner'
        self.owner.mkdir(parents=True)
        for key,value in [('ROOT',self.root),('OWNER',self.owner),('ENGINE',self.owner/'engine.json')]:
            replacement=patch.object(setup,key,value);replacement.start();self.addCleanup(replacement.stop)
        self.output=io.StringIO()
        redirect=contextlib.redirect_stdout(self.output);redirect.__enter__();self.addCleanup(redirect.__exit__,None,None,None)

    def test_initialize_preserves_secret_and_never_prints_it(self):
        setup.initialize('https://worker.example')
        first=setup.read_config();setup.initialize('https://worker.example/')
        self.assertEqual(first,setup.read_config())
        self.assertNotIn(first['relay_secret'],self.output.getvalue())
        if os.name!='nt':self.assertEqual(setup.ENGINE.stat().st_mode&0o777,0o600)
        with self.assertRaisesRegex(ValueError,'different Worker'):setup.initialize('https://other.example')

    def owner_config(self):
        value={'name':'saved-pilot','main':'old-code','assets':{'directory':'old-assets'},
               'vars':{'UPI_ID':'keep@bank','PAYEE_NAME':'Keep'},
               'd1_databases':[{'database_id':'keep-this-id','database_name':'keep-this-db'}]}
        (self.owner/'wrangler.json').write_text(json.dumps(value))
        return value

    def test_offline_engine_stops_before_secret_upload_or_owner_configuration_changes(self):
        setup.initialize('https://worker.example');old=self.owner_config()
        with patch.object(setup,'check_engine',side_effect=ValueError('offline')),patch.object(setup,'run_wrangler') as cli:
            with self.assertRaisesRegex(ValueError,'offline'):setup.connect('https://engine.example')
        cli.assert_not_called();self.assertEqual(json.loads((self.owner/'wrangler.json').read_text()),old)

    def test_connect_retains_database_payment_settings_and_uploads_secret_via_stdin(self):
        setup.initialize('https://worker.example');old=self.owner_config()
        response=io.BytesIO(json.dumps({'ok':True,'version':'0.8.0','engine_configured':True}).encode())
        with patch.object(setup,'check_engine') as check,patch.object(setup,'publish_origin'),patch.object(setup,'run_wrangler') as cli,\
                patch.object(setup.subprocess,'run') as command,\
                patch.object(setup,'deploy_worker',return_value='https://worker.example'),\
                patch.object(setup.urllib.request,'urlopen',return_value=response) as health:
            setup.connect('https://engine.example')
        request=health.call_args.args[0]
        self.assertEqual(request.get_header('User-agent'),'SPARKLE-CODER/0.8.0')
        self.assertEqual(request.get_header('Accept'),'application/json')
        value=json.loads((self.owner/'wrangler.json').read_text())
        self.assertEqual(value['d1_databases'][0]['database_id'],old['d1_databases'][0]['database_id'])
        self.assertEqual(value['vars']['UPI_ID'],'keep@bank')
        self.assertEqual(value['vars']['ENGINE_ORIGIN'],'https://engine.example')
        secret=setup.read_config()['relay_secret']
        check.assert_called_once_with('https://engine.example',secret)
        self.assertEqual(cli.call_args.args[1:],('secret','put','ENGINE_SECRET'))
        self.assertEqual(cli.call_args.kwargs['input_text'],secret)
        self.assertNotIn(secret,self.output.getvalue());self.assertNotIn(secret,(self.owner/'wrangler.json').read_text())
        self.assertEqual(command.call_count,2)

    def test_publish_origin_updates_runtime_without_worker_deploy(self):
        gateway='https://saved-pilot.example';origin='https://fresh-pilot.trycloudflare.com'
        setup.initialize(gateway);self.owner_config()
        response=io.BytesIO(json.dumps({'ok':True,'origin':origin}).encode())
        class Opener:
            def open(self,request,timeout=0):
                self.request=request;return response
        opener=Opener()
        with patch.object(setup,'check_engine') as check,patch.object(setup.urllib.request,'build_opener',return_value=opener),patch.object(setup,'deploy_worker') as deploy:
            result=setup.publish_origin(origin)
        self.assertEqual(result,origin);deploy.assert_not_called()
        check.assert_called_once_with(origin,setup.read_config()['relay_secret'])
        self.assertEqual(opener.request.full_url,gateway+'/api/internal/engine-origin')
        self.assertEqual(opener.request.get_header('X-sparkle-relay'),setup.read_config()['relay_secret'])
        self.assertEqual(json.loads(opener.request.data),{'origin':origin})
        self.assertEqual(json.loads((self.owner/'wrangler.json').read_text())['vars']['ENGINE_ORIGIN'],origin)
        receipt=json.loads((self.owner/'engine-deployment.json').read_text())
        self.assertEqual(receipt['engine_origin'],origin);self.assertTrue(receipt['health_verified'])

    def test_same_worker_workers_dev_subdomain_change_is_synchronized(self):
        old_url='https://saved-pilot.sparklecoder.workers.dev'
        new_url='https://saved-pilot.blindrobots.workers.dev'
        setup.initialize(old_url);self.owner_config()
        (self.owner/'deployment.json').write_text(json.dumps({'gateway_url':new_url}))
        response=io.BytesIO(json.dumps({'ok':True,'version':'0.8.0','engine_configured':True}).encode())
        with patch.object(setup,'check_engine'),patch.object(setup,'publish_origin'),patch.object(setup,'run_wrangler'),\
                patch.object(setup.subprocess,'run'),patch.object(setup,'deploy_worker',return_value=new_url),\
                patch.object(setup.urllib.request,'urlopen',return_value=response):
            changed=setup.connect('https://engine.example')
        self.assertTrue(changed)
        self.assertEqual(setup.read_config()['gateway_url'],new_url)

    def test_different_worker_name_is_still_rejected(self):
        setup.initialize('https://saved-pilot.sparklecoder.workers.dev');self.owner_config()
        (self.owner/'deployment.json').write_text(json.dumps({'gateway_url':'https://other-pilot.blindrobots.workers.dev'}))
        with patch.object(setup,'check_engine') as check:
            with self.assertRaisesRegex(ValueError,'different Worker'):setup.connect('https://engine.example')
        check.assert_not_called()

    def test_invalid_origins_and_redirects_do_not_forward_secret(self):
        for value in ('http://engine.example','https://user:pass@engine.example','https://engine.example/path'):
            with self.assertRaises(ValueError):setup.https_origin(value)
        with self.assertRaisesRegex(ValueError,'not forwarded'):
            setup.NoRedirect().redirect_request(None,None,None,None,None,None)


if __name__=='__main__':unittest.main()
