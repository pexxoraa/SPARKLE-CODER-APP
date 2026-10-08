"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../sparkle_coder/ui/app.js"),"utf8");
const poll=source.slice(source.indexOf("async function pollRun()"),source.indexOf("async function startTask("));
assert.ok(poll.startsWith("async function pollRun()"));

function fixture(){
  let calls=0,notices=0,scheduled=0;
  const id=name=>({hidden:false,textContent:"",value:"",disabled:false});
  let handler=()=>({id:"one",status:"running",events:[]});
  const api=async(...args)=>{calls++;return handler(...args);};
  const harness=[
    'let currentRun={id:"one",status:"running"},runEvents=[],pollInFlight=false,lastPollError="",monitorEventsTruncated=false;',
    'let appState={account:{enabled:false}},tab="activity",lastChangeKey="",lastConsoleKey="";',
    'function busy(){return ["queued","running","approval","pausing","paused_by_user","stopping"].includes(currentRun?.status);}',
    'function toast(v){handlers.toast(v);}',
    'function renderSession(){} function renderControls(){} function renderMonitor(){} function renderActivity(){}',
    'function schedulePoll(){handlers.scheduled();}',
    'async function loadChanges(){} async function loadFiles(){} async function loadHistory(){} async function refreshAccount(){}',
    poll,
    'return {poll:pollRun,events:()=>runEvents,reset:key=>{currentRun={id:key,status:"running"};},status:()=>currentRun?.status, truncated:()=>monitorEventsTruncated};'
  ].join("\n");
  const f=new Function("api","id","handlers",harness)(api,id,{toast:()=>{notices++;},scheduled:()=>{scheduled++;}});
  return {...f,calls:()=>calls,notices:()=>notices,scheduled:()=>scheduled,respond:fn=>{handler=fn;}};
}

(async()=>{
  const f=fixture();
  let resolve;f.respond(()=>new Promise(r=>{resolve=r;}));
  const first=f.poll();await f.poll();assert.equal(f.calls(),1,"one run must not have two overlapping polls");
  resolve({id:"one",status:"running",events:[{sequence:1,at:"2026-10-08T00:00:00Z",kind:"tool_start"}]});
  await first;assert.equal(f.events().length,1);assert.ok(f.scheduled()>0,'slow polling must arrange another refresh');
  f.respond(()=>({id:"one",status:"running",events:[{sequence:1,kind:"tool_start"},{sequence:2,kind:"tool_end"}]}));
  await f.poll();assert.deepEqual(f.events().map(x=>x.sequence),[1,2],"resends should not duplicate events");
  f.respond(()=>({id:"one",status:"running",events:[{sequence:600,kind:"finished"}],events_truncated:true}));
  await f.poll();assert.deepEqual(f.events().map(x=>x.sequence),[600]);
  assert.equal(f.truncated(),true,"show that earlier events were truncated");

  let bad=true;f.respond(async()=>{if(bad)throw Error("Connection lost");return {id:"one",status:"running",events:[]};});
  await f.poll();await f.poll();assert.equal(f.notices(),1,"repeat network errors must not spam notices");
  bad=false;await f.poll();bad=true;await f.poll();assert.equal(f.notices(),2,"restored network resets warning dedup");

  const pending=fixture();let release;
  pending.respond(()=>new Promise(r=>release=r));
  const read=pending.poll();pending.reset("two");
  release({id:"one",status:"running",events:[{sequence:42}]});await read;
  assert.equal(pending.status(),"running");
  assert.equal(pending.events().length,0,"old run response must not overwrite a newly selected run");

  const refresh=source.slice(source.indexOf('async function refreshState()'),source.indexOf('function schedulePoll('));
  const stateMonitor=new Function('api',`
    let currentRun={id:'still-running',project_id:'project-1',status:'running'},projectId='project-1',appState,scheduled=0;
    function renderProjects(){}function renderProvider(){}function renderExperience(){}function renderCloudState(){}function renderControls(){}
    function schedulePoll(){scheduled++;}function busy(){return currentRun?.status==='running';}
    ${refresh}
    return {refresh:refreshState,current:()=>currentRun,scheduled:()=>scheduled};
  `)(async()=>({projects:[{id:'project-1'}],active_run:null}));
  await stateMonitor.refresh();assert.equal(stateMonitor.current().id,'still-running',
    'transient /state responses cannot discard the live run');
  assert.ok(stateMonitor.scheduled()>0,'state refresh must keep polling until terminal confirmation');

  assert.match(source,/id="allowRepeatCommand"/);
  assert.match(source,/answerApproval\(true,true\)/);
  assert.match(source,/Cloud offline/);
  assert.match(source,/workspaceModeSwitch"\)\.onclick/);
  console.log("Run Monitor: serial polling, no duplicate events, no stale run overwrite, bounded retry notices, Cloud reconnect and approval reuse.");
})().catch(error=>{console.error(error);process.exitCode=1;});
