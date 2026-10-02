import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';

const publicDir=new URL('../public/',import.meta.url);
const text=name=>readFile(new URL(name,publicDir),'utf8');

test('hosted web client is zero-install and wired to pilot APIs',async()=>{
  const [html,js,manifest,sw]=await Promise.all([text('scratch.html'),text('app.js'),text('manifest.webmanifest'),text('sw.js')]);
  for(const asset of ['/app.css','/app.js','/manifest.webmanifest'])assert.match(html,new RegExp(asset.replace('/','\\/')));
  assert.match(html,/Open local folder/);
  assert.match(html,/AI coding assistant/);
  assert.doesNotMatch(html,/Download the local app source|installer from your admin/i);
  for(const endpoint of ['/api/enroll','/api/me','/api/payments','/v1/chat/completions'])assert.ok(js.includes(endpoint),endpoint+' is wired');
  assert.ok(js.includes('showDirectoryPicker'),'direct local folder access is available');
  assert.ok(js.includes('Idempotency-Key'),'model calls are idempotent');
  assert.doesNotMatch(js,/NVIDIA_API_KEY|ADMIN_SECRET|CACHE_SECRET/);
  const parsed=JSON.parse(manifest);assert.equal(parsed.display,'standalone');assert.equal(parsed.icons.length,2);
  assert.match(sw,/sparkle-web-v8/);
  assert.match(html,/\/features\.js/);
  assert.match(sw,/\/features\.js/);
});
