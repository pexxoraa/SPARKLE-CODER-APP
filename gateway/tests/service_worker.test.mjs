import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function fixture(){
  const handlers={},stored=new Map(),deleted=[],writes=[];
  const cache={match:async r=>stored.get(typeof r==='string'?r:new URL(r.url).pathname),put:async(r,value)=>{writes.push(new URL(r.url).pathname);stored.set(new URL(r.url).pathname,value);},addAll:async()=>{}};
  const context=vm.createContext({URL,Response,self:{location:{origin:'https://sparkle.example'},addEventListener:(event,fn)=>{handlers[event]=fn;},clients:{claim:async()=>{}},skipWaiting:async()=>{}},
    caches:{open:async()=>cache,keys:async()=>['sparkle-web-v2','sparkle-web-v3','sparkle-web-v4','sparkle-web-v5','another-app'],delete:async key=>deleted.push(key)},fetch:async()=>Response.json({ok:true})});
  vm.runInContext(readFileSync(new URL('../public/sw.js',import.meta.url),'utf8'),context);
  const dispatch=async path=>{
    let response;const pending=[];
    handlers.fetch({request:new Request('https://sparkle.example'+path),respondWith:value=>{response=value;},waitUntil:value=>pending.push(value)});
    const result=await response;await Promise.all(pending);return result;
  };
  return {handlers,context,stored,deleted,writes,dispatch};
}

test('PWA caches only successful shell responses and leaves admin/API requests untouched',async()=>{
  const f=fixture();for(const path of ['/admin','/admin.html','/admin.js','/api/me','/api/admin/overview','/v1/chat/completions','/missing.js'])assert.equal(await f.dispatch(path),undefined);
  await f.dispatch('/app.js');assert.deepEqual(f.writes,['/app.js']);
  f.context.fetch=async()=>new Response('Server failed',{status:503});assert.equal((await f.dispatch('/app.js')).status,503);assert.equal(f.writes.length,1);
  let activating;f.handlers.activate({waitUntil:p=>{activating=p;}});await activating;assert.deepEqual(f.deleted,['sparkle-web-v2','sparkle-web-v3','sparkle-web-v4']);
});

test('offline JavaScript receives its own cached file, never the app HTML fallback',async()=>{
  const f=fixture();f.stored.set('/',new Response('<html>app</html>'));f.context.fetch=async()=>{throw Error('Offline');};
  const missing=await f.dispatch('/app.js');assert.equal(missing.status,503);assert.doesNotMatch(await missing.text(),/<html>/);
  f.stored.set('/app.js',new Response('/* cached JS */'));assert.equal(await (await f.dispatch('/app.js')).text(),'/* cached JS */');assert.equal(await (await f.dispatch('/')).text(),'<html>app</html>');
});
