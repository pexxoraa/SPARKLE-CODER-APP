import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import recover_engine_tunnel as recovery


class TunnelRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.owner=Path(self.tmp.name)
        self.old='https://old-pilot.trycloudflare.com';self.new='https://new-pilot.trycloudflare.com'
        self.config={'vars':{'ENGINE_ORIGIN':self.old},'d1_databases':[{'database_id':'unchanged'}]}
        (self.owner/'wrangler.json').write_text(json.dumps(self.config))
        (self.owner/'engine-tunnel.log').write_text(self.old+'\n')
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(recovery.setup,'OWNER',self.owner))
        self.stack.enter_context(patch.object(recovery.setup,'read_config',return_value={'relay_secret':'R'*64}))
        self.clock=self.stack.enter_context(patch.object(recovery.time,'time',return_value=1000))
        self.restart=self.stack.enter_context(patch.object(recovery.subprocess,'run'))
        self.publish=self.stack.enter_context(patch.object(recovery.setup,'publish_origin'))
        self.sync=self.stack.enter_context(patch.object(recovery.setup,'sync_gateway_pairing',side_effect=lambda engine,config:(engine,False)))
        self.health=self.stack.enter_context(patch.object(recovery,'healthy',side_effect=lambda url,secret:url=='http://127.0.0.1:8788'))

    def test_expired_tunnel_restarts_after_two_failures_then_publishes_new_origin(self):
        self.assertEqual(recovery.recover()['status'],'waiting for tunnel recovery')
        self.restart.assert_not_called()
        self.assertEqual(recovery.recover()['status'],'restarting expired tunnel')
        self.restart.assert_called_once()
        (self.owner/'engine-tunnel.log').write_text(self.old+'\n'+self.new+'\n')
        self.health.side_effect=lambda url,secret:url in ('http://127.0.0.1:8788',self.new)
        self.assertEqual(recovery.recover()['status'],'reconnected')
        self.publish.assert_called_once_with(self.new)
        self.assertEqual((self.owner/'pilot-origin.txt').read_text(),self.new)

    def test_offline_local_engine_does_not_replace_tunnel_or_deploy(self):
        self.health.return_value=False;self.health.side_effect=None
        self.assertEqual(recovery.recover()['status'],'local engine unavailable')
        self.restart.assert_not_called();self.publish.assert_not_called()

    def test_healthy_published_origin_is_left_alone(self):
        self.health.return_value=True;self.health.side_effect=None
        (self.owner/'engine-deployment.json').write_text(json.dumps({'engine_origin':self.old,'deployed':True}))
        self.assertEqual(recovery.recover()['status'],'healthy')
        self.restart.assert_not_called();self.publish.assert_not_called()

    def test_failed_publish_retries_without_redeploying_worker(self):
        (self.owner/'engine-tunnel.log').write_text(self.old+'\n'+self.new+'\n')
        self.health.side_effect=lambda url,secret:url in ('http://127.0.0.1:8788',self.new)
        self.publish.side_effect=OSError('runtime update unavailable')
        self.assertIn('runtime publish failed',recovery.recover()['status'])
        self.assertEqual(recovery.recover()['status'],'waiting before reconnect')
        self.clock.return_value=1011;self.publish.side_effect=None
        self.assertEqual(recovery.recover()['status'],'reconnected')
        self.assertEqual(self.publish.call_count,2)

    def test_same_worker_gateway_update_restarts_hosted_engine_before_marking_healthy(self):
        self.sync.side_effect=lambda engine,config:({**engine,'gateway_url':'https://saved-pilot.new.workers.dev'},True)
        self.health.side_effect=lambda url,secret:url in ('http://127.0.0.1:8788',self.old)
        (self.owner/'engine-deployment.json').write_text(json.dumps({'engine_origin':self.old,'deployed':True}))
        result=recovery.recover()
        self.assertEqual(result['status'],'healthy');self.assertFalse(result['engine_restart_needed'])
        self.restart.assert_called_once()
        self.assertIn('sparkle-hosted-engine.service',self.restart.call_args.args[0])
        self.publish.assert_not_called()

    def test_log_cannot_supply_arbitrary_origins(self):
        self.assertIsNone(recovery.latest_origin('https://attacker.example\nhttp://localhost:9000'))
        self.assertEqual(recovery.latest_origin(self.old+'\n'+self.new),self.new)


if __name__=='__main__':unittest.main()
