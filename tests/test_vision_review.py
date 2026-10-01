import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder import vision_review
from sparkle_coder.config import Config
from sparkle_coder.skills import set_overrides
from sparkle_coder.state import Session
from sparkle_coder.tools import ToolSet
from sparkle_coder.workspace import Workspace


class Headers:
    def get_content_type(self): return 'application/json'
class Response:
    def __init__(self,payload): self.payload=json.dumps(payload).encode();self.headers=Headers()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n=-1): return self.payload if n<0 else self.payload[:n]

class VisionReviewTests(unittest.TestCase):
    def png(self,path): path.write_bytes(b'\x89PNG\r\n\x1a\n'+b'fake-render');return path

    def test_disabled_by_default_and_public_config_never_exposes_key(self):
        with patch.dict(os.environ,{},clear=True): value=vision_review.public_configuration()
        self.assertFalse(value['available']);self.assertNotIn('api_key',value);self.assertNotIn('secret',json.dumps(value).lower())

    def test_openai_compatible_vision_result_is_bounded_and_parsed(self):
        with tempfile.TemporaryDirectory() as folder:
            image=self.png(Path(folder)/'desktop.png')
            content=json.dumps({'summary':'Strong foundation; improve hero crop.','findings':[{'severity':'high','category':'hero','message':'Subject is obscured.','suggestion':'Adjust object-position.'}]})
            payload={'choices':[{'message':{'content':content}}]}
            env={'SPARKLE_VISION_BASE_URL':'https://vision.example/v1','SPARKLE_VISION_MODEL':'vision-test','SPARKLE_VISION_API_KEY':'do-not-return-this-key'}
            with patch.dict(os.environ,env,clear=True),patch('sparkle_coder.vision_review._OPENER.open',return_value=Response(payload)) as opened:
                result=vision_review.review_rendered_page([image],'photo studio',['visual_qa'])
            self.assertTrue(result['ok']);self.assertEqual(result['findings'][0]['category'],'hero')
            self.assertNotIn('do-not-return-this-key',json.dumps(result));self.assertIn('/chat/completions',opened.call_args.args[0].full_url)

    def test_invalid_vision_response_fails_softly(self):
        with tempfile.TemporaryDirectory() as folder:
            image=self.png(Path(folder)/'mobile.png');payload={'choices':[{'message':{'content':'not json'}}]}
            env={'SPARKLE_VISION_BASE_URL':'https://vision.example/v1','SPARKLE_VISION_MODEL':'vision-test','SPARKLE_VISION_API_KEY':'key'}
            with patch.dict(os.environ,env,clear=True),patch('sparkle_coder.vision_review._OPENER.open',return_value=Response(payload)):
                result=vision_review.review_rendered_page([image])
            self.assertTrue(result['available']);self.assertFalse(result['ok']);self.assertIn('unreadable',result['error'])

    def test_visual_tool_calls_vision_only_when_project_opted_in(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace=Workspace(Path(folder));(workspace.root/'index.html').write_text('<h1>Studio</h1><img src="a.jpg" alt="a"><img src="b.jpg" alt="b"><img src="c.jpg" alt="c"><style>@media(max-width:600px){body{margin:0}}</style>')
            session=Session.create(workspace,'build a static website for a photo studio',[],{})
            tools=ToolSet(workspace,session,Config(auto_approve=True),lambda _:True)
            render={'ok':True,'available':True,'screenshot':str(self.png(session.directory/'fake.png'))}
            with patch('sparkle_coder.visual_quality.render_page',return_value=render),patch('sparkle_coder.vision_review.review_rendered_page') as review:
                tools.inspect_visual_site('index.html','photography');review.assert_not_called()
            set_overrides(workspace,[],[],True)
            with patch('sparkle_coder.visual_quality.render_page',return_value=render),patch('sparkle_coder.vision_review.review_rendered_page',return_value={'available':True,'ok':True,'summary':'Looks good.','findings':[]}) as review:
                result=tools.inspect_visual_site('index.html','photography')
            review.assert_called_once();self.assertTrue(result['vision_review']['ok'])


if __name__=='__main__': unittest.main()
