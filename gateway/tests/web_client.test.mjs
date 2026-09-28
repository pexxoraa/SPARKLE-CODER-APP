// Run the shipped browser controller with DOM/storage adapters against the real
// Worker + transactional SQLite. This is not a substitute for a browser smoke test.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {D1} from './helpers.mjs';
import worker from '../src/worker.mjs';

function dom(){
  class Element {
    constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.value='';this.checked=false;this.hidden=false;this.disabled=false;this.open=false;this.selectionStart=0;this._text='';this.classList={add(){},remove(){}};}
    set textContent(v){this._text=String(v);this.children=[];}
    get textContent(){return this._text+this.children.map(n=>n.textContent).join(' ');}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this._text='';this.children=nodes;}
    addEventListener(name,fn){this['on'+name]=fn;}
    showModal(){this.open=true;}
    close(){this.open=false;}
    focus(){}
    remove(){}
    click(){return this.onclick?.();}
  }
  const html=readFileSync(new URL('../public/scratch.html',import.meta.url),'utf8');
  const elements=new Map([...html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)].map(m=>[m[2],new Element(m[1])]));
  const document={hidden:false,body:new Element('body'),getElementById:id=>{assert.ok(elements.has(id),'Missing HTML control #'+id);return elements.get(id);},createElement:tag=>new Element(tag),querySelectorAll:()=>[],addEventListener(){}};
  return {document,elements};
}
async function fixture(t){
  const env={DB:new D1(),ADMIN_SECRET:'A'.repeat(64),CACHE_SECRET:'B'.repeat(64),UPI_ID:'owner@bank',PAYEE_NAME:'Owner',NVIDIA_API_KEY:'test-only'};
  t.after(()=>env.DB.db.close());
  let calls=0,cookie='';
  env.UPSTREAM={fetch:async()=>{calls++;return Response.json({choices:[{message:{content:'Complete replacement:\n```js\nconsole.log("fixed");\n```'},finish_reason:'stop'}],usage:{prompt_tokens:100,completion_tokens:50}});}};
  const ui=dom(),local=new Map(),storage=new Map(),timers=[];
  const call=async(path,body,secret,admin=false,extra={})=>{
    const response=await worker.fetch(new Request('https://sparkle.example'+path,{method:body===undefined?'GET':'POST',headers:{...extra,Origin:'https://sparkle.example','Content-Type':'application/json',...(secret?{Authorization:'Bearer '+secret}:{}),...(admin?{Cookie:cookie}:{})},body:body===undefined?undefined:JSON.stringify(body)}),env);
    if(response.headers.has('Set-Cookie'))cookie=response.headers.get('Set-Cookie').split(';')[0];return response;
  };
  const context=vm.createContext({...ui,console,TextEncoder,Date,crypto,btoa,Blob,URL,Event,Response,Map,Set,
    navigator:{},window:{addEventListener(){}},prompt:()=>null,confirm:()=>true,
    setTimeout:()=>1,clearTimeout(){},setInterval:fn=>timers.push(fn),
    localStorage:{getItem:k=>local.get(k)||null,setItem:(k,v)=>local.set(k,v),removeItem:k=>local.delete(k)},
    fetch:(path,opts={})=>call(path,opts.body===undefined?undefined:JSON.parse(opts.body),opts.headers?.Authorization?.slice(7),false,opts.headers)
  });
  const script=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
  vm.runInContext(script.replace('const startup=init().catch(error=>toast(safeError(error)));',''),context);
  context.readStorage=async key=>structuredClone(storage.get(key));
  context.writeStorage=async(key,value)=>{storage.set(key,structuredClone(value));};
  vm.runInContext('dbGet=key=>readStorage(key); dbSet=(key,value)=>writeStorage(key,value);',context);
  const run=code=>vm.runInContext(code,context),el=id=>ui.elements.get(id);
  el('includeFile').checked=true;
  await run('init()');
  const signup=async()=>{el('loginMode').checked=false;el('loginMode').onchange();el('memberName').value='Browser tester';el('memberEmail').value='browser@example.test';el('memberPassword').value='BrowserPass123!';el('memberConsent').checked=true;await el('registerForm').onsubmit({preventDefault(){}});};
  const login=async()=>{assert.equal((await call('/api/admin/login',{password:env.ADMIN_SECRET},null,true)).status,200);};
  const approve=async()=>{
    await signup();await login();el('paymentReference').value='WEBTEST12345678';await el('paymentForm').onsubmit({preventDefault(){}});
    const payment=env.DB.db.prepare('SELECT id FROM payments_v2').get();assert.ok(payment);
    assert.equal((await call('/api/admin/payments/'+payment.id,{action:'approve',verified:true},null,true)).status,200);await run('refreshAccount()');
  };
  const edit=text=>{el('editor').value=text;el('editor').oninput();};
  const buttons=node=>node.children.flatMap(n=>[...(n.tagName==='button'?[n]:[]),...buttons(n)]);
  return {...ui,env,context,call,run,el,signup,login,approve,edit,storage,local,timers,buttons,get calls(){return calls;}};
}

test('browser signup receipt is in admin before payment; polling shows approved credits',async t=>{
  const f=await fixture(t);await f.signup();await f.login();
  const receipt=f.run('state.account'),overview=await (await f.call('/api/admin/overview',undefined,null,true)).json();
  assert.equal(overview.devices[0].id,receipt.request_id);assert.equal(overview.payments.length,0);
  assert.match(f.el('requestReceipt').textContent,new RegExp(receipt.request_id));assert.match(f.el('accountMessage').textContent,/new account request/i);
  f.el('paymentReference').value='BROWSER12345678';await f.el('paymentForm').onsubmit({preventDefault(){}});
  const id=f.env.DB.db.prepare('SELECT id FROM payments_v2').get().id;
  await f.call('/api/admin/payments/'+id,{action:'approve',verified:true},null,true);
  await f.timers[0]();assert.equal(f.run('state.account.ready'),true);assert.equal(f.el('accountBalance').textContent,'1,000,000');
});

test('typing a free coupon and submitting needs no Apply click or UPI reference',async t=>{
  const f=await fixture(t);await f.signup();await f.login();
  const created=await f.call('/api/admin/coupons',{code:'FREEUI',bonus_tokens:0,discount_paise:1500,max_uses:1,one_per_account:true},null,true);
  assert.equal(created.status,201);
  f.el('paymentCoupon').value='FREEUI';f.el('paymentCoupon').oninput();f.el('paymentReference').value='';
  assert.equal(f.el('paymentReferenceRow').hidden,true);assert.equal(f.el('upiPaymentBlock').hidden,true);
  assert.equal(f.el('paymentReference').required,false);
  await f.el('paymentForm').onsubmit({preventDefault(){}});
  const payment=f.env.DB.db.prepare('SELECT amount_paise,utr FROM payments_v2').get();
  assert.equal(payment.amount_paise,0);assert.match(payment.utr,/^FREE/);
  assert.equal(f.run('state.account.payments[0].amount_paise'),0);
});
test('a lost signup response retries the same saved identity without creating another account',async t=>{
  const f=await fixture(t),fetch=f.context.fetch;let drop=true;
  f.context.fetch=async(path,opts)=>{const response=await fetch(path,opts);if(path==='/api/enroll'&&drop){drop=false;throw Error('Connection interrupted');}return response;};
  await f.signup();assert.equal(f.run('state.account'),null);const secret=f.local.get('sparkle_device_secret');
  await f.signup();assert.equal(f.local.get('sparkle_device_secret'),secret);assert.ok(f.run('state.account.request_id'));
  assert.equal(f.env.DB.db.prepare('SELECT COUNT(*) AS n FROM accounts').get().n,1);
  assert.equal(f.env.DB.db.prepare('SELECT COUNT(*) AS n FROM devices').get().n,1);
});

test('invalid success bodies never display account-created success',async t=>{
  const f=await fixture(t);
  for(const data of [null,{}, {error:'Storage unavailable'}, {id:'x',ready:true}]){
    f.context.fetch=async()=>Response.json(data);await f.signup();assert.equal(f.run('state.account'),null);assert.equal(f.el('registerSection').hidden,false);assert.doesNotMatch(f.el('toast').textContent,/request received/i);
  }
});

test('late account lookup cannot erase the receipt; duplicate signup submits are blocked',async t=>{
  const f=await fixture(t),fetch=f.context.fetch;let release,entered;
  const waiting=new Promise(r=>{entered=r;});
  f.context.fetch=async(path,opts)=>{const response=await fetch(path,opts);if(path==='/api/me'){entered();await new Promise(r=>{release=r;});}return response;};
  const lookup=f.run('refreshAccount()');await waiting;await f.signup();release();await lookup;assert.ok(f.run('state.account.request_id'));
  let enrolls=0,finish;f.context.fetch=async(path,opts)=>{if(path==='/api/enroll'){enrolls++;await new Promise(r=>{finish=r;});}return fetch(path,opts);};
  const pending=f.signup();await f.signup();assert.equal(enrolls,1);finish();await pending;assert.equal(f.el('registerButton').disabled,false);
});

test('approved user signs back in with password without a new admin request',async t=>{
  const f=await fixture(t);await f.approve();f.run('reconnectAccount()');
  assert.equal(f.run('state.account'),null);assert.equal(f.el('loginMode').checked,true);
  f.el('memberEmail').value='browser@example.test';f.el('memberPassword').value='BrowserPass123!';
  await f.el('registerForm').onsubmit({preventDefault(){}});
  assert.equal(f.run('state.account.ready'),true);assert.equal(f.run('state.account.device_status'),'active');
  const pending=f.env.DB.db.prepare("SELECT COUNT(*) AS n FROM devices WHERE kind='recovery' AND status='pending'").get().n;
  assert.equal(pending,0);
});

test('new file saves the edited file first; a failed save prevents switching and stays dirty',async t=>{
  const f=await fixture(t);f.edit('Keep these edits');f.context.prompt=()=> 'src/app.js';await f.el('newFileButton').onclick();
  assert.equal(f.storage.get('scratchFiles')['README.md'],'Keep these edits');assert.equal(f.run('state.activePath'),'src/app.js');
  f.edit('Not saved yet');f.context.writeStorage=async()=>{throw Error('Quota exceeded');};f.context.prompt=()=> 'next.js';await f.el('newFileButton').onclick();
  assert.equal(f.run('state.activePath'),'src/app.js');assert.equal(f.el('editor').value,'Not saved yet');assert.equal(f.run('state.dirty'),true);assert.match(f.el('toast').textContent,/Quota exceeded/);
  await f.run('selectFile("README.md")');assert.equal(f.run('state.activePath'),'src/app.js');
});

test('slow directory reads are serialized and failed reads keep the previous buffer',async t=>{
  const f=await fixture(t);let release,entered;const waiting=new Promise(r=>{entered=r;});
  f.context.handles=new Map([['a.js',{getFile:async()=>{entered();await new Promise(r=>{release=r;});return {size:1,text:async()=> 'File A'};}}],['b.js',{getFile:async()=>{throw Error('Permission lost');}}]]);
  f.run('state.mode="directory";state.fileHandles=handles;');
  const first=f.run('selectFile("a.js")');await waiting;await f.run('selectFile("b.js")');release();await first;
  assert.equal(f.run('state.activePath'),'a.js');assert.equal(f.el('editor').value,'File A');
  await f.run('selectFile("b.js")');assert.equal(f.run('state.activePath'),'a.js');assert.equal(f.el('editor').value,'File A');
});

test('imports keep existing scratch files, skip dependencies and survive reload as scratch',async t=>{
  const f=await fixture(t);f.edit('Keep README');
  f.context.imports=[{name:'app.js',webkitRelativePath:'demo/app.js',size:2,text:async()=> 'ok'}, {name:'dep.js',webkitRelativePath:'demo/node_modules/dep.js',size:1,text:async()=> 'skip'}];
  await f.run('importFolder(imports)');assert.equal(f.storage.get('scratchFiles')['README.md'],'Keep README');assert.equal(f.storage.get('scratchFiles')['demo/app.js'],'ok');assert.equal(Object.keys(f.storage.get('scratchFiles')).length,2);assert.equal(f.storage.get('directoryHandle'),null);
  await f.run('loadScratch()');assert.equal(f.el('editor').value,'ok');
});

test('AI response stays bound to the original file and refuses newer editor changes',async t=>{
  const f=await fixture(t);await f.approve();f.edit('Original README');await f.run('saveActive()');
  let release,entered;const waiting=new Promise(r=>{entered=r;});
  f.env.UPSTREAM.fetch=async()=>{entered();await new Promise(r=>{release=r;});return Response.json({choices:[{message:{content:'```md\nReplacement\n```'},finish_reason:'stop'}],usage:{prompt_tokens:20,completion_tokens:10}});};
  f.el('prompt').value='Improve this file';const sending=f.el('promptForm').onsubmit({preventDefault(){}});await waiting;
  f.context.prompt=()=> 'other.md';await f.el('newFileButton').onclick();release();await sending;
  const review=f.buttons(f.el('chat')).find(n=>n.textContent.startsWith('Review block'));assert.match(review.textContent,/README.md/);
  review.click();assert.equal(f.el('applyDialog').open,false);assert.equal(f.el('editor').value,'');
  await f.run('selectFile("README.md")');review.click();assert.equal(f.el('applyDialog').open,true);
  f.edit('Newer edits');f.el('confirmApply').click();assert.equal(f.el('editor').value,'Newer edits');assert.match(f.el('toast').textContent,/file changed/);
  f.edit('Original README');f.el('confirmApply').click();assert.equal(f.el('editor').value,'Replacement');assert.equal(f.run('state.dirty'),true);
});

test('model transport retry replays one charge and follow-ups include conversation history',async t=>{
  const f=await fixture(t);await f.approve();const fetch=f.context.fetch;let drop=true;const bodies=[],ids=[];
  f.context.fetch=async(path,opts)=>{const response=await fetch(path,opts);if(path==='/v1/chat/completions'){bodies.push(opts.body);ids.push(opts.headers['Idempotency-Key']);if(drop){drop=false;throw Error('Response lost');}}return response;};
  f.el('prompt').value='Fix the file';await f.el('promptForm').onsubmit({preventDefault(){}});assert.equal(f.calls,1);
  await f.buttons(f.el('chat')).find(n=>n.textContent==='Retry same request').click();assert.equal(f.calls,1);assert.equal(ids[0],ids[1]);assert.equal(bodies[0],bodies[1]);assert.equal(f.run('state.account.available_tokens'),999850);
  f.el('prompt').value='Explain that change';await f.el('promptForm').onsubmit({preventDefault(){}});
  const messages=JSON.parse(bodies[2]).messages;assert.equal(messages[1].content,'Fix the file');assert.equal(messages[2].role,'assistant');assert.equal(f.calls,2);
});

test('truncated model output and oversized file context cannot replace a whole file',async t=>{
  const f=await fixture(t);await f.approve();f.edit('x'.repeat(40000));f.el('prompt').value='Fix this';
  assert.equal(f.run('preparePrompt("Fix this").target'),null);
  f.env.UPSTREAM.fetch=async()=>Response.json({choices:[{message:{content:'```js\npartial\n```'},finish_reason:'length'}],usage:{prompt_tokens:5,completion_tokens:5}});
  await f.el('promptForm').onsubmit({preventDefault(){}});assert.equal(f.buttons(f.el('chat')).filter(n=>n.textContent.startsWith('Review block')).length,0);
});
