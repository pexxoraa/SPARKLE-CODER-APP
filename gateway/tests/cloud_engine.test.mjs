// Browser transport -> real Worker + transactional SQLite -> real Python HTTP
// service -> real project files/history. Model replies are explicitly scripted.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import {setTimeout as delay} from 'node:timers/promises';
import worker from '../src/worker.mjs';
import {D1} from './helpers.mjs';

async function fixture(t,{python=false}={}){
  const env={DB:new D1(),ADMIN_SECRET:'A'.repeat(64),CACHE_SECRET:'C'.repeat(64),UPI_ID:'owner@bank',PAYEE_NAME:'Owner'};
  t.after(()=>env.DB.db.close());
  let cookie='',calls=[],modelCalls=0;
  if(python){
    env.NVIDIA_API_KEY='test-provider-key';
    env.UPSTREAM={fetch:async(url,options)=>{
      modelCalls++;const body=JSON.parse(options.body);
      assert.equal(options.headers.Authorization,'Bearer test-provider-key');assert.ok(body.tools.length>5);assert.equal(body.max_tokens,8192);
      const actions=modelCalls===1?[['write_file',{path:'src/hello.txt',content:'A real saved agent file'}],['write_file',{path:'README.md',content:'A second file'}]]:
        [['request_input',{question:'Which feature next?',next_step:'Choose a feature.'}]];
      return Response.json({choices:[{message:{role:'assistant',content:'',tool_calls:actions.map(([name,args],index)=>({id:'call_'+modelCalls+'_'+index,type:'function',function:{name,arguments:JSON.stringify(args)}}))},finish_reason:'tool_calls'}],usage:{prompt_tokens:100,completion_tokens:20}});
    }};
    const gateway=createServer(async(req,res)=>{
      try{
        const chunks=[];for await(const chunk of req)chunks.push(chunk);
        const response=await worker.fetch(new Request('https://sparkle.example'+req.url,{method:req.method,headers:req.headers,...(chunks.length?{body:Buffer.concat(chunks)}:{})}),env);
        res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
      }catch(error){res.writeHead(500);res.end(JSON.stringify({error:String(error)}));}
    });
    gateway.listen(0,'127.0.0.1');await once(gateway,'listening');
    t.after(()=>new Promise(resolve=>gateway.close(resolve)));
    const origin='http://127.0.0.1:'+gateway.address().port;
    const child=spawn('python3',['-u',fileURLToPath(new URL('./engine_server.py',import.meta.url)),origin],{stdio:['ignore','pipe','pipe']});
    let stderr='';child.stderr.on('data',chunk=>{stderr+=chunk;});
    const exited=once(child,'exit');
    t.after(async()=>{child.kill('SIGTERM');await exited;assert.equal(stderr,'');});
    const port=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('Python fixture did not start: '+stderr)),8000);
      child.once('error',error=>{clearTimeout(timer);reject(error);});
      child.stdout.once('data',chunk=>{clearTimeout(timer);resolve(Number(String(chunk).trim()));});
      child.once('exit',()=>{clearTimeout(timer);reject(Error('Python fixture exited: '+stderr));});
    });
    assert.ok(Number.isInteger(port)&&port>0);
    env.ENGINE_ORIGIN='https://engine.example';env.ENGINE_SECRET='R'.repeat(64);
    env.ENGINE={fetch:async(url,options)=>{calls.push({url,options});return fetch('http://127.0.0.1:'+port+new URL(url).pathname+new URL(url).search,options);}};
  }
  async function raw(path,body,secret,admin=false,extra={}){
    const result=await worker.fetch(new Request('https://sparkle.example'+path,{method:body===undefined?'GET':'POST',
      headers:{Origin:'https://sparkle.example',...(body===undefined?{}:{'Content-Type':'application/json'}),...(secret?{Authorization:'Bearer '+secret}:{}),...(admin?{Cookie:cookie}:{}),...extra},
      ...(body===undefined?{}:{body:JSON.stringify(body)})}),env);
    if(result.headers.has('Set-Cookie'))cookie=result.headers.get('Set-Cookie').split(';')[0];
    return result;
  }
  const local=new Map(),context=vm.createContext({window:{},Response,TextEncoder,crypto,btoa,location:{origin:'https://sparkle.example'},
    localStorage:{getItem:k=>local.get(k)||null,setItem:(k,v)=>local.set(k,v),removeItem:k=>local.delete(k)},
    fetch:(path,options)=>raw(path,options.body===undefined?undefined:JSON.parse(options.body),options.headers.Authorization.slice(7))});
  vm.runInContext(readFileSync(new URL('../public/cloud-adapter.js',import.meta.url),'utf8'),context);
  const request=(path,body)=>context.window.SparkleCloud.request(path,body);
  async function api(path,body){const response=await request(path,body),result=await response.json();assert.equal(response.status,200,JSON.stringify(result));return result;}
  const enroll=()=>api('/account/enroll',{name:'Cloud tester',email:'cloud@example.test',password:'CloudPass123!',consent:true});
  async function approve(){
    await api('/account/payment',{utr:'CLOUD123456789'});
    assert.equal((await raw('/api/admin/login',{password:env.ADMIN_SECRET},null,true)).status,200);
    const payment=env.DB.db.prepare('SELECT id FROM payments_v2').get();
    assert.equal((await raw('/api/admin/payments/'+payment.id,{action:'approve',verified:true},null,true)).status,200);
  }
  return {env,raw,api,request,local,context,calls,enroll,approve,get modelCalls(){return modelCalls;}};
}

test('full cloud flow: signup/admin approval -> two-file agent -> history/download/undo',async t=>{
  const f=await fixture(t,{python:true});
  let state=await f.api('/state');assert.equal(state.account.enrolled,false);assert.equal(state.engine.available,false);
  const receipt=await f.enroll();assert.ok(receipt.request_id);
  assert.equal(f.env.DB.db.prepare('SELECT id FROM devices WHERE status=?').get('pending').id,receipt.request_id);
  assert.equal((await f.raw('/api/engine/state',undefined,f.local.get('sparkle_device_secret'))).status,403);
  assert.equal(f.calls.length,0);
  await f.approve();state=await f.api('/state');assert.equal(state.account.balance_tokens,1000000);assert.equal(state.engine.available,true);
  const project='/projects/'+state.selected_project;
  await f.api(project+'/save-file',{path:'manual.txt',content:'Manual text'});
  assert.equal((await f.api(project+'/file?path=manual.txt')).content,'Manual text');
  const run=await f.api('/runs',{project_id:state.selected_project,goal:'Create two files',review_edits:true});
  let result,sawApproval=false;
  for(let i=0;i<100;i++){
    result=await f.api('/runs/'+run.id);
    if(result.status==='approval')sawApproval=true;
    if(!['queued','running','approval','stopping'].includes(result.status))break;
    await delay(15);
  }
  assert.equal(sawApproval,false);assert.equal(result.status,'needs_input');
  assert.equal(f.modelCalls,2);assert.equal((await f.api('/account')).balance_tokens,1000000-240);
  assert.deepEqual(new Set((await f.api(project+'/files')).files),new Set(['manual.txt','src/hello.txt','README.md']));
  const saved=project+'/sessions/'+result.session_id;
  assert.equal((await f.api(saved+'/changes')).changes.length,2);
  const archive=await f.request(project+'/download-project');assert.equal(archive.headers.get('Content-Type').split(';')[0],'application/zip');
  assert.match(archive.headers.get('Content-Disposition'),/attachment/);assert.ok((await archive.arrayBuffer()).byteLength>50);
  assert.match(await(await f.request(saved+'/report')).text(),/Create two files/);
  await f.api(saved+'/undo',{confirm:true});assert.deepEqual((await f.api(project+'/files')).files,['manual.txt']);
  for(const call of f.calls){
    assert.equal(call.options.headers['X-Sparkle-Relay'],f.env.ENGINE_SECRET);
    assert.equal(call.options.headers['X-Sparkle-Device'],f.local.get('sparkle_device_secret'));
    assert.equal(JSON.parse(Buffer.from(call.options.headers['X-Sparkle-Account'],'base64')).id,receipt.id);
    assert.equal(call.options.headers.Authorization,undefined);
  }
});

test('missing/invalid/unreachable engine reports a real blocked state, preserves account and receipt',async t=>{
  const f=await fixture(t);await f.enroll();await f.approve();
  for(const origin of [undefined,'invalid','http://engine.example','https://engine.example/path']){
    f.env.ENGINE_ORIGIN=origin;f.env.ENGINE_SECRET='R'.repeat(64);
    const state=await f.api('/state');assert.equal(state.account.ready,true);assert.equal(state.engine.available,false);assert.equal(state.projects.length,0);
  }
  f.env.ENGINE_ORIGIN='https://engine.example';f.env.ENGINE={fetch:async()=>{throw Error('Offline');}};
  const state=await f.api('/state');assert.equal(state.engine.available,false);assert.match(state.engine.message,/could not be reached/);
  assert.ok((await f.api('/account')).request_id);
});

test('gateway replaces spoofed identity and drops inbound credentials before proxying',async t=>{
  const f=await fixture(t);const receipt=await f.enroll();await f.approve();
  f.env.ENGINE_ORIGIN='https://engine.example';f.env.ENGINE_SECRET='R'.repeat(64);
  let seen;f.env.ENGINE={fetch:async(url,options)=>{seen=options;return Response.json({ok:true});}};
  const response=await f.raw('/api/engine/state',undefined,f.local.get('sparkle_device_secret'),false,{'X-Sparkle-Account':'spoof','X-Sparkle-Relay':'spoof',Cookie:'admin-secret'});
  assert.equal(response.status,200);assert.equal(seen.headers['X-Sparkle-Relay'],f.env.ENGINE_SECRET);
  assert.equal(JSON.parse(Buffer.from(seen.headers['X-Sparkle-Account'],'base64')).id,receipt.id);assert.equal(seen.headers.Cookie,undefined);
  f.env.DB.db.prepare('UPDATE accounts SET status=?').run('suspended');
  assert.equal((await f.raw('/api/engine/state',undefined,f.local.get('sparkle_device_secret'))).status,403);
});

test('cloud adapter retries a lost registration acknowledgement with the same device',async t=>{
  const f=await fixture(t);let first=true;const fetch=f.context.fetch;
  f.context.fetch=async(path,options)=>{const result=await fetch(path,options);if(path==='/api/enroll'&&first){first=false;throw Error('Dropped response');}return result;};
  await assert.rejects(f.enroll(),/Dropped/);const secret=f.local.get('sparkle_device_secret');
  const receipt=await f.enroll();assert.ok(receipt.request_id);assert.equal(f.local.get('sparkle_device_secret'),secret);
  assert.equal(f.env.DB.db.prepare('SELECT COUNT(*) AS n FROM devices').get().n,1);
  f.context.fetch=async()=>Response.json({});await assert.rejects(f.enroll(),/did not confirm/);
});

test('deployed cloud assets match the complete shared UI, with scratch data still reachable',()=>{
  assert.equal(readFileSync(new URL('../public/agent.js',import.meta.url),'utf8'),readFileSync(new URL('../../sparkle_coder/ui/app.js',import.meta.url),'utf8'));
  assert.equal(readFileSync(new URL('../public/agent.css',import.meta.url),'utf8'),readFileSync(new URL('../../sparkle_coder/ui/app.css',import.meta.url),'utf8'));
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  assert.match(html,/data-runtime="cloud"/);assert.ok(html.indexOf('cloud-adapter.js')<html.indexOf('agent.js'));assert.ok(html.indexOf('agent.js')<html.indexOf('cloud-features.js'));
  assert.match(html,/cloud-features\.css/);assert.match(readFileSync(new URL('../public/cloud-features.js',import.meta.url),'utf8'),/Cloud Workspace Studio/);
  assert.match(readFileSync(new URL('../public/scratch.html',import.meta.url),'utf8'),/src="\/app.js"/);
});

test('real Worker plus Python engine prevents cross-account project reads and writes',async t=>{
  const f=await fixture(t,{python:true});
  await f.enroll();await f.approve();
  const firstSecret=f.local.get('sparkle_device_secret');
  const firstState=await f.api('/state');
  const firstId=firstState.selected_project;
  assert.ok(firstId);
  await f.api('/projects/'+firstId+'/save-file',{path:'private.txt',content:'member-one-private-contents'});
  assert.equal((await f.api('/projects/'+firstId+'/file?path=private.txt')).content,'member-one-private-contents');

  const secondSecret='S'.repeat(64);
  f.local.set('sparkle_device_secret',secondSecret);
  const enrolled=await f.api('/account/enroll',{
    name:'Other tester',email:'other@example.test',password:'OtherPass123!',consent:true});
  assert.equal(enrolled.ready,false);
  const submitted=await f.api('/account/payment',{utr:'SECONDUPI1234567'});
  assert.equal(submitted.ready,false);
  assert.equal((await f.raw('/api/admin/login',{password:f.env.ADMIN_SECRET},null,true)).status,200);
  const payment=f.env.DB.db.prepare("SELECT id FROM payments_v2 WHERE utr=?").get('SECONDUPI1234567');
  assert.ok(payment);
  assert.equal((await f.raw('/api/admin/payments/'+payment.id,
    {action:'approve',verified:true},null,true)).status,200);
  const otherState=await f.api('/state');
  assert.equal(otherState.account.ready,true);
  assert.ok(otherState.selected_project);
  assert.notEqual(otherState.selected_project,firstId);
  const stolenRead=await f.request('/projects/'+firstId+'/file?path=private.txt');
  assert.ok([400,403,404].includes(stolenRead.status),'another member cannot inspect project content');
  assert.doesNotMatch(await stolenRead.text(),/member-one-private-contents/);
  const stolenWrite=await f.request('/projects/'+firstId+'/save-file',
    {path:'private.txt',content:'overwritten by other tenant'});
  assert.ok([400,403,404].includes(stolenWrite.status),'another member cannot mutate project files');

  f.local.set('sparkle_device_secret',firstSecret);
  const restored=await f.api('/state');
  assert.equal(restored.selected_project,firstId);
  assert.equal((await f.api('/projects/'+firstId+'/file?path=private.txt')).content,
    'member-one-private-contents','denied cross-account edit must leave owner file intact');
});
