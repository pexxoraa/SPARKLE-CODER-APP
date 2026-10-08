"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const code=fs.readFileSync(path.join(__dirname,"../sparkle_coder/ui/app.js"),"utf8");
assert.match(code,/id="taskSnapshot"[^>]+aria-live="polite"/);
assert.doesNotMatch(code,/JSON\.stringify\(session\?\.messages\|\|\[\]\)/);

const helpers=code.slice(code.indexOf("let renderedConversation="),code.indexOf("function renderSession("));
assert.ok(helpers.startsWith("let renderedConversation="));
const elements=new Map();
function element(name){
  if(!elements.has(name))elements.set(name,{textContent:"",hidden:false,replaceChildrenCalls:0,children:[],
    replaceChildren(){this.replaceChildrenCalls++;this.children=[];},
    append(...items){this.children.push(...items);},
    prepend(...items){this.children.unshift(...items);}});
  return elements.get(name);
}
const changed=new Function("id","friendly",
  'let projectId="project-A",lastMessageKey="",currentRun=null;\n'+helpers+
  '\nreturn {check:conversationNeedsRender,status:taskSnapshotText,render:renderTaskSnapshot,'+
  'setRun:run=>currentRun=run,setProject:project=>projectId=project,reset:()=>lastMessageKey=""};')(
    element,status=>status);

const longText="Start a project\n"+"Requirements keep exact text.\n".repeat(1900);
const session={id:"session-A",messages:[
  {role:"user",content:longText},{role:"assistant",content:"First tested result"}]};
assert.equal(changed.check(session,null),true);
assert.equal(changed.check({id:"session-A",messages:session.messages.map(m=>({...m}))},null),false,
  "polling equivalent JSON must not trigger a rebuild");
assert.equal(changed.check(session,null),false);
assert.equal(changed.check({id:"session-A",messages:[
  {role:"user",content:longText+" additional requirement"},
  {role:"assistant",content:"First tested result"}]},null),true,
  "an edit to an earlier message must invalidate the UI");
assert.equal(changed.check(session,{index:0}),true,"edit mode requires message DOM change");
assert.equal(changed.check(session,{index:0}),false,"unmodified edit mode must be stable");
assert.equal(changed.check(session,null),true,"closing edit mode must restore normal message");
changed.setProject("project-B");
assert.equal(changed.check(session,null),true,"project change cannot reuse previous conversation DOM");
changed.reset();
assert.equal(changed.check(session,null),true,"explicit refresh must rebuild once");
assert.equal(changed.check(null,null),true);
assert.equal(changed.check(null,null),false);

const state={id:"runA",status:"checked",
  plan:[{step:"Inspect",status:"completed"},{step:"Edit",status:"in_progress"},
    {step:"Verify",status:"planned"}],
  changed_files:["src/app.py","tests/test_app.py"],
  proof:{total:3,passed:2},
  interruption_review:{actions:1,possible_side_effects:1,uncertain_file_edits:1}};
const summary=changed.status(state,null);
assert.match(summary,/1 of 3 plan steps complete/);
assert.match(summary,/2 changed files recorded/);
assert.match(summary,/2 of 3 current checks passed/);
assert.match(summary,/2 interrupted actions to inspect; not replayed/);
assert.doesNotMatch(summary,/100%|fully verified|everything passed/);
changed.setRun({status:"queued"});
assert.match(changed.status(null,{status:"queued"}),/^Queued$/);
changed.render(state);
assert.equal(element("taskSnapshot").textContent,changed.status(state,{status:"queued"}));
assert.equal(element("taskSnapshot").hidden,false);
changed.setRun(null);changed.render(null);
assert.equal(element("taskSnapshot").hidden,true);

const activity=code.slice(code.indexOf("function renderActivity()"),code.indexOf("function renderRecovery("));
const panel=element("activityList");
const mockNode=(tag,css="",txt="")=>({
  tag,css,txt,children:[],innerHTML:"",
  append(...children){this.children.push(...children);},
  prepend(...children){this.children.unshift(...children);}
});
const ui=new Function("id","node","icon",
  'let currentSession={id:"task-A",actions:[{tool:"write_file",path:"app.js",ok:true}]};'+
  'let currentRun={id:"run-A",status:"running",current_action:"Editing app.js"};'+
  'let runEvents=[{sequence:1,kind:"tool_start",text:"Editing file"}],lastPollError="";'+
  'function busy(){return currentRun.status==="running";}'+
  'function visibleActivityActions(actions){return actions;}'+
  'function emptyPanel(){return node("div");}'+
  'function eventDescription(event){return event.text||event.kind;}'+activity+
  '\nreturn {render:renderActivity,setStatus:value=>currentRun.current_action=value,'+
  'setEvents:values=>runEvents=values,setAction:value=>currentSession.actions=value};')(
    element,mockNode,()=>"<svg/>");
ui.render();
const first=panel.replaceChildrenCalls;
assert.ok(first>0);
ui.render();
assert.equal(panel.replaceChildrenCalls,first,"poll with same visible activity must not rebuild DOM");
ui.setStatus("Running tests");ui.render();
assert.equal(panel.replaceChildrenCalls,first+1,"new live action must invalidate");
ui.setEvents([{sequence:2,kind:"tool_end",text:"Check finished",ok:true}]);ui.render();
assert.equal(panel.replaceChildrenCalls,first+2,"new run event must invalidate");
ui.setAction([{tool:"write_file",path:"new.js",ok:true}]);ui.render();
assert.equal(panel.replaceChildrenCalls,first+3,"new file action must invalidate");
// Opening check details must survive an identical API refresh.
const checksBlock=code.slice(code.indexOf("function checkCard("),code.indexOf("function renderRepairHistory("));
assert.ok(checksBlock.includes("function checksNeedRender("));
const checkPanel=element("checksList");
const checkUI=new Function("id","node",
  'let currentSession={id:"checked-run",checks:[{id:"one",active:true,ok:false,'+
  'required:false,source:"agent",label:"Integration test",command:"npm test",output:"AssertionError"}]};'+
  checksBlock+
  '\nreturn {render:renderChecks,setChecks:items=>currentSession.checks=items};')(
    element,mockNode);
checkUI.render();
const checksFirst=checkPanel.replaceChildrenCalls;
assert.ok(checksFirst>0);
const opened=checkPanel.children[0];
opened.open=true;
checkUI.render();
assert.equal(checkPanel.replaceChildrenCalls,checksFirst,"same check result must retain expanded details");
assert.equal(checkPanel.children[0],opened,"the exact opened node is retained");
checkUI.setChecks([{id:"one",active:true,ok:false,required:false,source:"agent",
  label:"Integration test",command:"npm test",output:"AssertionError"}]);
checkUI.render();
assert.equal(checkPanel.replaceChildrenCalls,checksFirst,"new equivalent API objects must not recreate check cards");
checkUI.setChecks([{id:"one",active:true,ok:true,required:false,source:"agent",
  label:"Integration test",command:"npm test",output:"All passed"}]);
checkUI.render();
assert.equal(checkPanel.replaceChildrenCalls,checksFirst+1,"new real check outcome must update displayed evidence");

console.log("Milestone 8 UI: long conversations avoid repeated JSON serialization; edits, switches, factual progress, interruption warnings and event/check repaint caching passed.");
