import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from sparkle_coder.agent import Agent, plain_discussion_text
from sparkle_coder.cloud import CloudAccount
from sparkle_coder.config import Config
from sparkle_coder.efficiency import compact_group, task_profile
from sparkle_coder.provider import ModelError, NemotronClient
from sparkle_coder.state import Session
from sparkle_coder.webapp import AppService
from sparkle_coder.workspace import Workspace


class EfficiencyTests(unittest.TestCase):
    def test_busy_pilot_keeps_waiting_beyond_six_short_retries(self):
        config=Config();config._runtime_cloud=True;client=NemotronClient(config)
        busy=urllib.error.HTTPError(config.base_url,429,'Busy',{'Retry-After':'3'},None)
        result=b'{"choices":[{"message":{"content":"Slot available"}}]}'
        with patch.object(client,'_read',side_effect=[busy]*8+[result]) as read,patch.object(client,'wait_retry'):
            self.assertEqual(client.complete([{'role':'user','content':'Build'}],[]).content,'Slot available')
        self.assertEqual(read.call_count,9)
        keys={call.args[0].get_header('Idempotency-key') for call in read.call_args_list}
        self.assertEqual(len(keys),1)

    def test_historical_file_writes_shrink_without_losing_original_or_pairing(self):
        code = 'body { color: green; }\n' * 1448
        group = [{'role':'assistant','content':'','tool_calls':[{'id':'write-1','type':'function','function':{'name':'write_file','arguments':json.dumps({'path':'styles.css','content':code})}}]},
                 {'role':'tool','tool_call_id':'write-1','content':json.dumps({'ok':True,'path':'styles.css','diff':code})}]
        original = json.dumps(group)
        compact = compact_group(group)
        self.assertLess(len(json.dumps(compact)), len(original)*.08)
        self.assertEqual(json.dumps(group), original)
        self.assertEqual(len(compact),1)
        self.assertEqual(compact[0]['role'],'assistant')
        self.assertIn('styles.css',compact[0]['content'])
        self.assertIn('metadata only',compact[0]['content'])
        self.assertNotIn('Historical edit body omitted',json.dumps(compact))
        self.assertNotIn('body { color: green; }',json.dumps(compact))

    def test_recent_file_write_keeps_exact_content_for_the_next_model_call(self):
        code = 'print("small task")\n' * 80
        group = [{'role':'assistant','content':'','tool_calls':[{'id':'write-1','type':'function','function':{'name':'write_file','arguments':json.dumps({'path':'app.py','content':code})}}]},
                 {'role':'tool','tool_call_id':'write-1','content':json.dumps({'ok':True,'path':'app.py'})}]
        compact = compact_group(group, recent=True)
        arguments = json.loads(compact[0]['tool_calls'][0]['function']['arguments'])
        self.assertEqual(arguments['content'], code)
        self.assertNotIn('Historical edit body omitted', arguments['content'])

    def test_corrupted_saved_edit_is_quarantined_even_when_recent(self):
        marker='[Historical edit body omitted from this request. The original source remains in history.]'
        group=[{'role':'assistant','content':'','tool_calls':[{'id':'write-1','type':'function','function':{
            'name':'write_file','arguments':json.dumps({'path':'styles.css','content':marker})}}]},
               {'role':'tool','tool_call_id':'write-1','content':json.dumps({'ok':True,'path':'styles.css'})}]
        compact=compact_group(group,recent=True)
        self.assertEqual(len(compact),1)
        self.assertIn('styles.css',compact[0]['content'])
        self.assertNotIn(marker,json.dumps(compact))

    def test_tiny_prompts_get_hard_budgets_without_misclassifying_debug_work(self):
        self.assertEqual(task_profile('addition program in python')['name'], 'micro')
        self.assertEqual(task_profile('build a simple landing page')['name'], 'simple_web')
        self.assertEqual(task_profile('build a static website for hotel')['name'], 'simple_web')
        self.assertEqual(task_profile('fix all bugs and test the existing project')['name'], 'standard')
        self.assertEqual(task_profile('simple landing page with authentication backend')['name'], 'standard')

    def test_micro_agent_uses_small_context_budget_and_tool_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace=Workspace(Path(temporary));config=Config()
            session=Session.create(workspace,'addition program in python',[],config.public_info())
            agent=Agent(workspace,session,config,None,lambda _:True,emit=lambda _:None)
            self.assertEqual(agent.task_profile['name'],'micro')
            self.assertEqual(config.max_steps,5)
            self.assertEqual(config.max_total_tokens,24000)
            self.assertEqual(config.max_tokens,3072)
            self.assertEqual(config.context_chars,12000)
            names={item['function']['name'] for item in agent.schemas}
            self.assertIn('verify',names)
            self.assertNotIn('run_command',names)
            self.assertNotIn('update_plan',names)
            self.assertNotIn('web_search',names)
            self.assertNotIn('read_web_page',names)

    def test_small_task_gets_web_tools_only_when_prompt_requests_current_web_info(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace=Workspace(Path(temporary));config=Config()
            session=Session.create(workspace,'build a simple landing page using the latest official docs',[],config.public_info())
            agent=Agent(workspace,session,config,None,lambda _:True,emit=lambda _:None)
            names={item['function']['name'] for item in agent.schemas}
            self.assertIn('web_search',names)
            self.assertIn('read_web_page',names)

    def test_old_saved_profile_is_reclassified_under_current_efficiency_rules(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace=Workspace(Path(temporary));config=Config()
            session=Session.create(workspace,'build a static website for a luxurious hotel',[],config.public_info())
            session.state['task_profile']={'name':'standard'}
            session.save()
            agent=Agent(workspace,session,config,None,lambda _:True,emit=lambda _:None)
            self.assertEqual(agent.task_profile['name'],'simple_web')
            self.assertEqual(agent.task_profile['version'],3)
            names={item['function']['name'] for item in agent.schemas}
            self.assertNotIn('web_search',names)
            self.assertNotIn('read_web_page',names)

    def test_ask_mode_plain_text_instruction_and_markdown_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace=Workspace(Path(temporary));config=Config()
            session=Session.create(workspace,'Discuss the best architecture for this project',[],config.public_info())
            session.state['task_mode']='ask';session.save()
            agent=Agent(workspace,session,config,None,lambda _:True,emit=lambda _:None)
            system=agent.context()[0]['content']
            self.assertIn('normal conversational plain text',system)
            raw='## Best approach\n\n- **Start simple**\n- Use `PostgreSQL`\n\n| Option | Note |\n| --- | --- |\n| Monolith | Easier first step |'
            cleaned=plain_discussion_text(raw)
            self.assertNotIn('##',cleaned)
            self.assertNotIn('**',cleaned)
            self.assertNotIn('`',cleaned)
            self.assertNotIn('|',cleaned)
            self.assertIn('Best approach',cleaned)
            self.assertIn('Start simple',cleaned)
            self.assertIn('PostgreSQL',cleaned)
            self.assertIn('Monolith',cleaned)

    def test_ask_mode_only_carries_web_schemas_when_the_question_needs_web(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace=Workspace(Path(temporary));config=Config()
            session=Session.create(workspace,'explain this function',[],config.public_info())
            session.state['task_mode']='ask'
            session.save()
            agent=Agent(workspace,session,config,None,lambda _:True,emit=lambda _:None)
            names={item['function']['name'] for item in agent.schemas}
            self.assertNotIn('web_search',names)
            session2=Session.create(workspace,'search the latest official Python docs',[],config.public_info())
            session2.state['task_mode']='ask'
            session2.save()
            agent2=Agent(workspace,session2,Config(),None,lambda _:True,emit=lambda _:None)
            names2={item['function']['name'] for item in agent2.schemas}
            self.assertIn('web_search',names2)
            self.assertIn('read_web_page',names2)

    def test_plain_site_verification_rechecks_edits_without_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace=Workspace(Path(temporary));config=Config()
            html='<html lang="en"><head><title>Flowers</title><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="styles.css"></head><body><a href="#contact">Contact</a><section id="contact">Flowers</section></body></html>'
            workspace.path('index.html').write_text(html);workspace.path('styles.css').write_text('body {color: green;}')
            session=Session.create(workspace,'Build a simple flower shop page',[],config.public_info())
            agent=Agent(workspace,session,config,None,lambda _:self.fail('A read-only HTML check must not run a command'),lambda _:None)
            self.assertTrue(agent.verify_completion()[0])
            self.assertEqual(session.state['checks'][-1]['source'],'builtin')
            self.assertIn('Not tested: rendered appearance', session.state['checks'][-1]['output'])
            workspace.path('styles.css').write_text('body {color: green;')
            self.assertFalse(agent.verify_completion()[0])
            workspace.path('styles.css').write_text('body {color: green;}')
            self.assertTrue(agent.verify_completion()[0])

    def test_direct_provider_does_not_repeat_an_ambiguous_post(self):
        client=NemotronClient(Config())
        with patch.object(client,'_read',side_effect=TimeoutError) as read:
            with self.assertRaisesRegex(ModelError,'not automatically repeated'):
                client.complete([],[])
            self.assertEqual(read.call_count,1)

    def test_gateway_retry_reuses_request_id_and_fast_mode_disables_reasoning(self):
        config=Config();config._runtime_cloud=True;client=NemotronClient(config);requests=[]
        def read(request):
            requests.append(request)
            if len(requests)==1:raise TimeoutError()
            return b'{"choices":[{"message":{"content":"OK"}}],"usage":{"prompt_tokens":0,"completion_tokens":3}}'
        with patch.object(client,'_read',side_effect=read),patch.object(client,'wait_retry'):
            response=client.complete([{'role':'user','content':'Hello'}],[])
        self.assertEqual(requests[0].get_header('Idempotency-key'),requests[1].get_header('Idempotency-key'))
        self.assertTrue(requests[0].get_header('Idempotency-key'))
        self.assertFalse(json.loads(requests[0].data)['chat_template_kwargs']['enable_thinking'])
        self.assertEqual(response.usage,{'prompt_tokens':0,'completion_tokens':3})

    def test_safe_gateway_5xx_uses_fresh_ids_and_stops_after_two_retries(self):
        config=Config();config._runtime_cloud=True;client=NemotronClient(config)
        failures=[urllib.error.HTTPError(config.base_url,502,'temporary',
                  {'Retry-After':'2','X-Sparkle-Safe-Retry':'true'},None) for _ in range(3)]
        with patch.object(client,'_read',side_effect=failures) as read,patch.object(client,'wait_retry') as wait:
            with self.assertRaisesRegex(ModelError,'HTTP 502'):
                client.complete([{'role':'user','content':'Hello'}],[])
        ids=[call.args[0].get_header('Idempotency-key') for call in read.call_args_list]
        self.assertEqual(len(ids),3);self.assertEqual(len(set(ids)),3);self.assertEqual(wait.call_count,2)

    def test_ambiguous_gateway_502_is_not_replayed_into_a_409(self):
        config=Config();config._runtime_cloud=True;client=NemotronClient(config)
        failure=urllib.error.HTTPError(config.base_url,502,'uncertain',{},None)
        with patch.object(client,'_read',side_effect=failure) as read,patch.object(client,'wait_retry') as wait:
            with self.assertRaisesRegex(ModelError,'HTTP 502'):
                client.complete([{'role':'user','content':'Hello'}],[])
        self.assertEqual(read.call_count,1);wait.assert_not_called()


class AccountReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.account=CloudAccount(self.temporary.name,'https://sparkle.example')
        self.payload={'name':'Tester','email':'tester@example.test','consent':True}
        self.receipt={'id':'account-1','request_id':'request-1','kind':'signup',
                      'device_status':'pending','status':'pending','ready':False}

    def test_confirmed_signup_does_not_fail_because_of_a_second_network_request(self):
        def request(path,payload=None):
            if path=='/api/enroll':return dict(self.receipt)
            raise ValueError('Connection lost after signup was saved')
        with patch.object(self.account,'request',side_effect=request) as call:
            result=self.account.enroll(self.payload)
        self.assertTrue(result['enrolled']);self.assertEqual(result['request_id'],'request-1')
        self.assertFalse(result['ready']);self.assertEqual(call.call_count,1)
        self.assertTrue(json.loads(self.account.path.read_text())['registered'])

    def test_unconfirmed_response_never_marks_the_account_registered(self):
        for response in ({},{'ok':True},{'error':'Request failed'},{**self.receipt,'error':'Request failed'},
                         {**self.receipt,'device_status':'revoked'}):
            with self.subTest(response=response),patch.object(self.account,'request',return_value=response):
                with self.assertRaisesRegex(ValueError,'did not confirm'):
                    self.account.enroll(self.payload)
                self.assertFalse(self.account.credentials['registered'])
                self.assertFalse(json.loads(self.account.path.read_text())['registered'])

    def test_retry_after_a_lost_response_reuses_the_saved_device_connection(self):
        with patch.object(self.account,'request',side_effect=ValueError('Response lost')):
            with self.assertRaises(ValueError):self.account.enroll(self.payload)
        original=json.loads(self.account.path.read_text())['device_secret']
        reopened=CloudAccount(self.temporary.name,'https://sparkle.example')
        with patch.object(reopened,'request',return_value=self.receipt):result=reopened.enroll(self.payload)
        self.assertEqual(reopened.secret,original);self.assertTrue(result['enrolled'])


@unittest.skipUnless(shutil.which('node'),'Node 24 required for gateway integration')
class DesktopGatewayTests(unittest.TestCase):
    def test_signup_approval_model_usage_restart_and_credit_reload(self):
        root=Path(__file__).resolve().parents[1]
        server=subprocess.Popen(['node',str(root/'scripts/test_gateway_server.mjs')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(server.stderr.close);self.addCleanup(server.stdout.close)
        self.addCleanup(lambda: server.wait(timeout=5));self.addCleanup(server.terminate)
        url=server.stdout.readline().strip()
        self.assertTrue(url.startswith('http://127.0.0.1:'))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        cookie=''
        def admin(path,payload=None):
            nonlocal cookie
            request=urllib.request.Request(url+'/api/admin/'+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Origin':url,'Cookie':cookie,'Content-Type':'application/json'})
            with opener.open(request,timeout=5) as response:
                if response.headers.get('Set-Cookie'):cookie=response.headers['Set-Cookie'].split(';')[0]
                return json.loads(response.read())
        with tempfile.TemporaryDirectory() as directory,patch('sparkle_coder.webapp.distribution',return_value=url):
            app=AppService(Path(directory));self.addCleanup(app.close)
            self.assertTrue(app.state()['account']['enabled'])
            account=app.account.enroll({'name':'Pilot Tester','email':'pilot@example.com','phone':'','password':'PilotPass123!','consent':True})
            self.assertFalse(account['ready']);self.assertTrue(account['enrolled'])
            token=app.account.secret
            self.assertGreater(len(token),43)
            self.assertNotIn(token,json.dumps(app.state()))
            self.assertNotIn(token,app.settings_path.read_text())
            admin('login',{'password':'test-admin-'*8})
            overview=admin('overview')
            self.assertEqual(overview['payments'],[])
            self.assertEqual(overview['devices'][0]['id'],account['request_id'])
            self.assertEqual(overview['devices'][0]['email'],'pilot@example.com')
            self.assertEqual(overview['audit'][0]['action'],'account-requested')
            with self.assertRaisesRegex(ValueError,'managed by the admin'):
                app.configure({'base_url':'https://attacker.example/v1','api_key':'oops'})
            app.account.payment({'utr':'123456789012'})
            admin('login',{'password':'test-admin-'*8})
            pending=admin('overview')['payments'][0]
            admin('payments/'+pending['id'],{'action':'approve','verified':True})
            ready=app.account.status();self.assertEqual(ready['available_tokens'],1000000)
            self.assertEqual(app.config().max_tokens,8192)
            client=NemotronClient(app.config())
            self.assertEqual(client.complete([{'role':'user','content':'Hi'}],[]).content,'Scripted response')
            self.assertEqual(app.account.status()['available_tokens'],999850)
            reopened=AppService(Path(directory));self.addCleanup(reopened.close)
            self.assertEqual(reopened.account.secret,token)
            self.assertTrue(reopened.account.status()['ready'])
            self.assertEqual(reopened.account.status()['available_tokens'],999850)
            if os.name!='nt':self.assertEqual(app.account.path.stat().st_mode&0o777,0o600)
            with tempfile.TemporaryDirectory() as destination:
                app.storage(destination)
                self.assertEqual(app.account.path,app.directory/'device-account.json')
