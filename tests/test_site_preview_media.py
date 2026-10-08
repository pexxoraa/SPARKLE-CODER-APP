"""Safe project previews and explicitly selected image assets."""
from pathlib import Path
from unittest.mock import patch
import base64
import tempfile
import unittest

from sparkle_coder.files import UserFiles
from sparkle_coder.site_preview import preview_site, _reference
from sparkle_coder.media_library import import_commons_image, create_svg_graphic
from sparkle_coder.webapp import AppService


class PreviewMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.files=UserFiles(self.root)

    def write(self, relative, content):
        path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(content if isinstance(content,bytes) else content.encode('utf-8'))

    def test_local_css_images_and_inline_styles_render_without_network_or_scripts(self):
        self.write('index.html', '''<!DOCTYPE html><html><head><title>Test site</title>
            <link rel="stylesheet" href="assets/base.css">
            <style>.inline{background:url("assets/hero.png")}</style>
            <script>fetch('/api/account');window.parent.alert('BAD')</script></head>
            <body><h1>Test</h1><img src="/assets/hero.png" alt="Test">
            <img src="https://images.example/private?token=no" alt="Blocked">
            <a href="/api/account">Link</a><iframe src="https://evil.example"></iframe>
            <meta http-equiv="refresh" content="0; url=https://evil.example">
            </body></html>''')
        self.write('assets/base.css','.thing{color:red;background:url(hero.png)}')
        self.write('assets/hero.png',b'\x89PNG\r\n\x1a\n'+b'0'*120)
        value=preview_site(self.files)
        self.assertEqual(value['entry'],'index.html')
        self.assertEqual(value['assets'],2)
        self.assertTrue(value['html'].startswith('<!DOCTYPE html>'))
        self.assertIn('data:text/css;base64,',value['html'])
        self.assertIn('data:image/png;base64,',value['html'])
        self.assertNotIn('window.parent',value['html'])
        self.assertNotIn('<iframe src=',value['html'])
        self.assertNotIn('http-equiv="refresh"',value['html'])
        self.assertNotIn('href="/api/account"',value['html'])
        self.assertNotIn('https://images.example/private',value['html'])
        self.assertIn("script-src 'none'",value['html'].replace('&#x27;',"'"))
        self.assertIn("external",value['warnings'][0].lower())

    def test_nested_relative_paths_are_bounded(self):
        self.assertEqual(_reference('site/pages/index.html','../assets/photo.jpg'),'site/assets/photo.jpg')
        self.assertEqual(_reference('site/pages/index.html','/assets/photo.jpg'),'assets/photo.jpg')
        for bad in ('../../../../etc/passwd','//example.org/file.css','https://example.com/a','data:image/png;base64,abc',
                    '#home','%2e%2e/private'):
            self.assertIsNone(_reference('site/pages/index.html',bad),bad)

    def test_no_private_files_and_no_unsafe_external_resources(self):
        self.write('index.html','<html><head><link rel="stylesheet" href=".env"></head><body><img src=".env"></body></html>')
        self.write('.env','SUPERSECRET=must-never-leak')
        result=preview_site(self.files)
        self.assertNotIn('SUPERSECRET',result['html'])
        self.assertTrue(any('blocked' in x.lower() or 'unsupported' in x.lower() for x in result['warnings']))
        with self.assertRaisesRegex(ValueError,'HTML file'):
            preview_site(self.files,'package.json')
        with self.assertRaisesRegex(ValueError,'not found'):
            preview_site(self.files,'dist/index.html')
        with self.assertRaises(ValueError):
            preview_site(self.files,'../../outside.html')
        self.write('large.html','x'*(500001))
        with self.assertRaisesRegex(ValueError,'size'):
            preview_site(self.files,'large.html')

    def test_resource_limits_expose_warning_instead_of_loading_more_assets(self):
        images=''.join(f'<img src="p{i}.png">' for i in range(55))
        self.write('index.html','<html><body>'+images+'</body></html>')
        for i in range(55):
            self.write(f'p{i}.png',b'\x89PNG\r\n\x1a\n00')
        output=preview_site(self.files)
        self.assertEqual(output['assets'],48)
        self.assertTrue(any('limit' in warning.lower() for warning in output['warnings']))

    def test_create_svg_is_original_and_does_not_overwrite(self):
        first=create_svg_graphic(self.files,'Quiet horizon',style='night',primary='#102030',secondary='#ddeeff')
        second=create_svg_graphic(self.files,'Quiet horizon',style='night')
        self.assertNotEqual(first['path'],second['path'])
        source=(self.root/first['path']).read_text()
        self.assertIn('Quiet horizon',source)
        self.assertIn('#102030',source)
        self.assertNotIn('<script',source)
        self.assertIn('SVG',first['message'])
        with self.assertRaisesRegex(ValueError,'title'):
            create_svg_graphic(self.files,'')
        with self.assertRaisesRegex(ValueError,'Choose'):
            create_svg_graphic(self.files,'Valid title',style='unknown')
        escaped=create_svg_graphic(self.files,'<script>bad</script>')
        self.assertNotIn('<script>',(self.root/escaped['path']).read_text())
        self.assertIn('&lt;script&gt;', (self.root/escaped['path']).read_text())

    def test_wikimedia_import_revalidates_metadata_saves_credit_and_keeps_files(self):
        from sparkle_coder.media_library import download_public_asset as actual_download
        url='https://upload.wikimedia.org/example-landscape.jpg'
        payload={'results':[{'title':'Landscape.JPG','url':url,'source_page':'https://commons.wikimedia.org/wiki/File:Landscape.JPG',
                             'license':'CC BY-SA 4.0','creator':'Photographer A'}]}
        image={'url':url,'data':b'\xff\xd8\xff123','bytes':6,'content_type':'image/jpeg'}
        with patch('sparkle_coder.media_library.search_public_assets',return_value=payload) as search,\
             patch('sparkle_coder.media_library.download_public_asset',return_value=image) as download:
            first=import_commons_image(self.files,'landscape',url)
            second=import_commons_image(self.files,'landscape',url)
            self.assertNotEqual(first['path'],second['path'])
            self.assertEqual((self.root/first['path']).read_bytes(),image['data'])
            credit=(self.root/first['source_note']).read_text()
            self.assertIn('CC BY-SA 4.0',credit)
            self.assertIn('Photographer A',credit)
            self.assertIn('check the original source page',credit)
            self.assertEqual(download.call_count,2)
            search.assert_called_with('landscape',8)
        with patch('sparkle_coder.media_library.search_public_assets',return_value=payload),\
             patch('sparkle_coder.media_library.download_public_asset') as download:
            with self.assertRaisesRegex(ValueError,'changed'):
                import_commons_image(self.files,'landscape','https://other.example/image.jpg')
            download.assert_not_called()
        payload['results'][0]['license']='Check source page'
        with patch('sparkle_coder.media_library.search_public_assets',return_value=payload),\
             patch('sparkle_coder.media_library.download_public_asset') as download:
            with self.assertRaisesRegex(ValueError,'license label'):
                import_commons_image(self.files,'landscape',url)
            download.assert_not_called()

    def test_hosted_cloud_project_purpose_matches_project_creation_ui(self):
        import uuid
        from sparkle_coder.hosted import Tenants
        from sparkle_coder.brief import read_brief
        manager=Tenants(self.root/'tenants', 'https://example.test', 'R'*64,
                        max_running=1,provider_factory=lambda config: None)
        self.addCleanup(manager.close)
        identity=str(uuid.uuid4())
        app=manager.get(identity, 'x'*64, {'id':identity,'ready':True})
        project=app.add_project('Hosted landing page', purpose='Publish a landing page for a real client')
        workspace=app.project(project['id'])[1]
        self.assertEqual(read_brief(workspace)['brief']['purpose'],
                         'Publish a landing page for a real client')

    def test_app_media_mutations_respect_active_project_lock(self):
        app=AppService(self.root/'data')
        self.addCleanup(app.close)
        project=app.add_project('Site')
        result=app.image_action(project['id'],'create',{'title':'App abstract graphic'})
        self.assertTrue((Path(project['path'])/result['path']).is_file())
        from sparkle_coder.monitor import Run
        job=Run(project['id'],'nemotron')
        job.status='running'
        app.jobs[job.id]=job
        with self.assertRaisesRegex(ValueError,'running task'):
            app.image_action(project['id'],'create',{'title':'Blocked'})
        del app.jobs[job.id]
