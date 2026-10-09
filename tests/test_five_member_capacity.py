"""Five-member admission and shared command throttling on a small host."""
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from unittest.mock import patch

from sparkle_coder.config import Config
from sparkle_coder.execution import CommandRunner, hosted_command_gate, hosted_command_slots
from sparkle_coder.hosted import EngineQueue, Tenants
from sparkle_coder.monitor import Run
from sparkle_coder.workspace import Workspace


class FiveMemberCapacityTests(unittest.TestCase):
    def test_five_distinct_active_members_and_sixth_waiting(self):
        waiting=EngineQueue(5)
        started=threading.Event()
        release=threading.Event()
        lock=threading.Lock()
        admitted=[]
        jobs=[Run('project-'+str(i),'nemotron') for i in range(6)]
        for job in jobs:waiting.enqueue(job)
        def run(job):
            if waiting.wait(job):
                with lock:
                    admitted.append(job.id)
                    if len(admitted)==5:started.set()
                release.wait(3)
                waiting.release(job)
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures=[pool.submit(run,j) for j in jobs]
            self.assertTrue(started.wait(2))
            self.assertEqual(len(waiting.running),5)
            self.assertEqual(len(waiting.waiting),1)
            self.assertEqual(len(admitted),5)
            release.set()
            for f in futures:f.result(timeout=3)
        self.assertEqual(len(admitted),6)
        self.assertFalse(waiting.running)
        self.assertFalse(waiting.waiting)

    def test_hosted_commands_serialize_and_waiter_can_cancel(self):
        with tempfile.TemporaryDirectory() as root:
            workspace=Workspace(Path(root))
            config=Config(auto_approve=True,execution='docker')
            config._runtime_cloud=True
            first_started=threading.Event()
            release=threading.Event()
            stopped=threading.Event()
            used=[]
            def fake_command(self,command,cwd,timeout,path,trusted):
                used.append(command)
                if command=='first':
                    first_started.set()
                    self.assert_not_a_real_method = True
                    release.wait(3)
                return {'ok':True,'exit_code':0,'output':'ok'}
            events=[]
            with patch.dict('os.environ',{'SPARKLE_HOSTED_COMMAND_SLOTS':'1'}),patch.object(CommandRunner,'_run_admitted_command',fake_command):
                runner1=CommandRunner(workspace,config,lambda _:True)
                runner2=CommandRunner(workspace,config,lambda _:True,should_stop=stopped.is_set,
                                      observe=lambda key,payload:events.append(key))
                result={}
                t1=threading.Thread(target=lambda:result.update(first=runner1.run('first')))
                t2=threading.Thread(target=lambda:result.update(second=runner2.run('second')))
                t1.start();self.assertTrue(first_started.wait(2))
                t2.start()
                deadline=time.monotonic()+2
                while 'command_wait' not in events and time.monotonic()<deadline:time.sleep(.01)
                self.assertIn('command_wait',events)
                self.assertEqual(used,['first'],'Second Docker command must wait, not run')
                stopped.set()
                t2.join(2)
                self.assertFalse(t2.is_alive())
                self.assertTrue(result['second']['cancelled'])
                self.assertEqual(used,['first'])
                release.set();t1.join(2)
                self.assertFalse(t1.is_alive())
                self.assertTrue(result['first']['ok'])
                third=CommandRunner(workspace,config,lambda _:True).run('third')
                self.assertTrue(third['ok'])
                self.assertEqual(used,['first','third'])

    def test_five_member_config_is_valid_not_six(self):
        with tempfile.TemporaryDirectory() as root:
            for count in (1,3,5):
                manager=Tenants(Path(root)/str(count),'https://gateway.example','R'*64,max_running=count)
                self.assertEqual(manager.queue.capacity,count)
                manager.close()
            with self.assertRaisesRegex(ValueError,'1–5'):
                Tenants(Path(root)/'six','https://gateway.example','R'*64,max_running=6)
        with patch.dict('os.environ',{'SPARKLE_HOSTED_COMMAND_SLOTS':'1'}):
            self.assertEqual(hosted_command_slots(),1)
        with patch.dict('os.environ',{'SPARKLE_HOSTED_COMMAND_SLOTS':'0'}):
            with self.assertRaises(ValueError):hosted_command_slots()


if __name__=='__main__':unittest.main()
