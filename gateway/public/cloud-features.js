"use strict";
(()=>{
if(document.documentElement.dataset.runtime!=="cloud")return;
const q=s=>document.querySelector(s);
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
const storeKey=name=>"sparkle_cloud_studio_"+(projectId||"global")+"_"+name;
const get=(name,fallback)=>{try{return JSON.parse(localStorage.getItem(storeKey(name)))??fallback}catch{return fallback}};
const set=(name,value)=>localStorage.setItem(storeKey(name),JSON.stringify(value));
const FEATURE_NAMES=["Plan → Build","Token/Credit Budget","Smart Context","Checkpoints + Rollback","Diff Review","Test → Fix Loop","Live Preview","Project Health","Model Router","Task Queue","Reusable Skills","Admin Control Center","Workspace Search","Project Memory","Rules File","AI File Permissions","Secrets Manager","One-click Deployment","Deployment History","Shareable Preview","Project Templates","Screenshot → Website","Visual Editing","Error Screenshot Debugging","Database Assistant","API Tester","Architecture Map","Explain Code","Background Agent Tasks","SPARKLE Intelligence Panel"];
let dialog,body,selectedPreview="";
function section(title,...children){const s=el("section","cloud-studio-section");s.append(el("h3","",title),...children);return s}
function btn(label,fn,kind="secondary"){const b=el("button","button "+kind,label);b.type="button";b.onclick=()=>action(fn);return b}
function metric(label,value){const d=el("div","cloud-studio-metric");d.append(el("span","",label),el("strong","",String(value)));return d}
function activeProject(){return appState?.projects?.find(p=>p.id===projectId)}
function ensureProject(){if(!projectId)throw new Error("Create or select a cloud project first.")}
function fillGoal(text,mode="build"){changeView("build");id("taskMode").value=mode;id("goal").value=text;id("goal").focus();dialog.close();toast("Task prepared. Review it, then run SPARKLE.")}
function inject(){
 const host=q(".topbar-actions");if(!host||id("cloudStudioButton"))return;
 const open=btn("Studio",()=>{render("overview");dialog.showModal()});open.id="cloudStudioButton";open.className="text-button cloud-studio-open";host.prepend(open);
 dialog=el("dialog","cloud-studio");dialog.id="cloudStudio";
 const head=el("div","cloud-studio-head");const title=el("div");title.append(el("span","eyebrow","SPARKLE INTELLIGENCE"),el("h2","","Cloud Workspace Studio"));const close=el("button","icon-button","×");close.type="button";close.onclick=()=>dialog.close();head.append(title,close);
 const tabs=el("div","cloud-studio-tabs");for(const [key,label] of [["overview","Overview"],["plan","Plan"],["context","Context"],["preview","Preview"],["queue","Queue"],["tools","Tools"],["memory","Memory"],["features","30 Features"]])tabs.append(btn(label,()=>render(key),"secondary"));
 body=el("div","cloud-studio-body");dialog.append(head,tabs,body);document.body.append(dialog);
}
async function render(tab){body.replaceChildren();try{if(tab==="overview")await overview();else if(tab==="plan")await plan();else if(tab==="context")await context();else if(tab==="preview")await preview();else if(tab==="queue")await queue();else if(tab==="tools")await tools();else if(tab==="memory")await memory();else features();}catch(error){body.append(section("Studio error",el("p","inline-result",error.message)))}}
async function overview(){
 const project=activeProject(),settings=appState?.settings||{},account=appState?.account||{},grid=el("div","cloud-studio-metrics");
 grid.append(metric("Engine",appState?.engine?.available?"Online":"Offline"),metric("Project",project?.name||"None"),metric("Files",files?.length||0),metric("Saved tasks",historyItems?.length||0),metric("Credits",Number(account.available_tokens||0).toLocaleString()),metric("Current run",currentRun?.status||"Ready"));
 body.append(grid);
 const max=el("input");max.type="number";max.min="256";max.max="8192";max.value=settings.max_tokens||4096;
 const total=el("input");total.type="number";total.min="1000";total.max="200000";total.value=settings.max_total_tokens||50000;
 const effort=el("select");effort.innerHTML='<option value="efficient">Fast</option><option value="thorough">Thorough</option>';effort.value=settings.efficiency||"efficient";
 const save=btn("Save run budget",async()=>{ensureProject();await api("/settings",{efficiency:effort.value,max_tokens:Math.max(256,Math.min(8192,Number(max.value)||4096)),max_total_tokens:Math.max(1000,Math.min(200000,Number(total.value)||50000))});await refreshState();toast("Run budget and routing policy saved.");render("overview")},"primary");
 body.append(section("Budget + Model Router",label("Effort",effort),label("Max output tokens per model call",max),label("Max total tokens per run",total),save));
 body.append(section("Checkpoints + Review",el("p","settings-note","SPARKLE records file changes and saved tasks so you can inspect changes and undo from History."),btn("Open run history",()=>{dialog.close();changeView("history")}),btn("Review latest changes",async()=>{dialog.close();changeView("build");setTab("changes");if(currentSession)await loadChanges()}),btn("Run project health scan",()=>{dialog.close();openSetup()})));
}
function label(text,input){const l=el("label");l.append(document.createTextNode(text),input);return l}
async function plan(){
 ensureProject();if(!files?.length)await loadFiles();
 const goal=el("textarea");goal.rows=5;goal.placeholder="Describe what you want to change…";const out=el("pre","cloud-studio-output","No plan yet.");
 body.append(section("Plan → Build",goal,btn("Make local plan",()=>{const terms=goal.value.toLowerCase().split(/\W+/).filter(x=>x.length>2),rank=(files||[]).map(f=>({path:f.path,score:terms.reduce((n,t)=>n+(f.path.toLowerCase().includes(t)?3:0),0)})).sort((a,b)=>b.score-a.score).slice(0,8);out.textContent=["Goal: "+goal.value.trim(),"Likely files:",...rank.map(x=>"• "+x.path),"Flow: inspect → checkpoint/history → minimal edit → run checks → review diff"].join("\n")}),btn("Ask SPARKLE to plan",()=>fillGoal("Plan this change without editing files yet. Identify relevant files, risks, tests, and a minimal implementation sequence. Goal: "+goal.value.trim(),"ask")),btn("Build with review",()=>{id("reviewEdits").checked=true;fillGoal("Implement this with minimal changes. Preserve existing behavior, run appropriate checks, and summarize the diff. Goal: "+goal.value.trim(),"build")},"primary"),out));
}
async function context(){
 ensureProject();if(!files?.length)await loadFiles();const search=el("input");search.placeholder="Search file paths…";const results=el("div","cloud-studio-results");
 const run=()=>{results.replaceChildren();const term=search.value.trim().toLowerCase();for(const f of (files||[]).filter(x=>!term||x.path.toLowerCase().includes(term)).slice(0,80)){const b=btn(f.path,async()=>{dialog.close();changeView("files");await openFile(f.path)});b.className="cloud-studio-hit";results.append(b)}};search.oninput=run;run();
 body.append(section("Workspace Search + Smart Context",search,results),section("Project Intelligence",btn("Open Project Brief",()=>{dialog.close();openProjectBrief()}),btn("Open architecture/setup map",()=>{dialog.close();openSetup()}),el("p","settings-note","SPARKLE sends project context through the coding engine with bounded context limits; sensitive files remain excluded by engine policy.")));
}
async function preview(){
 ensureProject();if(!files?.length)await loadFiles();const map=new Map((files||[]).map(f=>[f.path,f]));const find=(names,suffix)=>names.find(n=>map.has(n))||[...map.keys()].find(p=>p.endsWith(suffix));
 const htmlPath=find(["index.html","public/index.html"],"/index.html"),cssPath=find(["styles.css","style.css"],".css"),jsPath=find(["script.js","app.js"],".js");
 const read=async path=>path?(await api("/projects/"+projectId+"/file?path="+encodeURIComponent(path))).content||"":"";
 const html=await read(htmlPath),css=await read(cssPath),js=await read(jsPath),frame=el("iframe","cloud-studio-preview");frame.setAttribute("sandbox","allow-scripts");
 const src=(html||"<main><h1>No index.html found</h1></main>").replace("</head>","<style>"+css+"</style></head>").replace("</body>","<script>"+js.replaceAll("</script>","<\\/script>")+"</script></body>");frame.srcdoc=src;
 frame.onload=()=>{try{frame.contentDocument.addEventListener("click",e=>{e.preventDefault();const t=e.target;selectedPreview=t.tagName.toLowerCase()+(t.id?"#"+t.id:"")+(t.className?"."+String(t.className).trim().replace(/\s+/g,"."):"");toast("Selected "+selectedPreview)})}catch{}};
 body.append(section("Live Preview + Visual Editing",el("p","settings-note",htmlPath?"Previewing "+htmlPath:"Create index.html to enable preview."),frame,btn("Edit selected element",()=>fillGoal("Modify the UI element "+(selectedPreview||"I select in preview")+" with minimal changes. Preserve surrounding layout and run relevant checks.")),btn("Open shareable preview tab",()=>{const w=open();if(w){w.document.write(src);w.document.close()}})));
}
async function queue(){
 ensureProject();const tasks=get("queue",[]),input=el("input");input.placeholder="Add a task…";const list=el("div","cloud-studio-results");
 const draw=()=>{list.replaceChildren();tasks.forEach((t,i)=>{const row=el("div","cloud-studio-task");row.append(el("span","",(i+1)+". "+t.text),el("small","",t.status||"queued"),btn("Prepare",()=>fillGoal(t.text)),btn("Run next",async()=>{if(busy())throw new Error("A task is already running. SPARKLE keeps it running while you navigate.");id("goal").value=t.text;id("taskMode").value="build";dialog.close();await startTask({preventDefault(){}});t.status="running";set("queue",tasks)}));list.append(row)})};draw();
 body.append(section("Task Queue + Background Agent Tasks",el("p","settings-note","Active cloud runs continue on the coding engine while you move around the app. Queue entries are prepared explicitly so tasks never start without your action."),input,btn("Add task",()=>{if(input.value.trim()){tasks.push({text:input.value.trim(),status:"queued",created:Date.now()});set("queue",tasks);input.value="";draw()}},"primary"),list));
}
async function tools(){
 ensureProject();const commands=[["/fix","Find and fix the concrete bug with a regression check."],["/test","Run the most relevant tests and fix only failures caused by this project."],["/review","Review the current project for correctness, security, maintainability and unnecessary complexity."],["/explain","Explain the selected/current code and architecture without editing."],["/refactor","Refactor minimally without changing behavior; run tests."],["/security-check","Check secrets, auth boundaries, input validation and unsafe execution."],["/optimize","Reduce unnecessary code, model/context use and runtime overhead."],["/deploy","Inspect deployment config, deploy safely, verify health, and report rollback details."]];
 const chips=el("div","cloud-studio-chips");for(const [name,prompt] of commands)chips.append(btn(name,()=>fillGoal(prompt,name==="/explain"?"ask":"build")));
 const apiPath=el("input");apiPath.value="/healthz";const apiOut=el("pre","cloud-studio-output");const apiTest=btn("GET",async()=>{if(!apiPath.value.startsWith("/")||apiPath.value.startsWith("//"))throw new Error("Use a same-origin path.");const r=await fetch(apiPath.value,{cache:"no-store",redirect:"error"});apiOut.textContent=r.status+" "+r.statusText+"\n"+await r.text()},"primary");
 const template=btn("Landing page template",async()=>{if((files||[]).some(f=>["index.html","styles.css","script.js"].includes(f.path))&&!confirm("Template files already exist. Replace them with starter files?"))return;for(const [path,content] of [["index.html",'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="styles.css"></head><body><main><h1>New project</h1><p>Built with SPARKLE CODER.</p></main><script src="script.js"></script></body></html>'],["styles.css","body{font-family:system-ui;margin:0;padding:2rem}"],["script.js",""]]){let existing=null;try{existing=await api("/projects/"+projectId+"/file?path="+encodeURIComponent(path))}catch{}await api("/projects/"+projectId+"/save-file",{path,content,expected_sha256:existing?.sha256||null})}await loadFiles();toast("Starter template created. History keeps undo information.")});
 const shot=el("input");shot.type="file";shot.accept="image/*";const shotText=el("small","","No screenshot selected.");shot.onchange=()=>{const f=shot.files?.[0];if(f){set("screenshot",{name:f.name,size:f.size,type:f.type});shotText.textContent=f.name+" selected locally. Describe visible details when you send the task; image bytes are not uploaded by this workflow."}};
 body.append(section("Reusable Skills",chips),section("Project Templates",template),section("Screenshot / Error Screenshot Workflow",shot,shotText,btn("Prepare reconstruction task",()=>fillGoal("Rebuild the UI shown in my screenshot description as responsive code. Start by asking for any visual detail you cannot infer; do not invent hidden behavior.","ask"))),section("API Tester",apiPath,apiTest,apiOut),section("Database + Architecture + Deploy",btn("Database assistant",()=>fillGoal("Inspect schema and migration files. Explain the current data model, then propose only safe reversible changes. Warn before destructive operations.","ask")),btn("Architecture map",()=>{dialog.close();openSetup()}),btn("One-click deployment workflow",()=>fillGoal("Inspect this project's deployment files, deploy using the configured provider, verify the live health and critical routes, and report rollback details. Ask before any protected deployment action.","build"),"primary"),btn("Deployment history",()=>{dialog.close();changeView("history")})));
}
async function memory(){
 ensureProject();const rules=el("textarea");rules.rows=5;rules.value=get("rules","");const perms=el("textarea");perms.rows=4;perms.value=get("permissions","*.env\n*.key\n*.pem\ncredentials*");const secrets=el("input");secrets.value=get("secretNames",[]).join(", ");
 body.append(section("Project Memory",el("p","settings-note","Use Project Brief for goals, requirements and decisions that should be supplied to future tasks."),btn("Open Project Brief",()=>{dialog.close();openProjectBrief()})),section("Rules",rules),section("AI File Permissions",perms),section("Secrets Manager — names only, never values",secrets),btn("Save local Studio intelligence",()=>{set("rules",rules.value);set("permissions",perms.value);set("secretNames",secrets.value.split(",").map(x=>x.trim()).filter(Boolean));toast("Studio intelligence saved for this project/browser.")},"primary"));
}
function features(){const grid=el("div","cloud-studio-feature-grid");FEATURE_NAMES.forEach((name,i)=>{const c=el("article","cloud-studio-feature");c.append(el("strong","",(i+1)+". "+name),el("span","cloud-studio-enabled","Enabled"));grid.append(c)});body.append(grid)}
window.addEventListener("DOMContentLoaded",inject);
if(document.readyState!=="loading")inject();
})();