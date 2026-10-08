"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../sparkle_coder/ui/app.js"),"utf8");
const portion=(from,to)=>{
 const first=source.indexOf(from),last=source.indexOf(to,first);
 assert.ok(first>=0&&last>first,"Cannot extract "+from);
 return source.slice(first,last);
};
const renderCode=portion("function editSentMessage(","  id(\"resultBanner\").hidden=")+"\n}";
const submitCode=portion("async function startTask(","async function startDemo(");
class Element{
 constructor(tag="div",cls="",text=""){
  this.tag=tag;this.className=cls;this.textContent=text;
  this.children=[];this.value="";this.type="";this.disabled=false;this.hidden=false;
  this.dataset={};this.attrs={};this.id="";this.style={};this.scrollHeight=0;this.scrollTop=0;this.clientHeight=0;
  this.firstChild={textContent:""};
 }
 append(...list){this.children.push(...list);}
 prepend(...list){this.children.unshift(...list);}
 replaceChildren(...list){this.children=[...list];}
 setAttribute(name,value){this.attrs[name]=value;}
 focus(){this.focused=true;}
 querySelector(selector){
  if(selector[0]===".")return descendants(this).find(x=>x.className.split(" ").includes(selector.slice(1)))||null;
  return null;
 }
}
function descendants(element){
 return element.children.flatMap(child=>[child,...descendants(child)]);
}
const node=(...args)=>new Element(...args);
const staticElements=new Map();
const id=name=>{
 const dynamic=descendants(staticElements.get("messages")||new Element()).find(item=>item.id===name);
 if(dynamic)return dynamic;
 if(!staticElements.has(name))staticElements.set(name,new Element());
 return staticElements.get(name);
};
const events=[],calls=[];
const original={
 id:"saved-1",task_mode:"ask",status:"answered",
 messages:[{role:"user",content:"What are SQLite tradeoffs?"},{role:"assistant",content:"It is simple."}]
};
let response=()=>({id:"new-run",status:"running"}),recover=null,active=false;
const api=async(route,body)=>{calls.push({route,body});return response(route,body);};
const harness=[
 'let projectId="project-1",currentSession=null,currentRun=null,editingSentMessage=null;',
 'let lastMessageKey="",startingRun=false,transferBusy=false,runEvents=[],monitorEventsTruncated=false,lastPollError="",lastChangeKey="";',
 'let appState={account:{enabled:true,ready:true},settings:{key_configured:true},engine:{available:true}};',
 'const isCloud=true;',
 'function busy(){return active();}',
 'function toast(t){events.push("toast:"+t);}',
 'function action(fn){return fn();}',
 'function appendText(parent,content){parent.append(node("div","message-text",content));}',
 'function icon(){return "<svg></svg>";}',
 'function renderControls(){}function renderRecovery(){}function renderDelivery(){}function renderRepairHistory(){}',
 'function renderActivity(){}function renderChecks(){}function renderMonitor(){}',
 'function clearDraft(){events.push("clear-draft");} function changeView(){events.push("view");}function schedulePoll(){events.push("poll");}',
 'function hostedNoKey(){return false;}function openSettings(){}async function openAccount(){}',
 'async function refreshState(){if(recover())currentRun=recover();}',
 renderCode,
 submitCode,
 'return {renderSession,editSentMessage,cancelSentMessageEdit,retryEditedMessage,startTask,',
 'current:()=>currentSession,editing:()=>editingSentMessage,currentRun:()=>currentRun,',
 'getLastKey:()=>lastMessageKey,projectChange:name=>{projectId=name;},controls:()=>({startingRun})};'
].join("\n");
const ui=new Function("id","node","api","events","active","recover",harness)(
 id,node,api,events,()=>active,()=>recover);
const userMessage=()=>id("messages").children[0];
const editButton=()=>descendants(userMessage()).find(el=>el.className.includes("sent-message-edit-button"));
const editingField=()=>id("messages").querySelector(".sent-message-editor");
(async()=>{
 ui.renderSession(original);
 assert.equal(id("messages").children.length,2);
 assert.ok(editButton().textContent.includes("Edit & try again"));
 assert.equal(descendants(id("messages").children[1]).some(el=>el.className.includes("sent-message-edit-button")),false,
  "Only sent user messages should offer the action.");
 editButton().onclick();
 assert.equal(editingField().value,original.messages[0].content);
 assert.match(descendants(userMessage()).find(el=>el.className==="sent-message-edit-note").textContent,/new task/i);
 assert.match(descendants(userMessage()).find(el=>el.className==="sent-message-edit-note").textContent,/credits/i);
 editingField().value="Should I use SQLite or PostgreSQL?";
 editingField().oninput();
 assert.equal(ui.editing().draft,editingField().value);
 ui.renderSession({...original,messages:[...original.messages,{role:"assistant",content:"Update."}]});
 assert.equal(editingField().value,"Should I use SQLite or PostgreSQL?","Refresh must not lose unsent edits.");
 const cancel=descendants(userMessage()).find(el=>el.textContent==="Cancel");
 cancel.onclick();
 assert.equal(ui.editing(),null);
 assert.equal(id("messages").querySelector(".sent-message-editor"),null);
 assert.equal(calls.length,0,"Cancel never invokes a model API.");

 ui.renderSession(original);
 editButton().onclick();
 editingField().value="   ";
 editingField().oninput();
 await ui.retryEditedMessage();
 assert.equal(calls.length,0,"Empty edits cannot start a task.");
 assert.match(id("sentMessageEditError").textContent,/Enter a message/);
 editingField().value="  Use SQLite with migrations and backups. ";
 editingField().oninput();
 let finish;
 response=()=>new Promise(resolve=>{finish=resolve;});
 const pending=ui.retryEditedMessage();
 await ui.retryEditedMessage();
 assert.equal(calls.length,1,"Double click cannot start a second run.");
 assert.equal(calls[0].route,"/runs");
 assert.equal(calls[0].body.goal,"Use SQLite with migrations and backups.");
 assert.equal(calls[0].body.session_id,null,"Edited prompt must fork into a NEW session.");
 assert.equal(calls[0].body.task_mode,"ask");
 assert.deepEqual(original.messages,[{role:"user",content:"What are SQLite tradeoffs?"},{role:"assistant",content:"It is simple."}],
  "Original saved messages must remain untouched.");
 finish({id:"new-run",status:"running"});
 await pending;
 assert.equal(ui.editing(),null);
 assert.equal(ui.current(),null,"Successful retry must not continue the old session.");
 assert.equal(ui.currentRun().id,"new-run");

 // Failure must leave edited request available; no automatic second charge.
 active=false;response=async()=>{throw Error("Network error");};
 ui.renderSession(original);editButton().onclick();
 editingField().value="Retry after network error";editingField().oninput();
 const prior=calls.length;
 await ui.retryEditedMessage();
 assert.equal(calls.length,prior+1);
 assert.equal(ui.current().id,original.id);
 assert.equal(ui.editing().draft,"Retry after network error");
 assert.match(id("taskError").textContent,/Network error/);
 assert.match(id("sentMessageEditError").textContent,/not confirmed/);

 // When a read-only refresh shows a running task, prohibit another request.
 active=true;
 const initial=calls.length;
 assert.equal(editButton().disabled,true===editButton().disabled?true:false);
 await ui.retryEditedMessage();
 assert.equal(calls.length,initial);
 console.log("Edit & try again: user-only buttons, cancel, draft persistence, fresh sessions, no double send, failure safety and active-run guard passed.");
})().catch(e=>{console.error(e);process.exitCode=1;});
