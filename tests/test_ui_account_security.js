"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../sparkle_coder/ui/app.js"),"utf8");
assert.match(source,/id="currentAccountPasswordRow" hidden/);
assert.match(source,/autocomplete="current-password"/);
assert.match(source,/id\('currentAccountPasswordRow'\)\.hidden=!a\.password_set/);
assert.match(source,/id\('currentAccountPassword'\)\.required=!!a\.password_set/);
assert.match(source,/id\('passwordSection'\)\.hidden=!a\.enrolled\|\|a\.device_status!=='active'/);

const code=source.slice(source.indexOf("id('passwordForm').onsubmit="),
  source.indexOf("id('legacySetupForm').onsubmit="));
assert.ok(code.startsWith("id('passwordForm').onsubmit="));
const elements=new Map(),requests=[],messages=[],errors=[];
const id=name=>{
  if(!elements.has(name))elements.set(name,{value:"",onsubmit:null});
  return elements.get(name);
};
let appState={account:{password_set:true}},rendered=0,refreshed=0;
const api=async(_url,payload)=>{
  requests.push(payload);
  if(payload.password==="reject_this_password")throw Error("Server refused password");
  return {ready:true,password_set:true};
};
const action=fn=>Promise.resolve().then(fn).catch(error=>errors.push(error.message));
const setup=new Function("id","api","action","appState","renderAccount",
  "refreshState","toast",code+";return id('passwordForm').onsubmit;");
const initialize=()=>setup(id,api,action,appState,()=>rendered++,
  async()=>refreshed++,text=>messages.push(text));
const submit=async()=>{
  const handler=initialize();
  handler({preventDefault(){}});
  await new Promise(resolve=>setImmediate(resolve));
};
(async()=>{
  id("newAccountPassword").value="NewPass123!";
  id("currentAccountPassword").value="ExistingPass123!";
  await submit();
  assert.deepEqual(requests[0],{password:"NewPass123!",current_password:"ExistingPass123!"});
  assert.equal(id("newAccountPassword").value,"");
  assert.equal(id("currentAccountPassword").value,"");
  assert.equal(rendered,1);assert.equal(refreshed,1);
  assert.match(messages.at(-1),/Other devices must sign in again/);

  appState.account={password_set:false};
  id("newAccountPassword").value="LegacyNewPass123!";
  id("currentAccountPassword").value="";
  await submit();
  assert.deepEqual(requests[1],{password:"LegacyNewPass123!"},'first-time setup must not demand nonexistent current password');

  appState.account={password_set:true};
  id("newAccountPassword").value="reject_this_password";
  id("currentAccountPassword").value="bad password";
  const previousMessages=messages.length;
  await submit();
  assert.equal(messages.length,previousMessages,"a rejected change must not display success");
  assert.equal(errors.at(-1),"Server refused password");
  assert.equal(id("currentAccountPassword").value,"");
  assert.equal(id("newAccountPassword").value,"");
  console.log("Account security UI: verified current-password forwarding, first-time setup, error handling and sensitive-field clearing.");
})().catch(error=>{console.error(error);process.exitCode=1;});
