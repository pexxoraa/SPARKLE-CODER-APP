"""Regressions: project change intent, checkpoint continuation, metered token counts."""
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from sparkle_coder.agent import Agent
from sparkle_coder.change_intent import requests_code_change
from sparkle_coder.config import Config
from sparkle_coder.provider import Completion,parse_completion
from sparkle_coder.state import Session
from sparkle_coder.webapp import AppService
from sparkle_coder.workspace import Workspace


class Provider:
    def __init__(self, responses):
        self.responses=iter(responses)
        self.calls=0

    def complete(self,messages,schemas):
        self.calls+=1
        return next(self.responses)


class ChangesAndUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace=Workspace(Path(self.temp.name)/'project')

    def make_agent(self,goal, provider, *, max_steps=None, runtime_cloud=False, task_mode='ask'):
        session=Session.create(self.workspace,goal,[],{})
        session.state['task_mode']=task_mode
        session.save()
        config=Config(base_url='http://127.0.0.1:8000/v1',max_steps=max_steps)
        config._auto_continue_cloud=runtime_cloud
        agent=Agent(self.workspace,session,config,provider,lambda command:True,emit=lambda *_:None)
        return agent,session

    def test_edit_intent_is_not_confused_with_explanations(self):
        for text in ('fix this bug', 'Add a button to the existing website',
                     'Change the home page colors', 'please update my project',
                     'Can you fix the navigation?', 'Build me a landing page'):
            self.assertTrue(requests_code_change(text),text)
        for text in ('Explain how to fix that bug', 'What changes are needed?',
                     'How can I make this app faster?', 'Why is the project broken?',
                     'Describe how to build a website', 'Do you know how to change that?'):
            self.assertFalse(requests_code_change(text),text)

    def test_ask_followup_explicit_edit_uses_build_and_saves_baseline(self):
        app=AppService(Path(self.temp.name)/'app',provider_factory=lambda config: Provider([Completion('done',[],{'prompt_tokens':2,'completion_tokens':3})]))
        self.addCleanup(app.close)
        app.configure({'base_url':'http://127.0.0.1:8000/v1','api_key':'test-key'})
        project=app.add_project('Existing app')
        workspace=app.project(project['id'])[1]
        (workspace.root/'index.html').write_text('<h1>Original</h1>')
        old=Session.create(workspace,'Explain this project',[],{})
        old.state.update(task_mode='ask',status='answered')
        old.save()
        # This test verifies follow-up mode and checkpoint creation, not how
        # long an actual agent takes to exhaust its repair loop. Mocking just
        # execution makes the background session setup deterministic on CI.
        # Separate tests cover real agent verification and continuation.
        with patch('sparkle_coder.webapp.Agent.run', return_value='paused') as run_agent:
            run=app.start(project['id'],'Change the existing homepage text',session_id=old.id,task_mode='ask')
            job=app.jobs[run['id']]
            job.thread.join(timeout=15)
            self.assertFalse(job.thread.is_alive(), 'Background session preparation did not finish')
            run_agent.assert_called_once()
        self.assertEqual(job.status, 'paused')
        self.assertIsNone(job.error)
        state=Session.load(workspace,old.id).state
        self.assertEqual(state['task_mode'],'build')
        self.assertEqual(state['requested_change']['goal'],'Change the existing homepage text')
        self.assertEqual(state['requested_change']['baseline'],workspace.fingerprint())
        self.assertNotEqual(state['status'],'checked')
        self.assertEqual((workspace.root/'index.html').read_text(),'<h1>Original</h1>')

    def test_reported_success_without_edit_refused_for_explicit_change(self):
        agent,session=self.make_agent('Change the existing home page',Provider([]),task_mode='build')
        path=self.workspace.root/'feature.py'
        path.write_text('print("Unchanged")')
        session.state['requested_change']={'goal':'Change the existing home page',
                                           'baseline':self.workspace.fingerprint(),'journal_start':0}
        session.save()
        # Stub only the verification check runners; project fingerprint and
        # runtime completion rules remain the original code under test.
        agent.tools.discover_checks=lambda:{'checks':[]}
        agent.tools.inspect_static_site=lambda *_:None
        ok,message=agent.verify_completion()
        self.assertFalse(ok)
        self.assertIn('no project file has changed',message)
        # Even a write then revert to the same contents isn't completion.
        session.state['journal'].append({'path':'feature.py','applied':True})
        ok,message=agent.verify_completion()
        self.assertFalse(ok)
        self.assertIn('no project file has changed',message)
        path.write_text('print("Changed")')
        ok,message=agent.verify_completion()
        self.assertNotIn('no project file has changed',message)

    def test_managed_cloud_continues_two_segments_then_respects_cap(self):
        provider=Provider([Completion('tool step', [{'id':'call1','type':'function',
              'function':{'name':'list_files','arguments':'{}'}}],{'prompt_tokens':10,'completion_tokens':4}),
              Completion('Completed',[],{'prompt_tokens':10,'completion_tokens':4})])
        agent,session=self.make_agent('Fix a project feature',provider,max_steps=1,
                                       runtime_cloud=True,task_mode='build')
        agent.verify_completion=lambda:(True,'verified')
        events=[]
        agent.observe=lambda kind,payload:events.append((kind,payload))
        self.assertEqual(agent.run(),'checked')
        self.assertEqual(provider.calls,2)
        self.assertEqual(agent.auto_continuations,1)
        self.assertTrue(any(kind=='budget_upgrade' for kind,_ in events))
        self.assertEqual(session.state['usage']['prompt_tokens'],20)

    def test_many_productive_segments_finish_without_arbitrary_pause(self):
        calls=[Completion('step', [{'id':f'call{i}', 'type':'function',
            'function':{'name':'list_files','arguments':'{}'}}],
            {'prompt_tokens':3,'completion_tokens':2}) for i in range(7)]
        calls.append(Completion('Completed',[],{'prompt_tokens':3,'completion_tokens':2}))
        provider=Provider(calls)
        agent,session=self.make_agent('Build a long project',provider,max_steps=1,
                                      runtime_cloud=True,task_mode='build')
        original_complete=provider.complete
        def advancing(messages,schemas):
            result=original_complete(messages,schemas)
            session.state['plan'].append({'step':f'Work item {provider.calls}',
                                          'status':'completed'})
            return result
        provider.complete=advancing
        agent.verify_completion=lambda:(True,'verified')
        self.assertEqual(agent.run(),'checked')
        self.assertEqual(provider.calls,8)
        self.assertEqual(agent.auto_continuations,7)
        self.assertEqual(session.state['usage']['prompt_tokens'],24)

    def test_new_diagnostic_evidence_does_not_trigger_false_stall(self):
        calls=[Completion('Investigating', [{'id':f'read{i}', 'type':'function',
            'function':{'name':'read_file','arguments':'{"path":"file%d.txt"}' % i}}],
            {'prompt_tokens':3,'completion_tokens':2}) for i in range(8)]
        calls.append(Completion('Verified', [], {'prompt_tokens':3,'completion_tokens':2}))
        provider=Provider(calls)
        agent,session=self.make_agent('Investigate a complex bug',provider,max_steps=1,
                                      runtime_cloud=True,task_mode='build')
        agent.tools.execute=lambda name,args:{'ok':True,'content':args.get('path','setup')}
        agent.verify_completion=lambda:(True,'verified')
        self.assertEqual(agent.run(),'checked')
        self.assertEqual(provider.calls,9)
        self.assertEqual(agent.auto_continuations,8)
        self.assertGreaterEqual(agent.continuation_evidence(),8)

    def test_stalled_cloud_run_stops_without_endless_credit_spend(self):
        provider=Provider([Completion('Repeated listing', [{'id':f'call{i}',
                'type':'function','function':{'name':'list_files','arguments':'{}'}}],
                {'prompt_tokens':3,'completion_tokens':2}) for i in range(10)])
        agent,session=self.make_agent('Build a project',provider,max_steps=1,
                                      runtime_cloud=True,task_mode='build')
        self.assertEqual(agent.run(),'blocked')
        self.assertEqual(provider.calls,5)
        self.assertTrue(agent._auto_continuation_stalled)
        self.assertIn('no new',session.state['summary'])
        self.assertNotIn('One detail is needed',session.state['summary'])

    def test_user_run_limit_is_never_automatically_extended(self):
        provider=Provider([Completion('tool step',[{'id':'call1','type':'function',
          'function':{'name':'list_files','arguments':'{}'}}],{'prompt_tokens':3,'completion_tokens':2})])
        agent,session=self.make_agent('Fix a project feature',provider,max_steps=1,runtime_cloud=False,task_mode='build')
        self.assertEqual(agent.run(),'paused')
        self.assertEqual(provider.calls,1)

    def test_exact_counts_and_estimates_are_separate(self):
        provider=Provider([
            Completion('Need a step', [{'id':'call1','type':'function',
                'function':{'name':'list_files','arguments':'{}'}}],{},'tool_calls'),
            Completion('Done',[],{'prompt_tokens':84,'completion_tokens':31})])
        agent,session=self.make_agent('Explain this',provider,task_mode='ask')
        self.assertEqual(agent.run(),'answered')
        usage=session.state['usage']
        self.assertEqual(usage['measurement'],'separate')
        self.assertEqual(usage['prompt_tokens'],84)
        self.assertEqual(usage['completion_tokens'],31)
        self.assertEqual(usage['confirmed_calls'],1)
        self.assertEqual(usage['estimated_calls'],1)
        self.assertGreater(usage['estimated_prompt_tokens'],0)
        self.assertGreater(usage['estimated_completion_tokens'],0)
        self.assertEqual(agent.usage_budget_total(),115+usage['estimated_prompt_tokens']+usage['estimated_completion_tokens'])

    def test_fractional_and_string_provider_usage_are_not_reported_as_exact(self):
        for invalid in ({'prompt_tokens':12.3,'completion_tokens':4},
                        {'prompt_tokens':'12','completion_tokens':4},
                        {'prompt_tokens':True,'completion_tokens':4},
                        {'prompt_tokens':-1,'completion_tokens':4}):
            value={'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],
                   'usage':invalid}
            self.assertEqual(parse_completion(value,'native').usage,{},invalid)
        good={'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],
                   'usage':{'prompt_tokens':16,'completion_tokens':4}}
        self.assertEqual(parse_completion(good,'native').usage,{'prompt_tokens':16,'completion_tokens':4})


if __name__=='__main__':
    unittest.main()
