// Exercise actual workerd fetch semantics, D1 and response caching, not a Node fetch stub.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import * as runtime from 'miniflare';

test('Workers runtime sends model/engine requests, settles exact usage, and refuses redirects',async()=>{
  const secret='A'.repeat(64),device='D'.repeat(64),calls=[];
  let redirect=false;
  const options={modules:['worker.mjs','engine.mjs'].map(name=>({type:'ESModule',path:fileURLToPath(new URL('../src/'+name,import.meta.url))})),compatibilityDate:'2026-09-01',
    bindings:{ADMIN_SECRET:secret,CACHE_SECRET:'C'.repeat(64),NVIDIA_API_KEY:'test-provider-key',ENGINE_SECRET:'R'.repeat(64),ENGINE_ORIGIN:'https://engine.example'},
    d1Databases:['DB'],outboundService:async request=>{
      calls.push({url:request.url,authorization:request.headers.get('authorization')});
      if(redirect)return new runtime.Response('',{status:307,headers:{Location:'https://untrusted.example/'}});
      return runtime.Response.json(request.url.startsWith('https://engine.example')?{projects:[{id:'real-runtime-project'}]}:
        {choices:[{message:{role:'assistant',content:'SPARKLE_READY'}}],usage:{prompt_tokens:10,completion_tokens:5}});
    }};
  const mf=new runtime.Miniflare(runtime.convertV4MiniflareOptions?runtime.convertV4MiniflareOptions(options):options);
  try{
    const db=await mf.getD1Database('DB');
    for(const migration of ['0001_pilot.sql','0002_login_coupons.sql']){
      let statement='';
      for(const line of readFileSync(new URL('../migrations/'+migration,import.meta.url),'utf8').split('\n')){
        if(!line.trim()||line.startsWith('--'))continue;statement+=line+' ';
        if(line.trim().endsWith(';')){await db.exec(statement);statement='';}
      }
    }
    await db.prepare("INSERT INTO accounts(id,email,name,status,balance,created) VALUES ('test','runtime@example.test','Runtime','active',1000000,1)").run();
    const digest=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(device))).toString('hex');
    await db.prepare("INSERT INTO devices(id,account_id,secret_hash,status,claimed_name,created) VALUES ('device','test',?,'active','Runtime',1)").bind(digest).run();
    const send=(path,body,headers={})=>mf.dispatchFetch('http://localhost'+path,{method:body===undefined?'GET':'POST',headers:{...(body===undefined?{}:{'Content-Type':'application/json'}),...headers},body:body===undefined?undefined:JSON.stringify(body)});
    const login=await send('/api/admin/login',{password:secret},{Origin:'http://localhost'});assert.equal(login.status,200);
    const cookie=login.headers.get('Set-Cookie').split(';')[0];
    const diagnostic=await send('/api/admin/model-check',{}, {Origin:'http://localhost',Cookie:cookie});
    assert.equal(diagnostic.status,200,JSON.stringify(await diagnostic.clone().json()));assert.equal((await diagnostic.json()).ok,true);
    const body={messages:[{role:'user',content:'Hello'}],max_tokens:64},auth={Authorization:'Bearer '+device,'Idempotency-Key':'runtime-request-0001'};
    const result=await send('/v1/chat/completions',body,auth);assert.equal(result.status,200,await result.clone().text());
    assert.equal(result.headers.get('X-Sparkle-Charged-Tokens'),'15');
    const before=calls.length;assert.equal((await send('/v1/chat/completions',body,auth)).status,200);assert.equal(calls.length,before);
    assert.deepEqual(await db.prepare("SELECT balance,held FROM accounts WHERE id='test'").first(),{balance:999985,held:0});
    const state=await send('/api/engine/state',undefined,auth);assert.equal(state.status,200);assert.equal((await state.json()).projects[0].id,'real-runtime-project');
    assert.equal(calls.at(-1).authorization,null);
    redirect=true;
    const rejected=await send('/api/engine/state',undefined,auth);assert.equal(rejected.status,502);assert.match((await rejected.json()).error,/redirected/);
    const providerRedirect=await send('/v1/chat/completions',body,{...auth,'Idempotency-Key':'runtime-request-0002'});assert.equal(providerRedirect.status,502);
    assert.ok(calls.every(call=>!call.url.includes('untrusted')),'Redirect destinations must never receive credentials');
  }finally{await mf.dispose();}
});
