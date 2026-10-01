"use strict";
(()=>{
const core=()=>window.SparkleCore;
const q=s=>document.querySelector(s);
const h=(tag,props={},...kids)=>{const e=document.createElement(tag);for(const[k,v]of Object.entries(props)){if(k==="class")e.className=v;else if(k==="text")e.textContent=v;else if(k.startsWith("on"))e.addEventListener(k.slice(2),v);else e.setAttribute(k,v);}for(const k of kids.flat())if(k!=null)e.append(k.nodeType?k:document.createTextNode(k));return e;};
const store={get(k,d){try{return JSON.parse(localStorage.getItem("sparkle_"+k))??d}catch{return d}},set(k,v){localStorage.setItem("sparkle_"+k,JSON.stringify(v));}};
const features=[
["Plan → Build","Generate a file/change plan before editing."],["Task Budget","Cap output tokens per request."],["Smart Context","Rank relevant project files for prompts."],["Checkpoints","Snapshot project state before risky edits."],["Diff Review","Review active-file changes before save."],["Test/Fix Loop","Create bounded diagnose→fix→verify tasks."],["Live Preview","Render HTML/CSS/JS in a sandboxed preview."],["Project Health","Scan files for common project risks."],["Model Router","Route simple vs complex tasks by policy."],["Task Queue","Run work as explicit ordered tasks."],["Skills / Commands","Reusable /fix, /test, /review and more."],["Admin Control","Usage, accounts and credits remain in admin."],["Workspace Search","Search filenames and file contents."],["Project Memory","Persist architecture and decisions per browser."],["Rules File","Maintain project instructions in .sparkle/rules.md."],["AI File Permissions","Exclude sensitive/read-only paths from context."],["Secrets Manager","Keep secret names locally without exposing values."],["One-click Deploy","Generate deployment plans for supported targets."],["Deployment History","Track deployment checkpoints and status locally."],["Share Preview","Open a clean preview in a new tab."],["Project Templates","Bootstrap common project structures."],["Screenshot → Website","Attach a screenshot workflow brief for reconstruction."],["Visual Editing","Select preview elements and turn them into edit prompts."],["Error Screenshot Debug","Create structured debugging tasks from screenshot notes."],["Database Assistant","Inspect schema files and generate safe DB prompts."],["API Tester","Test same-origin JSON endpoints."],["Architecture Map","Derive a project dependency/file map."],["Explain Code","Explain/review/refactor the active selection or file."],["Background Tasks","Queue independent non-blocking workspace tasks."],["Intelligence Panel","Show usage, files, checkpoints and task metrics."]
];
let lastCheckpoint=null,lastSelectedPreview="";
function inject(){
 const btn=h("button",{id:"sparkleStudioButton",class:"button secondary",text:"Studio"});
 const top=q(".top-actions"); if(top)top.prepend(btn);
 const dlg=h("dialog",{id:"sparkleStudio",class:"studio-dialog"});
 dlg.innerHTML='<div class="dialog-head"><div><span class="eyebrow">SPARKLE INTELLIGENCE</span><h2>Workspace Studio</h2></div><button class="icon-button" id="studioClose">×</button></div><div class="studio-tabs" id="studioTabs"></div><div class="studio-body" id="studioBody"></div>';
 document.body.append(dlg);
 btn.onclick=()=>{render("overview");dlg.showModal();};q("#studioClose").onclick=()=>dlg.close();
 const tabs=[["overview","Overview"],["plan","Plan"],["search","Search"],["preview","Preview"],["tasks","Tasks"],["tools","Tools"],["memory","Memory"],["features","30 Features"]];
 for(const[t,l]of tabs)q("#studioTabs").append(h("button",{class:"text-button",text:l,onclick:()=>render(t)}));
}
async function files(){return await core().getFiles();}
function section(title,...kids){return h("section",{class:"studio-section"},h("h3",{text:title}),...kids);}
function metric(label,value){return h("div",{class:"metric"},h("span",{text:label}),h("strong",{text:String(value)}));}
async function render(tab){
 const body=q("#studioBody");body.replaceChildren();
 if(tab==="overview")return overview(body);
 if(tab==="plan")return plan(body);
 if(tab==="search")return search(body);
 if(tab==="preview")return preview(body);
 if(tab==="tasks")return tasks(body);
 if(tab==="tools")return tools(body);
 if(tab==="memory")return memory(body);
 if(tab==="features")return featureGrid(body);
}
async function overview(body){
 const f=await files(),cps=store.get("checkpoints",[]),tasks=store.get("tasks",[]),usage=store.get("usage",{in:0,out:0,calls:0});
 const budget=Number(localStorage.getItem("sparkle_task_budget")||4096);
 const grid=h("div",{class:"metric-grid"},metric("Files",Object.keys(f).length),metric("Budget",budget+" tokens"),metric("Checkpoints",cps.length),metric("Queued tasks",tasks.filter(x=>x.status!=="done").length),metric("Model calls",usage.calls),metric("Tokens",usage.in+usage.out));
 body.append(grid);
 const controls=section("Execution controls");
 const input=h("input",{type:"number",min:"256",max:"8192",value:String(budget)});
 const save=h("button",{class:"button primary",text:"Save budget",onclick:()=>{localStorage.setItem("sparkle_task_budget",String(Math.max(256,Math.min(8192,Number(input.value)||4096))));core().toast("Task budget saved.");render("overview");}});
 controls.append(h("label",{},"Max output tokens per task",input),save);
 const cp=h("button",{class:"button secondary",text:"Create checkpoint",onclick:createCheckpoint});
 const health=h("button",{class:"button secondary",text:"Run project health scan",onclick:()=>healthScan(body)});
 const router=h("select");router.innerHTML="<option value=\"deep\">Deep reasoning</option><option value=\"fast\">Fast/simple tasks</option>";router.value=localStorage.getItem("sparkle_router_mode")||"deep";router.onchange=()=>localStorage.setItem("sparkle_router_mode",router.value);
 controls.append(h("label",{},"Model routing policy",router),h("div",{class:"studio-actions"},cp,health));body.append(controls);
 if(cps.length){const active=core().getActive();const history=section("Checkpoint / Diff Review");cps.slice(0,5).forEach((x,i)=>{const changed=x.files?.[active.path]!==active.content;history.append(h("div",{class:"task-row"},h("span",{text:new Date(x.created).toLocaleString()+" · "+(changed?"active file changed":"no active-file change")}),h("button",{class:"text-button",text:"Restore active",onclick:()=>{if(x.files?.[active.path]!=null)core().setActive(active.path,x.files[active.path]);}})));});body.append(history);}
}
async function createCheckpoint(){
 const cp=await core().createCheckpoint();const list=store.get("checkpoints",[]);list.unshift(cp);store.set("checkpoints",list.slice(0,20));lastCheckpoint=cp;core().toast("Checkpoint created.");
}
async function healthScan(body){
 const f=await files(),issues=[];for(const[p,c]of Object.entries(f)){if(c.length>120000)issues.push(p+" is very large.");if(/TODO|FIXME/.test(c))issues.push(p+" contains TODO/FIXME.");if(/eval\s*\(/.test(c))issues.push(p+" uses eval().");if(/console\.log/.test(c)&&/src\//.test(p))issues.push(p+" contains console.log.");}
 body.append(section("Health results",h("pre",{class:"studio-output",text:issues.length?issues.join("\n"):"No basic health warnings found."})));
}
async function plan(body){
 const ta=h("textarea",{rows:"6",placeholder:"Describe the change you want…"}),out=h("pre",{class:"studio-output",text:"No plan yet."});
 const make=h("button",{class:"button primary",text:"Generate plan",onclick:async()=>{const f=await files(),rank=rankFiles(f,ta.value).slice(0,8);out.textContent=["Goal: "+ta.value.trim(),"Relevant files:",...rank.map(x=>"• "+x.path),"Execution: checkpoint → edit → diff → test → preview"].join("\n");}});
 const build=h("button",{class:"button secondary",text:"Send plan to AI",onclick:()=>core().sendPromptText("Plan first, then implement with minimal changes. Goal: "+ta.value.trim())});
 body.append(section("Plan → Build",ta,h("div",{class:"studio-actions"},make,build),out));
}
function rankFiles(f,query){const terms=query.toLowerCase().split(/\W+/).filter(x=>x.length>2);return Object.entries(f).map(([path,c])=>({path,score:terms.reduce((n,t)=>n+(path.toLowerCase().includes(t)?5:0)+(c.toLowerCase().includes(t)?1:0),0)})).sort((a,b)=>b.score-a.score);}
async function search(body){
 const input=h("input",{placeholder:"Search project…"}),out=h("div",{class:"search-results"});
 const run=async()=>{out.replaceChildren();const f=await files(),term=input.value.trim().toLowerCase();if(!term)return;for(const[p,c]of Object.entries(f)){if(p.toLowerCase().includes(term)||c.toLowerCase().includes(term)){const n=c.toLowerCase().indexOf(term);out.append(h("button",{class:"search-hit",text:p+" — "+(n>=0?c.slice(Math.max(0,n-50),n+120).replace(/\s+/g," "):"filename match"),onclick:()=>core().setActive(p,c)}));}}};
 input.addEventListener("input",run);body.append(section("Workspace Search",input,out));
}
async function preview(body){
 const f=await files(),frame=h("iframe",{class:"studio-preview",sandbox:"allow-scripts"});frame.srcdoc=buildPreview(f);
 frame.addEventListener("load",()=>{try{frame.contentWindow.document.addEventListener("click",e=>{e.preventDefault();lastSelectedPreview=e.target.tagName.toLowerCase()+(e.target.id?"#"+e.target.id:"")+(e.target.className?"."+String(e.target.className).trim().replace(/\s+/g,"."):"");core().toast("Selected "+lastSelectedPreview);});}catch{}});
 const refresh=h("button",{class:"button secondary",text:"Refresh",onclick:async()=>frame.srcdoc=buildPreview(await files())});
 const share=h("button",{class:"button secondary",text:"Open preview tab",onclick:()=>{const w=open();if(w){w.document.write(buildPreview(f));w.document.close();}}});
 const visual=h("button",{class:"button primary",text:"Edit selected element",onclick:()=>core().sendPromptText("Modify the UI element "+(lastSelectedPreview||"I select in preview")+" with minimal code changes. Explain the files changed.")});
 body.append(section("Live Preview + Visual Editing",h("div",{class:"studio-actions"},refresh,share,visual),frame));
}
function buildPreview(f){let html=f["index.html"]||Object.entries(f).find(([p])=>p.endsWith("/index.html"))?.[1]||"<main><h1>No index.html found</h1></main>";const css=f["styles.css"]||f["style.css"]||Object.entries(f).filter(([p])=>p.endsWith(".css")).map(x=>x[1]).join("\n");const js=f["script.js"]||Object.entries(f).filter(([p])=>p.endsWith(".js")&&!p.includes("node_modules")).map(x=>x[1]).join("\n");return html.replace("</head>","<style>"+css+"</style></head>").replace("</body>","<script>"+js.replaceAll("</script>","<\\/script>")+"</script></body>");}
function tasks(body){
 const tasks=store.get("tasks",[]),input=h("input",{placeholder:"Add task…"}),list=h("div",{class:"task-list"});
 const redraw=()=>{list.replaceChildren();tasks.forEach((t,i)=>{const row=h("div",{class:"task-row"},h("span",{text:(i+1)+". "+t.text}),h("small",{text:t.status}));row.append(h("button",{class:"text-button",text:"Run",onclick:async()=>{t.status="running";store.set("tasks",tasks);redraw();await createCheckpoint();await core().sendPromptText("Task "+(i+1)+": "+t.text+". Work minimally, report changed files and verification.");t.status="done";store.set("tasks",tasks);redraw();}}));list.append(row);});};
 const add=h("button",{class:"button primary",text:"Add",onclick:()=>{if(input.value.trim()){tasks.push({text:input.value.trim(),status:"queued",created:Date.now()});store.set("tasks",tasks);input.value="";redraw();}}});redraw();body.append(section("Task Queue + Background Tasks",h("div",{class:"inline-form"},input,add),list));
}
async function tools(body){
 const commands=["/fix","/test","/review","/explain","/refactor","/security-check","/optimize","/deploy"];const active=core().getActive();
 const cmdBox=section("Reusable Skills",h("div",{class:"chip-grid"},...commands.map(c=>h("button",{class:"button secondary",text:c,onclick:()=>core().sendPromptText(c+" "+active.path+" — inspect the active code and perform this task with minimal edits.")}))));
 const apiPath=h("input",{value:"/healthz"}),apiOut=h("pre",{class:"studio-output"});const apiBtn=h("button",{class:"button primary",text:"Send GET",onclick:async()=>{try{const r=await fetch(apiPath.value,{redirect:"error"});apiOut.textContent=r.status+" "+r.statusText+"\n"+await r.text();}catch(e){apiOut.textContent=e.message;}}});
 const db=h("button",{class:"button secondary",text:"Database assistant",onclick:()=>core().sendPromptText("Inspect SQL/schema/migration files in this project. Explain the schema and propose only safe, reversible database changes. Warn before destructive operations.")});
 const arch=h("button",{class:"button secondary",text:"Architecture map",onclick:async()=>{const f=await files();apiOut.textContent=architecture(f);}});
 const deploy=h("button",{class:"button secondary",text:"Deployment plan",onclick:()=>core().sendPromptText("Inspect this project's deployment files and create a safe deployment plan with rollback and verification steps. Do not expose secrets.")});
 const templates=h("div",{class:"chip-grid"});[["Landing page","<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><link rel=\"stylesheet\" href=\"styles.css\"></head><body><main><h1>New project</h1><p>Built with SPARKLE CODER.</p></main><script src=\"script.js\"></script></body></html>"],["Dashboard","<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><link rel=\"stylesheet\" href=\"styles.css\"></head><body><aside>Dashboard</aside><main><h1>Overview</h1></main></body></html>"]].forEach(([name,html])=>templates.append(h("button",{class:"button secondary",text:name,onclick:async()=>{await createCheckpoint();await core().createTextFile("index.html",html);await core().createTextFile("styles.css","body{font-family:system-ui;margin:0;padding:2rem}");core().toast(name+" template created.");}})));
 const shot=h("input",{type:"file",accept:"image/*"}),shotOut=h("small",{text:"No screenshot selected."});shot.onchange=()=>{const f=shot.files?.[0];if(f){store.set("screenshotRef",{name:f.name,size:f.size,type:f.type,created:Date.now()});shotOut.textContent=f.name+" selected as local visual reference. Add a description before sending to AI.";}};
 body.append(cmdBox,section("Project Templates",templates),section("Screenshot / Error Screenshot Workflow",shot,shotOut,h("button",{class:"button secondary",text:"Create reconstruction task",onclick:()=>core().sendPromptText("Reconstruct the referenced screenshot as a responsive web UI. The screenshot is kept locally; use my next description of its layout and styling. Start by asking only for missing visual details you cannot infer.")})),section("API Tester + Database + Architecture + Deploy",h("div",{class:"inline-form"},apiPath,apiBtn),h("div",{class:"studio-actions"},db,arch,deploy),apiOut));
}
function architecture(f){const groups={frontend:[],backend:[],tests:[],config:[],data:[]};for(const p of Object.keys(f)){if(/test|spec/.test(p))groups.tests.push(p);else if(/worker|server|api|backend|\.py$/.test(p))groups.backend.push(p);else if(/html|css|jsx|tsx|vue|svelte/.test(p))groups.frontend.push(p);else if(/sql|migration|schema/.test(p))groups.data.push(p);else groups.config.push(p);}return Object.entries(groups).map(([k,v])=>k.toUpperCase()+"\n"+v.slice(0,30).map(x=>"  • "+x).join("\n")).join("\n\n");}
function memory(body){
 const mem=store.get("memory",""),rules=store.get("rules",""),perm=store.get("permissions","*.env\n*.key\n*.pem\ncredentials*"),secrets=store.get("secretNames",[]);
 const m=h("textarea",{rows:"5"});m.value=mem;const r=h("textarea",{rows:"5"});r.value=rules;const p=h("textarea",{rows:"4"});p.value=perm;const s=h("input",{value:secrets.join(", "),placeholder:"SECRET_NAME, API_TOKEN"});
 const save=h("button",{class:"button primary",text:"Save project intelligence",onclick:()=>{store.set("memory",m.value);store.set("rules",r.value);store.set("permissions",p.value);store.set("secretNames",s.value.split(",").map(x=>x.trim()).filter(Boolean));core().toast("Project intelligence saved.");}});
 body.append(section("Project Memory",m),section("Rules File",r),section("AI File Permissions",p),section("Secrets Manager (names only — never values)",s),save);
}
function featureGrid(body){const grid=h("div",{class:"feature-grid"});features.forEach((x,i)=>{grid.append(h("article",{class:"feature-card"},h("strong",{text:(i+1)+". "+x[0]}),h("p",{text:x[1]}),h("span",{class:"status-badge",text:"Enabled"})));});body.append(grid);}
window.addEventListener("sparkle:usage",e=>{const u=store.get("usage",{in:0,out:0,calls:0});u.in+=Number(e.detail.prompt_tokens||0);u.out+=Number(e.detail.completion_tokens||0);u.calls++;store.set("usage",u);});
window.addEventListener("DOMContentLoaded",inject);
})();