from datetime import datetime, timezone
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.agent import Agent
from sparkle_coder.config import Config
from sparkle_coder.state import Session
from sparkle_coder.tools import ToolSet
from sparkle_coder.visual_quality import inspect_visual_quality, render_page
from sparkle_coder.workspace import Workspace


class VisualQualityTests(unittest.TestCase):
    def workspace(self):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        return Workspace(Path(temporary.name))

    def test_photo_studio_regression_rejects_boring_placeholder_output(self):
        workspace=self.workspace()
        (workspace.root/'index.html').write_text('''<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head><body><h1>Capture Your Moments</h1><img src="https://via.placeholder.com/800" alt="studio"><footer>© 2024 Studio</footer></body></html>''')
        (workspace.root/'styles.css').write_text('body{font-family:Arial;}')
        result=inspect_visual_quality(workspace,'index.html','photography')
        self.assertFalse(result['ok'])
        codes={item['code'] for item in result['findings']}
        self.assertTrue({'placeholder-assets','photography-imagery','responsive-intent','stale-date'} <= codes)
        self.assertIn('generic-creative-copy',codes)

    def test_image_first_responsive_photo_site_passes_blocking_gate(self):
        workspace=self.workspace();year=datetime.now(timezone.utc).year
        (workspace.root/'index.html').write_text(f'''<!doctype html><html><head><link rel="stylesheet" href="/styles.css"></head><body><h1>Quiet stories, honestly framed.</h1><img src="hero.jpg" alt="Portrait at dusk"><img src="work-1.jpg" alt="Wedding portrait"><img src="work-2.jpg" alt="Editorial portrait"><footer>© {year} Northlight Studio</footer></body></html>''')
        (workspace.root/'styles.css').write_text("body{font-family:Georgia,serif} @media(max-width:700px){body{padding:1rem}}")
        result=inspect_visual_quality(workspace,'index.html','photography')
        self.assertTrue(result['ok'],result['output'])

    def test_visual_tool_records_a_check_and_two_render_attempts(self):
        workspace=self.workspace();(workspace.root/'index.html').write_text('<h1>Studio</h1><img src="a.jpg" alt="a"><img src="b.jpg" alt="b"><img src="c.jpg" alt="c"><style>@media(max-width:600px){h1{font-size:2rem}}</style>')
        session=Session.create(workspace,'build a static website for a photo studio',[],{})
        tools=ToolSet(workspace,session,Config(auto_approve=True),lambda _:True)
        with patch('sparkle_coder.visual_quality.render_page',return_value={'ok':True,'available':True,'screenshot':'x.png'}):
            result=tools.inspect_visual_site('index.html','photography')
        self.assertTrue(result['ok']);self.assertEqual(len(result['renders']),2)
        self.assertTrue(session.state['checks'][-1]['command'].startswith('builtin:visual-site '))

    def test_render_page_uses_bounded_chromium_viewport(self):
        workspace=self.workspace();(workspace.root/'index.html').write_text('<h1>Render</h1>')
        session=Session.create(workspace,'render',[],{})
        def fake_run(command,**kwargs):
            target=Path(next(x.split('=',1)[1] for x in command if x.startswith('--screenshot=')))
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(b'\x89PNG\r\n\x1a\n'+b'0'*8+struct.pack('>II',390,844))
            class Result: returncode=0; stdout=''
            return Result()
        with patch('sparkle_coder.visual_quality.find_browser',return_value='/usr/bin/chromium'),patch('sparkle_coder.visual_quality.subprocess.run',side_effect=fake_run) as run:
            result=render_page(workspace,session.directory,'index.html','mobile')
        self.assertTrue(result['ok']);self.assertEqual(result['requested_size'],[390,844]);self.assertEqual(result['image_size'],[390,844])
        self.assertIn('--headless=new',run.call_args.args[0])

    def test_agent_completion_automatically_requires_visual_gate_for_photo_site(self):
        workspace=self.workspace();(workspace.root/'index.html').write_text('<h1>Capture Your Moments</h1><img src="https://via.placeholder.com/900" alt="placeholder"><style>@media(max-width:600px){body{margin:0}}</style>')
        session=Session.create(workspace,'build a static website for a photo studio',[],{})
        agent=Agent(workspace,session,Config(auto_approve=True),object(),lambda _:True,emit=lambda _:None)
        with patch('sparkle_coder.visual_quality.render_page',return_value={'ok':False,'available':False,'error':'not installed'}):
            passed,evidence=agent.verify_completion()
        self.assertFalse(passed);self.assertIn('visual-site',str([(c['command'],c['ok']) for c in session.state['checks']]))
        self.assertIn('Checks need repair',evidence)


if __name__=='__main__': unittest.main()
