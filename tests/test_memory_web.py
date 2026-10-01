import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder import internet
from sparkle_coder.agent import Agent
from sparkle_coder.config import Config
from sparkle_coder.state import Session
from sparkle_coder.tools import ToolSet
from sparkle_coder.workspace import Workspace


class MemoryAndWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace=Workspace(Path(self.tmp.name)/"project")
        self.config=Config()
        self.session=Session.create(self.workspace,"Build a hotel website",[],self.config.public_info())
        self.tools=ToolSet(self.workspace,self.session,self.config,lambda _:False)

    def test_context_compaction_marker_can_never_be_written_as_source(self):
        marker="[Historical edit body omitted from this request. The tool result records its outcome.]"
        result=self.tools.execute("write_file",{"path":"styles.css","content":marker})
        self.assertFalse(result["ok"])
        self.assertIn("compaction marker",result["error"])
        self.assertFalse((self.workspace.root/"styles.css").exists())

    def test_memory_recall_returns_relevant_facts_not_the_whole_store(self):
        facts={
            "hotel-brand":("Hotel site uses warm neutral styling and a booking CTA.","project brief"),
            "python-tests":("Run python3 -m unittest for backend checks.","README"),
            "database":("D1 stores member credit balances.","architecture"),
            "shipping":("There is no shipping feature in this software.","notes"),
            "windows":("Windows packaging uses a separate script.","build docs"),
        }
        for key,(fact,source) in facts.items():
            self.assertTrue(self.tools.execute("remember",{"key":key,"fact":fact,"source":source})["ok"])
        recalled=self.tools.recall_memory("update the hotel booking page",limit=2)
        text=json.dumps(recalled)
        self.assertIn("hotel-brand",text)
        self.assertNotIn("python-tests",text)
        self.assertLessEqual(len(recalled),2)

    def test_file_memory_tracks_hash_without_copying_file_body(self):
        body="body { color: #222; }\n"*100
        result=self.tools.execute("write_file",{"path":"styles.css","content":body})
        self.assertTrue(result["ok"])
        store=json.loads((self.workspace.state_dir/"memory.json").read_text("utf-8"))
        self.assertEqual(store["version"],2)
        self.assertEqual(store["files"]["styles.css"]["sha256"],result["sha256"])
        self.assertEqual(store["files"]["styles.css"]["size"],len(body.encode()))
        self.assertNotIn(body, json.dumps(store))

    def test_successful_task_summary_becomes_retrievable_memory(self):
        agent=Agent(self.workspace,self.session,self.config,None,lambda _:True,emit=lambda _:None)
        agent.finish("checked","Hotel page completed with responsive layout and booking CTA.")
        recalled=agent.tools.recall_memory("hotel booking layout",limit=3)
        self.assertTrue(any(item.get("kind")=="task" and "booking CTA" in item.get("summary","")
                            for item in recalled))

    def test_old_flat_memory_format_remains_usable(self):
        legacy={"tests":{"fact":"Use unittest.","source":"README.md","updated":"2026-01-01T00:00:00+00:00"}}
        (self.workspace.state_dir/"memory.json").write_text(json.dumps(legacy),"utf-8")
        self.assertEqual(self.tools.memory()["tests"]["fact"],"Use unittest.")
        self.assertEqual(self.tools.recall_memory("unittest",1)[0]["key"],"tests")

    def test_private_and_local_web_addresses_are_blocked_before_fetch(self):
        for url in ("http://127.0.0.1/","http://localhost/","http://169.254.169.254/latest/meta-data/"):
            with self.subTest(url=url):
                result=self.tools.execute("read_web_page",{"url":url})
                self.assertFalse(result["ok"])
                self.assertIn("blocked",result["error"].lower())
        with patch("sparkle_coder.internet.socket.getaddrinfo",
                   return_value=[(2,1,6,"",("10.0.0.4",443))]):
            result=self.tools.execute("read_web_page",{"url":"https://internal.example/"})
        self.assertFalse(result["ok"])
        self.assertIn("blocked",result["error"].lower())

    def test_web_tools_reject_credential_like_outbound_data(self):
        query=self.tools.execute("web_search",{"query":"api_key=super-secret-value python docs"})
        self.assertFalse(query["ok"])
        self.assertIn("credential",query["error"].lower())
        url=self.tools.execute("read_web_page",{"url":"https://example.com/docs?access_token=abc123"})
        self.assertFalse(url["ok"])
        self.assertIn("credential",url["error"].lower())

    def test_read_web_page_returns_visible_text_not_scripts(self):
        html="<html><head><title>Docs</title><script>steal()</script></head><body><h1>API guide</h1><p>Use the supported endpoint.</p></body></html>"
        with patch("sparkle_coder.internet._fetch",return_value=("https://docs.example/guide",html,"text/html")):
            result=internet.read_web_page("https://docs.example/guide")
        self.assertEqual(result["title"],"Docs")
        self.assertIn("API guide",result["text"])
        self.assertIn("supported endpoint",result["text"])
        self.assertNotIn("steal()",result["text"])

    def test_web_search_returns_bounded_public_results(self):
        html="""<html><body>
          <a class="result__a" href="https://docs.example/one">Official docs</a>
          <div class="result__snippet">Current API documentation.</div>
          <a class="result__a" href="https://example.org/two">Release notes</a>
          <div class="result__snippet">Latest changes.</div>
        </body></html>"""
        with patch("sparkle_coder.internet._fetch",return_value=("https://html.duckduckgo.com/html/",html,"text/html")), \
             patch("sparkle_coder.internet._public_url",side_effect=lambda value:value):
            result=internet.web_search("current api docs",limit=1)
        self.assertEqual(result["provider"],"duckduckgo")
        self.assertEqual(len(result["results"]),1)
        self.assertEqual(result["results"][0]["title"],"Official docs")
        self.assertEqual(result["results"][0]["url"],"https://docs.example/one")

    def test_web_search_falls_back_to_bing_and_decodes_destination(self):
        target="https://docs.python.org/3/"
        token="a1"+base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
        challenge="<html><body>Unfortunately, bots use DuckDuckGo too.</body></html>"
        bing=f'<html><body><li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u={token}">Python docs</a></h2><div class="b_caption"><p>Official language documentation.</p></div></li></body></html>'
        with patch("sparkle_coder.internet._fetch",side_effect=[
                 ("https://html.duckduckgo.com/html/",challenge,"text/html"),
                 ("https://www.bing.com/search",bing,"text/html")]), \
             patch("sparkle_coder.internet._public_url",side_effect=lambda value:value):
            result=internet.web_search("python docs",limit=2)
        self.assertEqual(result["provider"],"bing")
        self.assertEqual(result["results"][0]["url"],target)
        self.assertEqual(result["results"][0]["title"],"Python docs")


if __name__=="__main__":
    unittest.main()

class AssetToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.workspace=Workspace(Path(self.tmp.name)/'project')
        self.session=Session.create(self.workspace,'build a static website for a photo studio',[],{})
        self.tools=ToolSet(self.workspace,self.session,Config(auto_approve=True),lambda _:True)

    def test_download_asset_is_bounded_journaled_and_requires_usage_note(self):
        data=b'\x89PNG\r\n\x1a\n'+b'image-bytes'
        fetched={'url':'https://upload.wikimedia.org/example.png','content_type':'image/png','data':data,'bytes':len(data),'extensions':('.png',)}
        with patch('sparkle_coder.tools.fetch_public_asset',return_value=fetched):
            result=self.tools.execute('download_asset',{'url':'https://upload.wikimedia.org/example.png','path':'assets/hero.png','usage_note':'Wikimedia Commons · CC BY-SA · Example Artist'})
        self.assertTrue(result['ok']);self.assertEqual((self.workspace.root/'assets/hero.png').read_bytes(),data)
        self.assertTrue(self.session.state['journal'][-1]['applied'])
        self.assertFalse(self.tools.execute('download_asset',{'url':'https://example.com/x.png','path':'assets/hero.png','usage_note':'valid source note'})['ok'])
        self.assertFalse(self.tools.execute('download_asset',{'url':'https://example.com/y.png','path':'assets/other.png','usage_note':'short'})['ok'])

    def test_asset_download_rejects_private_and_credential_urls_before_network(self):
        for url in ('http://127.0.0.1/image.png','https://example.com/image.png?access_token=secret'):
            with self.subTest(url=url):
                result=self.tools.execute('download_asset',{'url':url,'path':'assets/x.png','usage_note':'Public-domain test source'})
                self.assertFalse(result['ok'])

    def test_photo_skill_enables_public_asset_search_but_offline_prompt_does_not(self):
        agent=Agent(self.workspace,self.session,Config(),None,lambda _:True,emit=lambda _:None)
        names={item['function']['name'] for item in agent.schemas}
        self.assertIn('search_assets',names);self.assertIn('download_asset',names)
        other=Session.create(self.workspace,'build a static website for a photo studio using local assets only',[],{})
        agent2=Agent(self.workspace,other,Config(),None,lambda _:True,emit=lambda _:None)
        names2={item['function']['name'] for item in agent2.schemas}
        self.assertNotIn('search_assets',names2)

class PublicAssetSearchTests(unittest.TestCase):
    class Headers:
        def __init__(self,content_type): self.content_type=content_type
        def get_content_type(self): return self.content_type
        def get(self,key,default=None): return default
    class Response:
        def __init__(self,data,content_type,url='https://commons.wikimedia.org/w/api.php'):
            self.data=data;self.headers=PublicAssetSearchTests.Headers(content_type);self.url=url
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self,n=-1): return self.data if n<0 else self.data[:n]
        def geturl(self): return self.url

    def test_commons_asset_search_returns_license_creator_and_direct_url(self):
        payload={'query':{'pages':[{'title':'File:Studio portrait.jpg','imageinfo':[{'thumburl':'https://upload.wikimedia.org/portrait.jpg','thumbwidth':1200,'thumbheight':800,'extmetadata':{'LicenseShortName':{'value':'CC BY-SA 4.0'},'Artist':{'value':'<b>Example Artist</b>'},'ImageDescription':{'value':'Editorial portrait'}}}]}]}}
        response=self.Response(json.dumps(payload).encode(),'application/json')
        with patch('sparkle_coder.internet._OPENER.open',return_value=response),patch('sparkle_coder.internet._public_url',side_effect=lambda value:value):
            result=internet.search_public_assets('editorial portrait',limit=3)
        item=result['results'][0]
        self.assertEqual(item['license'],'CC BY-SA 4.0');self.assertEqual(item['creator'],'Example Artist')
        self.assertEqual(item['url'],'https://upload.wikimedia.org/portrait.jpg')

    def test_public_asset_download_validates_image_signature_and_type(self):
        data=b'\x89PNG\r\n\x1a\n'+b'payload'
        response=self.Response(data,'image/png','https://upload.wikimedia.org/image.png')
        with patch('sparkle_coder.internet._OPENER.open',return_value=response),patch('sparkle_coder.internet._public_url',side_effect=lambda value:value):
            result=internet.download_public_asset('https://upload.wikimedia.org/image.png')
        self.assertEqual(result['content_type'],'image/png');self.assertEqual(result['data'],data)
        bad=self.Response(b'not-an-image','image/png','https://upload.wikimedia.org/bad.png')
        with patch('sparkle_coder.internet._OPENER.open',return_value=bad),patch('sparkle_coder.internet._public_url',side_effect=lambda value:value):
            with self.assertRaisesRegex(ValueError,'do not match'): internet.download_public_asset('https://upload.wikimedia.org/bad.png')
