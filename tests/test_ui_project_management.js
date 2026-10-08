"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../sparkle_coder/ui/app.js"),"utf8");
const extract=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
for(const name of ['deleteProjectDialog','deleteProjectFiles','confirmProjectName','clearHistory',
                    'projectPurpose','suggestBrief','briefSuggestionStatus','skillSaveStatus']){
  assert.ok(source.includes('id="'+name+'"'),name);
}

class El {
  constructor(tag="div",classname="",text="") {
    this.tag=tag;this.className=classname;this.text=text;this.textContent=text;
    this.children=[];this.value="";this.checked=false;this.hidden=false;
    this.disabled=false;this.dataset={};this.open=false;
  }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  setAttribute(name,value){this[name]=value;}
  showModal(){this.open=true;}
  close(){this.open=false;}
  reset(){}
}
const node=(...args)=>new El(...args);
const elements=new Map();
const id=name=>{if(!elements.has(name))elements.set(name,new El());return elements.get(name);};
const descendants=target=>{
  const out=[];
  for(const item of target.children){out.push(item,...descendants(item));}
  return out;
};
const document={querySelectorAll:()=>descendants(id("skillsList")).filter(item=>item.dataset.skillId)};
const requests=[];
let savedOverrides={enabled:[],disabled:[],vision_review:false};
let failSave=false;
const catalog=[
  {id:"visual_qa",title:"Visual QA",source:"builtin"},
  {id:"visual_design",title:"Visual design",source:"builtin"}
];
const api=async(route,body)=>{
  requests.push({route,body});
  if(route==="/projects/p1/skills"){
    if(body?.action==="overrides"){
      if(failSave)throw Error("Service temporarily unavailable");
      savedOverrides={enabled:body.enabled,disabled:body.disabled,vision_review:body.vision_review};
    }
    if(body?.action==="save_custom")catalog.push({id:body.id,title:body.title,source:"custom"});
    return {skills:catalog.slice(),overrides:{...savedOverrides},vision:{available:false,reason:"Unavailable"}};
  }
  if(route==="/projects/p1/brief-suggestion"){
    return {revision:null,brief:{purpose:"Build a contact form",
      requirements:["Build a contact form","Make it keyboard accessible"],constraints:""},
      sources:2,note:"Based on saved user requests only."};
  }
  if(route==="/projects/p1/delete"){
    if(body.name!=="My project")throw Error("Wrong project name");
    return {removed:true,files_deleted:body.delete_files,message:"Project removed."};
  }
  if(route==="/projects/p1/sessions/clear")return {deleted:2};
  if(route==="/projects/p1/sessions/abc123def456/delete")return {deleted:"abc123def456"};
  throw Error("Unexpected API "+route);
};
const handlers=[
 'let projectId="p1",briefProjectId="p1",briefRevision=null;',
 'let appState={projects:[{id:"p1",name:"My project",managed:true}],selected_project:"p1",active_run:null};',
 'let startingRun=false,currentRun=null,currentSession=null,runEvents=[],lastMessageKey="";',
 'let historyItems=[{id:"abc123def456"},{id:"other"}];',
 'function busy(){return false;}function toast(message){messages.push(message);}',
 'function clearDraft(p){messages.push("draft cleared: "+p);}',
 'function changeView(){}function schedulePoll(){}',
 'async function refreshState(){projectId=null;}async function newTask(){}',
 'async function loadFiles(){}async function loadHistory(){}',
 'function renderSession(){}',
 'function action(fn){return fn();}',
 extract("async function deleteSavedTask(", "async function loadSession("),
 extract("async function suggestProjectBrief(", "async function saveProjectBrief("),
 extract("let projectSkillState=", "function renderSetupReport(report)"),
 'return {deleteSavedTask,clearSavedHistory,openDeleteProject,confirmDeleteProject,suggestProjectBrief,',
 ' openProjectSkills,saveProjectSkillOverrides,saveCustomProjectSkill,renderProjectSkills,',
 ' projectId:()=>projectId,restoreProject:()=>{projectId="p1";},skillProjectId:()=>skillProjectId};'
].join("\n");
const messages=[];
let accept=true;
const window={confirm:()=>accept};
const ui=new Function("id","node","api","document","window","messages",handlers)(
  id,node,api,document,window,messages);

(async()=>{
  id("briefPurpose").value="My existing user-authored purpose";
  id("briefRequirements").value="Preserve my existing files";
  id("briefConstraints").value="No fake testimonials";
  await ui.suggestProjectBrief();
  assert.equal(id("briefPurpose").value,"My existing user-authored purpose");
  assert.equal(id("briefConstraints").value,"No fake testimonials");
  assert.equal(id("briefRequirements").value.split("\n").length,3);
  assert.match(id("briefSuggestionStatus").textContent,/Nothing was saved yet/);

  await ui.openProjectSkills();
  const selectors=()=>document.querySelectorAll("#skillsList [data-skill-id]");
  selectors()[0].value="on";
  selectors()[1].value="off";
  id("visionReview").checked=true;
  await ui.saveProjectSkillOverrides();
  assert.deepEqual(savedOverrides,{enabled:["visual_qa"],disabled:["visual_design"],vision_review:true});
  assert.match(id("skillSaveStatus").textContent,/Saved for this project/);
  await ui.openProjectSkills();
  assert.equal(selectors()[0].value,"on");
  assert.equal(selectors()[1].value,"off");

  selectors()[1].value="on";
  id("customSkillId").value="brand_voice";
  id("customSkillTitle").value="Brand voice";
  id("customSkillTriggers").value="brand voice";
  id("customSkillBody").value="Retain human-friendly content.";
  await ui.saveCustomProjectSkill({preventDefault(){}});
  assert.equal(selectors()[1].value,"on","unsaved selections survive custom skill save");
  assert.equal(selectors().length,3);
  failSave=true;
  await ui.saveProjectSkillOverrides();
  assert.match(id("skillSaveStatus").textContent,/Could not save/);
  assert.equal(selectors()[1].value,"on","failed save keeps edits");
  failSave=false;

  ui.openDeleteProject();
  assert.equal(id("deleteProjectDialog").open,true);
  assert.equal(id("deleteProjectFilesLabel").hidden,false);
  id("confirmProjectName").value="Wrong";
  await ui.confirmDeleteProject();
  assert.match(id("deleteProjectError").textContent,/Wrong project name/);
  assert.equal(id("deleteProjectDialog").open,true);
  id("confirmProjectName").value="My project";
  id("deleteProjectFiles").checked=true;
  await ui.confirmDeleteProject();
  assert.equal(requests.filter(x=>x.route==="/projects/p1/delete").at(-1).body.delete_files,true);
  assert.equal(id("deleteProjectDialog").open,false);
  assert.equal(ui.projectId(),null);
  ui.restoreProject();

  const clearRequest=requests.length;
  accept=false;
  await ui.deleteSavedTask("abc123def456");
  assert.equal(requests.length,clearRequest,"cancelled deletion must make no request");
  accept=true;
  await ui.deleteSavedTask("abc123def456");
  assert.ok(requests.some(x=>x.route.endsWith("/abc123def456/delete")&&x.body.confirm===true));
  await ui.clearSavedHistory();
  assert.ok(requests.some(x=>x.route.endsWith("/sessions/clear")&&x.body.confirm===true));
  console.log("Project/workspace UI: grounded brief merge, skill saving and unsaved custom-skill edits, explicit deletion confirmation and preserving project files.");
})().catch(error=>{console.error(error);process.exitCode=1;});
