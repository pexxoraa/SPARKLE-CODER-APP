import {test} from 'node:test';
import assert from 'node:assert/strict';
import {engineConfigured,proxyEngine} from '../src/engine.mjs';

const account={id:'account-1',name:'Member',email:'member@example.test',status:'active',
  kind:'signup',device_status:'active',device_id:'device-1',device_created:1,
  balance:1000000,held:0};
const makeRequest=()=>new Request('https://sparkle.example/api/engine/state',{
  headers:{Authorization:'Bearer '+'S'.repeat(64)}});

test('relay rejects loopback and literal IP origins from environment or persisted runtime config',async()=>{
  const invalid=[
    'http://engine.example/','https://127.0.0.1/','https://169.254.169.254/',
    'https://10.1.2.3/','https://[::1]/','https://localhost/',
    'https://dev.localhost/','https://engine.example/path',
    'https://engine.example/?id=1','https://user:password@engine.example/'
  ];
  for(const origin of invalid){
    let called=0;
    const env={ENGINE_SECRET:'R'.repeat(64),ENGINE_ORIGIN:origin,
      ENGINE:{fetch:async()=>{called++;return Response.json({ok:true});}}};
    assert.equal(await engineConfigured(env),false,origin);
    const response=await proxyEngine(makeRequest(),env,account);
    assert.equal(response.status,503,origin);
    assert.equal(called,0,'never leak relay token to an invalid origin');
    // A bad stored origin must not override a safe environment fallback.
    env.DB={prepare:()=>({first:async()=>({value:origin})})};
    env.ENGINE_ORIGIN='https://engine.example/';
    assert.equal(await engineConfigured(env),true,origin);
  }
});

test('valid configured public HTTPS origin relays the authorized identity without forwarding bearer',async()=>{
  let called=0;
  const env={ENGINE_SECRET:'R'.repeat(64),ENGINE_ORIGIN:'https://engine.example/',
    ENGINE:{fetch:async(url,options)=>{
      called++;assert.equal(url,'https://engine.example/api/state');
      assert.equal(options.headers['X-Sparkle-Relay'],'R'.repeat(64));
      assert.equal(options.headers.Authorization,undefined);
      assert.equal(options.headers['X-Sparkle-Device'],'S'.repeat(64));
      assert.equal(options.redirect,'manual');
      return Response.json({ready:true});
    }}};
  assert.equal(await engineConfigured(env),true);
  const response=await proxyEngine(makeRequest(),env,account);
  assert.equal(response.status,200);
  assert.deepEqual(await response.json(),{ready:true});
  assert.equal(called,1);
});

test('untrusted engine redirects cannot forward relay credentials to a new host',async()=>{
  const env={ENGINE_SECRET:'R'.repeat(64),ENGINE_ORIGIN:'https://engine.example/',
    ENGINE:{fetch:async()=>new Response(null,{status:302,headers:{Location:'https://evil.example/'}})}};
  const response=await proxyEngine(makeRequest(),env,account);
  assert.equal(response.status,502);
  assert.equal(response.headers.has('Location'),false);
});
