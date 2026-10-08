// Exercise the shipped submit controller, including an accepted request whose response is lost.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');
const controller=source.slice(source.indexOf('async function startTask('),source.indexOf('async function startDemo('));
function fixture(){
  const elements=new Map(),calls=[];
  const id=name=>{if(!elements.has(name))elements.set(name,{value:'',hidden:true,focus(){}});return elements.get(name);};
  id('goal').value='Build my project';id('taskMode').value='build';
  let send=async()=>({id:'run-1',status:'running'}),recover=null,refreshes=0;
  const api=async(p,b)=>{calls.push({p,b});return send();};
  const ui=new Function('id','api','recover','isCloud',`
    let startingRun=false,currentRun=null,currentSession=null,transferBusy=false,projectId='project-1',renderCount=0,
      waitingForCapacity=false,cancelQueuedStart=false,capacityRetryTimer=null,capacityWaitResolve=null,retryWaits=0;
      appState={account:{enabled:true,ready:true},settings:{key_configured:true},engine:{available:true}},runEvents=[],lastChangeKey='';
    function busy(){return currentRun?.status==='running'||currentRun?.status==='queued';}
    function renderControls(){id('runButton').disabled=startingRun||busy();}
    function renderSession(){renderCount++;}
    function hostedNoKey(){return false;} function openSettings(){} function toast(){} function clearDraft(){} function saveDraftNow(){}
    async function waitForCapacityRetry(){retryWaits++;}
    function changeView(){} function schedulePoll(){} async function openAccount(){}
    async function refreshState(){const value=await recover();if(value)currentRun=value;}
    function codeChangeRequested(text){return /\\b(fix|repair|patch|refactor|implement|add|remove|delete|rename|update|modify|change|edit|replace|redesign|improve|build|create|make|correct|integrate|upgrade|rework|rewrite)\\b/i.test(text);}
    ${controller}
    return {start:()=>startTask({preventDefault(){}}),resume:()=>{currentSession={id:'saved-session'};return startTask(null,true);},
      state:()=>({startingRun,currentRun,renderCount,waitingForCapacity,retryWaits}),
      cancelWait(){cancelQueuedStart=true;},offline(){appState.engine={available:false,message:'Engine offline.'};}};
  `)(id,api,async()=>{refreshes++;return recover;},true);
  return {...ui,id,calls,setSend:fn=>{send=fn;},recover:value=>{recover=value;},refreshes:()=>refreshes};
}
(async()=>{
  const f=fixture();let resolve;f.setSend(()=>new Promise(r=>resolve=r));
  const first=f.start();await f.start();assert.equal(f.calls.length,1);assert.equal(f.id('runButton').disabled,true);
  resolve({id:'run-1',status:'running'});await first;assert.equal(f.id('goal').value,'');assert.equal(f.state().startingRun,false);assert.equal(f.state().renderCount,1);
  const resumed=fixture();resumed.id('goal').value='keep this draft';await resumed.resume();
  assert.equal(resumed.calls.length,1);assert.equal(resumed.calls[0].b.goal,'');assert.equal(resumed.calls[0].b.session_id,'saved-session');
  assert.equal(resumed.id('goal').value,'keep this draft');assert.equal(resumed.state().renderCount,1);
  const failed=fixture();failed.setSend(async()=>{throw Error('Connection lost');});await failed.start();
  assert.match(failed.id('taskError').textContent,/Connection lost/);assert.equal(failed.id('goal').value,'Build my project');
  assert.equal(failed.refreshes(),1);assert.equal(failed.calls.length,1);assert.equal(failed.id('runButton').disabled,false);
  const lost=fixture();lost.setSend(async()=>{throw Error('Connection lost');});lost.recover({id:'accepted-run',status:'running'});await lost.start();
  assert.equal(lost.state().currentRun.id,'accepted-run');assert.equal(lost.calls.length,1);assert.match(lost.id('taskError').textContent,/Reconnected/);
  const capacity=fixture();let busyReplies=2;
  capacity.setSend(async()=>{
    if(busyReplies-->0)throw Error('The coding server is busy. Retry shortly; no model call was started.');
    return {id:'queued-then-started',status:'queued'};
  });
  await capacity.start();
  assert.equal(capacity.calls.length,3,'Only explicit no-run busy responses are retried');
  assert.equal(capacity.state().retryWaits,2);
  assert.equal(capacity.state().currentRun.id,'queued-then-started');
  assert.equal(capacity.id('goal').value,'');
  const busyThenConnection=fixture();let messages=0;
  busyThenConnection.setSend(async()=>{
    if(messages++===0)throw Error('The coding server is busy. Retry shortly; no model call was started.');
    throw Error('Connection lost');
  });
  await busyThenConnection.start();
  assert.equal(busyThenConnection.calls.length,2,'Ambiguous errors must not be automatically retried');
  assert.equal(busyThenConnection.id('goal').value,'Build my project');
  const offline=fixture();offline.offline();await offline.start();assert.equal(offline.calls.length,0);assert.equal(offline.id('taskError').textContent,'Engine offline.');
  const changed=fixture();changed.id('taskMode').value='ask';changed.id('goal').value='Fix the existing login page';
  await changed.start();assert.equal(changed.calls[0].b.task_mode,'build',
    'An actual code-change request after Ask mode must not remain read-only.');

  assert.match(source,/sparkleDraft:v1:/);
  assert.match(source,/Draft restored/);
  assert.match(source,/continueLastTask/);
  assert.match(source,/Improve quality/);
  assert.match(source,/Test & fix/);
  assert.match(source,/Auto expands when needed/);
  const refresh=source.slice(source.indexOf('async function refreshState('),source.indexOf('function schedulePoll('));
  const reconnect=new Function('api',`let currentRun={id:'finished-run',status:'completed'},projectId='project-1',appState;function renderProjects(){}function renderProvider(){}function renderExperience(){}function renderCloudState(){}function schedulePoll(){} ${refresh};return {refreshState,current:()=>currentRun};`)(async()=>({projects:[{id:'project-1'}],active_run:{id:'followup-run',project_id:'project-1',status:'running'}}));
  await reconnect.refreshState();assert.equal(reconnect.current().id,'followup-run','An old finished run must not hide a newly accepted follow-up');
  console.log('Prompt submit: duplicate prevention, preserved prompt, read-only reconnect and offline errors passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
