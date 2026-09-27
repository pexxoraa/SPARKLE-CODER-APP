import {test} from 'node:test';
import assert from 'node:assert/strict';
import {D1} from './helpers.mjs';
import worker, {cleanup} from '../src/worker.mjs';

function fixture(){
 const env={DB:new D1(),ADMIN_SECRET:'A'.repeat(64),CACHE_SECRET:'B'.repeat(64),UPI_ID:'owner@bank',PAYEE_NAME:'Pilot owner',NVIDIA_API_KEY:'private-provider-test-key',MAX_MEMBERS:'50',MAX_INFLIGHT:'3'};
 let calls=0;env.UPSTREAM={fetch:async(url,options)=>{calls++;assert.equal(url,'https://integrate.api.nvidia.com/v1/chat/completions');assert.equal(options.headers.Authorization,'Bearer '+env.NVIDIA_API_KEY);
  return Response.json({choices:[{message:{role:'assistant',content:'Created the page.'},finish_reason:'stop'}],usage:{prompt_tokens:120,completion_tokens:30}});}};
 const device='device_'+crypto.randomUUID().replaceAll('-','')+'A'.repeat(20);
 let cookie='';
 async function api(path,data,{secret=device,admin=false,origin,extra={}}={}){
  const headers={'CF-Connecting-IP':'192.0.2.1',...extra};
  if(secret)headers.Authorization='Bearer '+secret;
  if(data!==undefined)headers['Content-Type']='application/json';
  if(admin){headers.Cookie=cookie;headers.Origin='https://sparkle.example';}
  if(origin!==undefined)headers.Origin=origin;
  const response=await worker.fetch(new Request('https://sparkle.example'+path,{method:data===undefined?'GET':'POST',headers,body:data===undefined?undefined:JSON.stringify(data)}),env);
  if(response.headers.has('Set-Cookie'))cookie=response.headers.get('Set-Cookie').split(';')[0];
  const result=await response.json();return {status:response.status,body:result,headers:response.headers};
 }
 async function enroll(email='tester@example.com',secret=device){const r=await api('/api/enroll',{name:'Test user',email,phone:'1234567890',password:'TestPass123!',consent:true},{secret});assert.equal(r.status,201);return r.body;}
 async function login(){const r=await api('/api/admin/login',{password:env.ADMIN_SECRET},{admin:true,secret:null});assert.equal(r.status,200);assert.match(r.headers.get('Set-Cookie'),/HttpOnly; SameSite=Strict/);}
 async function approve(){await enroll();await login();const payment=await api('/api/payments',{utr:'UPI1234567890',credits:999999999,amount_paise:1});assert.equal(payment.status,201);
  const r=await api('/api/admin/payments/'+payment.body.id,{action:'approve',verified:true},{admin:true});assert.equal(r.status,200);return payment.body.id;}
 const payload={messages:[{role:'user',content:'Build a flower shop landing page'}],max_tokens:4096};
 const infer=(id='request_1234567890',data=payload,options={})=>api('/v1/chat/completions',data,{...options,extra:{'Idempotency-Key':id}});
 return {env,api,enroll,login,approve,infer,device,payload,get calls(){return calls;}};
}
test('registration, manual payment approval, exact credit pack and no double credit',async()=>{
 const f=fixture(),id=await f.approve();let me=(await f.api('/api/me')).body;
 assert.equal(me.balance_tokens,1000000);assert.equal(me.available_tokens,1000000);assert.equal(me.ready,true);
 assert.equal(me.payments[0].amount_paise,1500);assert.equal(me.payments[0].credits,1000000);
 const second=await f.api('/api/admin/payments/'+id,{action:'approve',verified:true},{admin:true});assert.equal(second.body.already_reviewed,true);
 assert.equal((await f.api('/api/me')).body.balance_tokens,1000000);
 assert.equal(f.env.DB.db.prepare('SELECT COUNT(*) AS n FROM ledger').get().n,1);
});
test('signup receipt appears in admin before payment and retry cannot duplicate it',async()=>{
 const f=fixture(),receipt=await f.enroll();await f.login();
 assert.equal(receipt.name,'Test user');assert.equal(receipt.ready,false);assert.equal(receipt.balance_tokens,0);
 assert.ok(receipt.request_id);assert.ok(receipt.requested_at>0);
 let overview=(await f.api('/api/admin/overview',undefined,{admin:true})).body;
 assert.equal(overview.payments.length,0);assert.equal(overview.devices.length,1);
 assert.equal(overview.devices[0].id,receipt.request_id);assert.equal(overview.devices[0].account_id,receipt.id);
 assert.equal(overview.devices[0].created,receipt.requested_at);assert.equal(overview.devices[0].kind,'signup');
 assert.equal(overview.devices[0].email,'tester@example.com');assert.equal(overview.devices[0].account_status,'pending');
 assert.equal(overview.audit[0].action,'account-requested');assert.equal(overview.audit[0].reference,receipt.request_id);
 assert.ok(!JSON.stringify(overview).includes(f.device));assert.ok(!JSON.stringify(overview).includes('secret_hash'));
 const retry=await f.api('/api/enroll',{name:'Test user',email:'tester@example.com',password:'TestPass123!',consent:true});
 assert.equal(retry.status,200);assert.equal(retry.body.request_id,receipt.request_id);
 overview=(await f.api('/api/admin/overview',undefined,{admin:true})).body;
 assert.equal(overview.accounts.length,1);assert.equal(overview.devices.length,1);assert.equal(overview.audit.length,1);
 const payment=await f.api('/api/payments',{utr:'VISIBLE12345678'});
 await f.api('/api/admin/payments/'+payment.body.id,{action:'approve',verified:true},{admin:true});
 assert.equal((await f.api('/api/admin/overview',undefined,{admin:true})).body.devices.length,0);
 assert.equal((await f.api('/api/me')).body.available_tokens,1000000);
});
test('database write failure never returns a signup receipt or a false capacity error',async()=>{
 const f=fixture();
 f.env.DB.db.exec("CREATE TRIGGER fail_account_audit BEFORE INSERT ON audit WHEN NEW.action='account-requested' BEGIN SELECT RAISE(ABORT,'Simulated storage failure'); END");
 const result=await f.api('/api/enroll',{name:'Test user',email:'tester@example.com',password:'TestPass123!',consent:true});
 assert.equal(result.status,500);assert.ok(!result.body.request_id);assert.doesNotMatch(result.body.error,/full|registered/);
 for(const table of ['accounts','devices','audit'])assert.equal(f.env.DB.db.prepare('SELECT COUNT(*) AS n FROM '+table).get().n,0);
});
test('pending accounts cannot infer and approval requires bank verification',async()=>{
 const f=fixture();await f.enroll();assert.equal((await f.infer()).status,403);await f.login();
 const payment=await f.api('/api/payments',{utr:'123456789012'});
 assert.equal((await f.api('/api/admin/payments/'+payment.body.id,{action:'approve'},{admin:true})).status,400);
 assert.equal((await f.api('/api/me')).body.balance_tokens,0);assert.equal(f.calls,0);
});
test('credits use confirmed input + output usage; identical retry does not call or charge again',async()=>{
 const f=fixture();await f.approve();const result=await f.infer();assert.equal(result.status,200);
 let me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,999850);assert.equal(me.held_tokens,0);
 const second=await f.infer();assert.equal(second.status,200);assert.equal(second.headers.get('X-Sparkle-Replayed'),'true');assert.equal(f.calls,1);
 assert.equal((await f.api('/api/me')).body.balance_tokens,999850);
 const row=f.env.DB.db.prepare('SELECT * FROM requests').get();assert.equal(row.charged,150);assert.ok(!row.response_cipher.includes('Created the page'));
 assert.equal((await f.infer('request_1234567890',{messages:[{role:'user',content:'Different request'}]})).status,409);
});
test('concurrent use holds credits atomically and duplicate requests do not trigger two calls',async()=>{
 const f=fixture();await f.approve();let release,entered;
 const waiting=new Promise(r=>{entered=r;});f.env.UPSTREAM.fetch=async()=>{entered();await new Promise(r=>{release=r;});return Response.json({choices:[],usage:{prompt_tokens:100,completion_tokens:10}});};
 const first=f.infer();await waiting;
 assert.ok((await f.api('/api/me')).body.held_tokens>0);
 assert.equal((await f.infer()).status,409);assert.equal((await f.infer('request_other_123456')).status,429);
 release();assert.equal((await first).status,200);assert.equal((await f.api('/api/me')).body.balance_tokens,999890);
});
test('missing provider usage holds funds for reconciliation without inventing a charge',async()=>{
 const f=fixture();await f.approve();f.env.UPSTREAM.fetch=async()=>Response.json({choices:[]});
 assert.equal((await f.infer()).status,502);let me=(await f.api('/api/me')).body;
 assert.equal(me.balance_tokens,1000000);assert.ok(me.held_tokens>0);assert.equal(me.ledger.length,1);
 const held=me.held_tokens;
 f.env.UPSTREAM.fetch=async()=>Response.json({choices:[{message:{role:'assistant',content:'OK'}}],usage:{prompt_tokens:10,completion_tokens:5}});
 assert.equal((await f.infer('another_request_12345')).status,200);
 me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,999985);assert.equal(me.held_tokens,held);
 const resolve=await f.api('/api/admin/requests/request_1234567890',{verified:true,charged_tokens:25,note:'Confirmed against provider usage record'},{admin:true});assert.equal(resolve.status,200);
 me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,999960);assert.equal(me.held_tokens,0);
 assert.equal((await f.api('/api/admin/requests/request_1234567890',{verified:true,charged_tokens:25,note:'Try duplicate charge'},{admin:true})).status,409);
});
test('uncertain holds cannot accumulate without limit or be charged by retrying',async()=>{
 const f=fixture();await f.approve();let upstreamCalls=0;
 f.env.UPSTREAM.fetch=async()=>{upstreamCalls++;return Response.json({choices:[]});};
 for(let i=0;i<3;i++)assert.equal((await f.infer('uncertain_request_'+i)).status,502);
 const before=(await f.api('/api/me')).body;
 assert.equal((await f.infer('uncertain_request_0')).status,409);
 const blocked=await f.infer('fourth_uncertain_request');assert.equal(blocked.status,409);assert.match(blocked.body.error,/Three model requests/);
 const after=(await f.api('/api/me')).body;
 assert.equal(upstreamCalls,3);assert.equal(after.held_tokens,before.held_tokens);assert.equal(after.balance_tokens,1000000);
});
test('owner AI diagnostic requires admin access and does not change member billing',async()=>{
 const f=fixture();await f.approve();const before=(await f.api('/api/me')).body;
 assert.equal((await f.api('/api/admin/model-check',{})).status,401);
 const result=await f.api('/api/admin/model-check',{}, {admin:true});
 assert.equal(result.status,200);assert.equal(result.body.ok,true);assert.equal(result.body.prompt_tokens,120);
 const after=(await f.api('/api/me')).body;assert.equal(after.balance_tokens,before.balance_tokens);assert.equal(after.held_tokens,0);
 assert.equal(f.env.DB.db.prepare('SELECT COUNT(*) AS n FROM requests').get().n,0);
 assert.ok(!JSON.stringify(result.body).includes(f.env.NVIDIA_API_KEY));
});
test('rejected provider calls release holds and shared NVIDIA key never reaches users',async()=>{
 const f=fixture();await f.approve();f.env.UPSTREAM.fetch=async()=>new Response('secret '+f.env.NVIDIA_API_KEY,{status:401});
 const result=await f.infer();assert.equal(result.status,502);assert.ok(!JSON.stringify(result).includes(f.env.NVIDIA_API_KEY));
 const me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,1000000);assert.equal(me.held_tokens,0);
});
test('explicit provider 5xx releases the hold and permits a fresh safe retry',async()=>{
 const f=fixture();await f.approve();f.env.UPSTREAM.fetch=async()=>new Response('temporary failure',{status:500});
 const result=await f.infer();assert.equal(result.status,502);
 assert.equal(result.headers.get('X-Sparkle-Safe-Retry'),'true');assert.equal(result.headers.get('Retry-After'),'2');
 const me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,1000000);assert.equal(me.held_tokens,0);
 const row=f.env.DB.db.prepare('SELECT state,charged,note FROM requests').get();
 assert.equal(row.state,'failed');assert.equal(row.charged,0);assert.match(row.note,/HTTP 500/);
});
test('no cross-account response, payment or admin access; CSRF and logout protection',async()=>{
 const f=fixture();await f.approve();assert.equal((await f.api('/api/admin/overview')).status,401);
 assert.equal((await f.api('/api/admin/overview',undefined,{admin:true,origin:'https://evil.example'})).status,403);
 const other='other_'+crypto.randomUUID().replaceAll('-','')+'C'.repeat(20);await f.enroll('other@example.com',other);
 assert.equal((await f.api('/api/payments',{utr:'UPI1234567890'},{secret:other})).status,409);
 assert.equal((await f.api('/api/admin/logout',{}, {admin:true})).status,200);
 assert.equal((await f.api('/api/admin/overview',undefined,{admin:true})).status,401);
});
test('account suspension, exhausted balance and invalid model cannot reach provider',async()=>{
 const f=fixture();const account=await f.enroll();await f.login();
 f.env.DB.db.prepare("UPDATE accounts SET status='active' WHERE id=?").run(account.id);
 f.env.DB.db.prepare("UPDATE devices SET status='active'").run();
 assert.equal((await f.infer()).status,402);assert.equal((await f.infer('a_request_123456789',{...f.payload,model:'other-model'})).status,400);
 assert.equal((await f.api('/api/admin/accounts/'+account.id,{status:'suspended'},{admin:true})).status,200);
 assert.equal((await f.infer()).status,403);assert.equal(f.calls,0);
});
test('device recovery is manually approved and does not expose balance or grant more credits',async()=>{
 const f=fixture();await f.approve();const replacement='new_'+crypto.randomUUID().replaceAll('-','')+'D'.repeat(20);
 const registered=await f.api('/api/enroll',{name:'New device',email:'tester@example.com',consent:true,recovery:true},{secret:replacement});
 assert.equal(registered.status,201);assert.equal(registered.body.balance_tokens,0);
 assert.equal((await f.api('/api/payments',{utr:'RECOVER1234567'},{secret:replacement})).status,403);
 const overview=(await f.api('/api/admin/overview',undefined,{admin:true})).body;
 const recover=overview.devices.find(x=>x.kind==='recovery');
 assert.equal((await f.api('/api/admin/devices/'+recover.id,{action:'approve',verified:true},{admin:true})).status,200);
 assert.equal((await f.api('/api/me',undefined,{secret:replacement})).body.balance_tokens,1000000);
 assert.equal((await f.api('/api/me')).status,401);
});
test('approved account signs in on a new device with password and creates no admin request',async()=>{
 const f=fixture();await f.approve();const replacement='login_'+crypto.randomUUID().replaceAll('-','')+'L'.repeat(20);
 const signed=await f.api('/api/login',{email:'tester@example.com',password:'TestPass123!'},{secret:replacement});
 assert.equal(signed.status,200);assert.equal(signed.body.ready,true);assert.equal(signed.body.device_status,'active');
 assert.equal(signed.body.balance_tokens,1000000);
 const wrongSecret='wrong_'+crypto.randomUUID().replaceAll('-','')+'W'.repeat(20);
 const wrong=await f.api('/api/login',{email:'tester@example.com',password:'WrongPass123!'},{secret:wrongSecret});
 assert.equal(wrong.status,401);
 const overview=(await f.api('/api/admin/overview',undefined,{admin:true})).body;
 assert.equal(overview.devices.filter(x=>x.kind==='recovery').length,0);
 assert.equal(f.env.DB.db.prepare("SELECT COUNT(*) AS n FROM devices WHERE account_id=? AND status='active'").get(signed.body.id).n,2);
});
test('legacy active account must create a password before coding or buying, then can sign in without admin review',async()=>{
 const f=fixture();await f.approve();f.env.DB.db.prepare('DELETE FROM account_credentials').run();
 let me=(await f.api('/api/me')).body;assert.equal(me.password_set,false);assert.equal(me.password_required,true);assert.equal(me.ready,false);
 assert.equal((await f.api('/v1/balance')).status,428);
 assert.equal((await f.api('/api/payments',{utr:'LEGACYBUY12345'})).status,428);
 const saved=await f.api('/api/account/password',{password:'LegacyPass123!'});assert.equal(saved.status,200);
 me=(await f.api('/api/me')).body;assert.equal(me.password_set,true);assert.equal(me.password_required,false);assert.equal(me.ready,true);
 const replacement='legacy_'+crypto.randomUUID().replaceAll('-','')+'Q'.repeat(20);
 const signed=await f.api('/api/login',{email:'tester@example.com',password:'LegacyPass123!'},{secret:replacement});
 assert.equal(signed.status,200);assert.equal(signed.body.ready,true);
 const overview=(await f.api('/api/admin/overview',undefined,{admin:true})).body;
 assert.equal(overview.devices.filter(x=>x.kind==='recovery').length,0);
});
test('coupon adds bonus tokens only after verified payment and enforces account use limit',async()=>{
 const f=fixture();await f.approve();await f.login();
 const created=await f.api('/api/admin/coupons',{code:'BONUS250',bonus_tokens:250000,discount_paise:500,max_uses:3,one_per_account:true,expires:Math.floor(Date.now()/1000)+3600,note:'Pilot bonus'},{admin:true});
 assert.equal(created.status,201);assert.equal(created.body.code,'BONUS250');assert.equal(created.body.discount_paise,500);
 const quote=await f.api('/api/coupons/quote',{code:'bonus250'});assert.equal(quote.status,200);assert.equal(quote.body.bonus_tokens,250000);assert.equal(quote.body.final_amount_paise,1000);
 const payment=await f.api('/api/payments',{utr:'COUPONPAY12345',coupon_code:'bonus250'});assert.equal(payment.status,201);
 assert.equal(payment.body.amount_paise,1000);assert.equal(payment.body.discount_paise,500);assert.equal(payment.body.total_credits,1250000);
 assert.equal((await f.api('/api/me')).body.balance_tokens,1000000);
 const approved=await f.api('/api/admin/payments/'+payment.body.id,{action:'approve',verified:true},{admin:true});assert.equal(approved.status,200);
 const me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,2250000);
 assert.equal(me.ledger.filter(x=>x.kind==='coupon').length,1);
 assert.equal((await f.api('/api/coupons/quote',{code:'BONUS250'})).status,409);
 const overview=(await f.api('/api/admin/overview',undefined,{admin:true})).body;
 const coupon=overview.coupons.find(x=>x.code==='BONUS250');assert.equal(coupon.redeemed_uses,1);assert.equal(coupon.reserved_uses,1);
});
test('money-only and 100 percent coupons change the payable amount without inventing bonus tokens',async()=>{
 const f=fixture();await f.approve();await f.login();
 let created=await f.api('/api/admin/coupons',{code:'SAVE5',bonus_tokens:0,discount_paise:500,max_uses:2,one_per_account:true,expires:Math.floor(Date.now()/1000)+3600,note:'₹5 off'},{admin:true});
 assert.equal(created.status,201);
 let quote=await f.api('/api/coupons/quote',{code:'SAVE5'});assert.equal(quote.body.final_amount_paise,1000);assert.equal(quote.body.bonus_tokens,0);
 let payment=await f.api('/api/payments',{utr:'SAVEFIVE12345',coupon_code:'SAVE5'});assert.equal(payment.status,201);assert.equal(payment.body.amount_paise,1000);
 await f.api('/api/admin/payments/'+payment.body.id,{action:'approve',verified:true},{admin:true});
 let me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,2000000);assert.equal(me.ledger.filter(x=>x.kind==='coupon').length,0);
 created=await f.api('/api/admin/coupons',{code:'FREEPACK',bonus_tokens:0,discount_paise:1500,max_uses:1,one_per_account:true,expires:Math.floor(Date.now()/1000)+3600,note:'100% off'},{admin:true});
 assert.equal(created.status,201);
 quote=await f.api('/api/coupons/quote',{code:'FREEPACK'});assert.equal(quote.body.final_amount_paise,0);
 payment=await f.api('/api/payments',{utr:'',coupon_code:'FREEPACK'});assert.equal(payment.status,201);assert.equal(payment.body.amount_paise,0);assert.equal(payment.body.payment_required,false);
 assert.match(f.env.DB.db.prepare('SELECT utr FROM payments_v2 WHERE id=?').get(payment.body.id).utr,/^FREE/);
 await f.api('/api/admin/payments/'+payment.body.id,{action:'approve',verified:true},{admin:true});
 me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,3000000);
});
test('rejected coupon payment releases its use and expired coupons are refused',async()=>{
 const f=fixture();await f.approve();await f.login();
 const created=await f.api('/api/admin/coupons',{code:'ONCE10',bonus_tokens:10000,max_uses:1,one_per_account:true,expires:Math.floor(Date.now()/1000)+3600,note:''},{admin:true});
 assert.equal(created.status,201);
 const payment=await f.api('/api/payments',{utr:'COUPONREJECT123',coupon_code:'ONCE10'});assert.equal(payment.status,201);
 assert.equal((await f.api('/api/coupons/quote',{code:'ONCE10'})).status,409);
 await f.api('/api/admin/payments/'+payment.body.id,{action:'reject',note:'Bank payment not found'},{admin:true});
 assert.equal((await f.api('/api/coupons/quote',{code:'ONCE10'})).status,200);
 const updated=await f.api('/api/admin/coupons/'+created.body.id,{bonus_tokens:10000,max_uses:1,one_per_account:true,expires:Math.floor(Date.now()/1000)-1,active:true,note:'expired'},{admin:true});
 assert.equal(updated.status,200);
 assert.equal((await f.api('/api/coupons/quote',{code:'ONCE10'})).status,400);
});
test('pilot capacity, UPI setup and oversized requests fail closed',async()=>{
 const f=fixture();f.env.MAX_MEMBERS='1';await f.enroll();f.env.UPI_ID='';
 assert.equal((await f.api('/api/payments',{utr:'123456789012'})).status,503);
 const other='member_'+crypto.randomUUID().replaceAll('-','')+'E'.repeat(20);
 assert.equal((await f.api('/api/enroll',{name:'Other',email:'other@example.com',password:'OtherPass123!',consent:true},{secret:other})).status,409);
 assert.equal((await f.api('/api/enroll',{name:'A'.repeat(20000),email:'a@b.co',password:'OtherPass123!',consent:true},{secret:other})).status,413);
 assert.equal(f.env.DB.db.prepare('SELECT COUNT(*) AS n FROM accounts').get().n,1);
});
test('ledger cannot be edited and concurrent approval credits exactly once',async()=>{
 const f=fixture();await f.enroll();await f.login();const p=await f.api('/api/payments',{utr:'123456789012'});
 const responses=await Promise.all([1,2].map(()=>f.api('/api/admin/payments/'+p.body.id,{action:'approve',verified:true},{admin:true})));
 assert.ok(responses.every(x=>x.status===200));assert.equal((await f.api('/api/me')).body.balance_tokens,1000000);
 assert.throws(()=>f.env.DB.db.exec('DELETE FROM ledger'),/immutable/);
});
test('an approved second account cannot replay another account response',async()=>{
 const f=fixture();await f.approve();await f.infer();
 const other='second_'+crypto.randomUUID().replaceAll('-','')+'Z'.repeat(20);await f.enroll('second@example.com',other);
 const p=await f.api('/api/payments',{utr:'SECOND12345678'},{secret:other});
 await f.api('/api/admin/payments/'+p.body.id,{action:'approve',verified:true},{admin:true});
 assert.equal((await f.infer('request_1234567890',f.payload,{secret:other})).status,409);
 assert.equal((await f.api('/api/me',undefined,{secret:other})).body.balance_tokens,1000000);assert.equal(f.calls,1);
});
test('scheduled cleanup expires response content and flags abandoned holds without charging',async()=>{
 const f=fixture();await f.approve();await f.infer();const stamp=Math.floor(Date.now()/1000);
 f.env.DB.db.prepare('UPDATE requests SET completed=?').run(stamp-1800);
 const account=(await f.api('/api/me')).body.id;
 f.env.DB.db.prepare("INSERT INTO requests(id,account_id,payload_hash,reserve,state,created) VALUES ('abandoned',?,'test',100,'inflight',?)").run(account,stamp-1000);
 await cleanup(f.env);
 assert.equal(f.env.DB.db.prepare('SELECT response_cipher FROM requests WHERE id=?').get('request_1234567890').response_cipher,null);
 assert.equal(f.env.DB.db.prepare('SELECT state FROM requests WHERE id=?').get('abandoned').state,'uncertain');
 const a=(await f.api('/api/me')).body;assert.equal(a.balance_tokens,999850);assert.equal(a.held_tokens,100);
});
test('payment trigger rolls back payment and ledger when the account is suspended',async()=>{
 const f=fixture();const account=await f.enroll();const payment=await f.api('/api/payments',{utr:'SUSPEND12345678'});
 const db=f.env.DB.db;db.prepare("UPDATE accounts SET status='suspended' WHERE id=?").run(account.id);
 assert.throws(()=>db.prepare("UPDATE payments_v2 SET status='approved',reviewed=1 WHERE id=?").run(payment.body.id),/Account is suspended/);
 assert.equal(db.prepare('SELECT status FROM payments_v2').get().status,'pending');
 assert.equal(db.prepare('SELECT balance FROM accounts').get().balance,0);
 assert.equal(db.prepare('SELECT status FROM devices').get().status,'pending');
 assert.equal(db.prepare('SELECT COUNT(*) AS n FROM ledger').get().n,0);
});
test('settlement exceeding the reservation rolls back without losing the hold or charging',async()=>{
 const f=fixture();await f.approve();const account=(await f.api('/api/me')).body.id,db=f.env.DB.db;
 db.prepare("INSERT INTO requests(id,account_id,payload_hash,reserve,state,created) VALUES ('guard-test',?,'hash',100,'inflight',1)").run(account);
 assert.throws(()=>db.exec("UPDATE requests SET state='succeeded',charged=101,completed=2 WHERE id='guard-test'"),/Usage exceeds reservation/);
 let me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,1000000);assert.equal(me.held_tokens,100);
 assert.equal(db.prepare("SELECT state FROM requests WHERE id='guard-test'").get().state,'inflight');
 assert.equal(db.prepare('SELECT COUNT(*) AS n FROM ledger').get().n,1);
 db.exec("UPDATE requests SET state='succeeded',charged=100,completed=2 WHERE id='guard-test'");
 me=(await f.api('/api/me')).body;assert.equal(me.balance_tokens,999900);assert.equal(me.held_tokens,0);
 db.exec("UPDATE requests SET state='succeeded' WHERE id='guard-test'");
 assert.equal(db.prepare('SELECT COUNT(*) AS n FROM ledger').get().n,2);
});
