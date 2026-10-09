"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../sparkle_coder/ui/app.js"),"utf8");
const css=fs.readFileSync(path.join(__dirname,"../sparkle_coder/ui/app.css"),"utf8");

function between(a,b){
 const start=source.indexOf(a);
 assert.ok(start>=0,"missing "+a);
 const end=source.indexOf(b,start);
 assert.ok(end>start,"missing "+b);
 return source.slice(start,end);
}
const rankingCode=between("function searchTerms(", "function renderFileList(")+
                  between("function rankSearchItems(", "function renderGlobalSearch(");
const search=new Function(rankingCode+";return {searchTerms,matchSearch,rankSearchItems};")();
assert.deepEqual(search.searchTerms("  SRC  Test  "),["src","test"]);
assert.equal(search.matchSearch("src/components/TestWidget.tsx",["test","src"]),true);
assert.equal(search.matchSearch("src/components/Widget.tsx",["test","src"]),false);
const tasks=[{id:"1",goal:"Build checkout"},{id:"2",goal:"Fix checkout keyboard layout"}];
const ranked=search.rankSearchItems("checkout",["src/checkout.ts","docs/README.md"],tasks);
assert.deepEqual(ranked.results.map(x=>x.id),["src/checkout.ts","1","2"]);
assert.equal(ranked.total,3);
const limited=search.rankSearchItems("",["a","b","c"],[],2);
assert.equal(limited.total,3);
assert.equal(limited.results.length,2);

class El{
 constructor(){this.children=[];this.textContent="";this.value="";this.hidden=false;this.disabled=false;this.open=false;this.dataset={};this.className="";this.attrs={};}
 append(...items){this.children.push(...items);}
 prepend(...items){this.children.unshift(...items);}
 replaceChildren(...items){this.children=[...items];}
 setAttribute(k,v){this.attrs[k]=v;}
 removeAttribute(k){delete this.attrs[k];}
 focus(){this.focused=true;}
 showModal(){this.open=true;}
 close(){this.open=false;}
}
const elements=new Map();
const id=k=>{if(!elements.has(k))elements.set(k,new El());return elements.get(k);};
const node=(tag,cls,text)=>{const e=new El();e.tag=tag;e.className=cls;e.textContent=text||"";return e;};
const errors=[],navigation=[];
let sourceData={files:["src/main.py","README.md"],sessions:[{id:"s1",goal:"Fix search issues"}],truncated:false};
let rejectTasks=false;
const api=async url=>{
 if(url.endsWith("/files"))return {files:sourceData.files,truncated:sourceData.truncated};
 if(url.endsWith("/sessions")){if(rejectTasks)throw Error("History service offline");return {sessions:sourceData.sessions};}
 throw Error("Unexpected request: "+url);
};
const funcs=between("function rankSearchItems(", "let previewProjectId=");
const harness=[
 'let projectId="p1",searchProjectId="",searchFiles=[],searchTasks=[],searchGeneration=0;',
 rankingCode.substring(rankingCode.indexOf("function searchTerms("),rankingCode.indexOf("function rankSearchItems(")),
 funcs,
 'return {openGlobalSearch,renderGlobalSearch,changeProject:p=>projectId=p};'
].join("\n");
const ui=new Function("id","node","api","action","changeView","loadFiles","openFile","loadSession","toast","icon",harness)(
 id,node,api,f=>f(),view=>navigation.push(view),async()=>{},async file=>navigation.push(file),
 async sid=>navigation.push(sid),e=>errors.push(e),icon=>icon
);
(async()=>{
 await ui.openGlobalSearch();
 assert.equal(id("searchDialog").open,true);
 assert.equal(id("searchResults").children.filter(e=>e.tag==="button").length,3);
 id("globalSearch").value="search";
 ui.renderGlobalSearch();
 assert.equal(id("searchResults").children.filter(e=>e.tag==="button").length,1);
 const taskButton=id("searchResults").children.find(e=>e.tag==="button");
 await taskButton.onclick();
 assert.deepEqual(navigation,["s1"]);
 assert.equal(id("searchDialog").open,false);

 // Fallback must say that history could not be loaded instead of implying no results.
 rejectTasks=true;
 await ui.openGlobalSearch();
 assert.match(id("searchStatus").textContent,/Unavailable: History service offline/);
 id("globalSearch").value="no such file";
 ui.renderGlobalSearch();
 assert.match(id("searchStatus").textContent,/No matching/);
 assert.match(id("searchStatus").textContent,/Unavailable: History service offline/);
 rejectTasks=false;
 sourceData.truncated=true;
 await ui.openGlobalSearch();
 assert.match(id("searchStatus").textContent,/File listing was limited/);
 ui.changeProject("p2");
 ui.renderGlobalSearch();
 assert.match(id("searchStatus").textContent,/Project changed/);

 const tokenCode=between("function modelRequestCounts(", "function renderSession(");
 const {renderTokenUsage,modelRequestCounts}=new Function("id",tokenCode+
   ";return {renderTokenUsage,modelRequestCounts};")(id);
 const failures=modelRequestCounts({calls:8,confirmed_calls:5,estimated_calls:1});
 assert.equal(failures.attempts,"8");
 assert.match(failures.detail,/5 confirmed/);
 assert.match(failures.detail,/1 missing usage/);
 assert.match(failures.detail,/2 without accepted response/);
 assert.equal(modelRequestCounts({calls:1,confirmed_calls:0,estimated_calls:0}).attempts,"1");
 assert.match(modelRequestCounts({calls:1,confirmed_calls:0,estimated_calls:0}).detail,/without accepted response/);
 assert.equal(modelRequestCounts({calls:1668}).attempts,"1,668");
 assert.match(modelRequestCounts({calls:1668}).detail,/confirmation details unavailable/);
 assert.match(modelRequestCounts({calls:4,confirmed_calls:5,estimated_calls:0}).detail,/confirmation details unavailable/);
 assert.match(source,/MODEL REQUEST ATTEMPTS/);
 assert.match(source,/id="callsMetricDetail"/);
 renderTokenUsage({prompt_tokens:1300,completion_tokens:700,calls:2});
 assert.equal(id("tokensMetric").textContent,"2,000");
 assert.equal(id("tokensMetricLabel").textContent,"MODEL TOKENS · REPORTED");
 assert.match(id("tokensMetricDetail").textContent,/Input 1,300.*Output 700/);
 renderTokenUsage({prompt_tokens:1300,completion_tokens:700,estimated_calls:1});
 assert.match(id("tokensMetric").textContent,/≈ 2,000/);
 assert.match(id("tokensMetricLabel").textContent,/EST\./);
 assert.match(id("tokensMetric").title,/not exact/);
 renderTokenUsage(undefined);
 assert.equal(id("tokensMetric").textContent,"—");
 renderTokenUsage({prompt_tokens:null,completion_tokens:100,estimated_calls:1});
 assert.equal(id("tokensMetric").textContent,"—","missing provider usage must never display a fabricated total");
 renderTokenUsage({measurement:"separate",prompt_tokens:84,completion_tokens:31,confirmed_calls:1,
                   estimated_calls:2,estimated_prompt_tokens:400,estimated_completion_tokens:100});
 assert.equal(id("tokensMetric").textContent,"115","only provider-reported usage belongs in the confirmed total");
 assert.match(id("tokensMetricLabel").textContent,/PARTIAL/);
 assert.match(id("tokensMetricDetail").textContent,/500 additional, NOT confirmed/);
 assert.match(id("tokensMetric").title,/never billed from this estimate/);
 renderTokenUsage({prompt_tokens:1500,completion_tokens:400,estimated_calls:2});
 assert.equal(id("tokensMetric").textContent,"≈ 1,900","older mixed usage must be explicitly marked approximate");
 assert.match(id("tokensMetric").title,/Legacy run/);

 assert.ok(source.includes('id="advancedSettings"'));
 const advanced=between('id="advancedSettings"',"</details>");
 for(const field of ['executionMode','toolFormat','maxSteps','maxSeconds','maxTotalTokens','commandTimeout','maxTokens','requestTimeout'])
  assert.ok(advanced.includes('id="'+field+'"'),"Advanced settings should contain "+field);
 assert.match(source,/id="menuButton" aria-label="Open navigation" aria-expanded="false"/);
 assert.match(source,/function closeSidebar\(/);
 assert.match(source,/Ctrl\/⌘ Shift F/);
 assert.match(css,/@media\(max-width:760px\)/);
 assert.match(css,/\.search-result/);
 assert.match(css,/\.simple-mode \.navigation \[data-view="monitor"\]\{display:flex\}/);

 console.log("Minimal UI: unified filename/task search, offline results, project isolation, verified/estimated token labeling, advanced settings and mobile navigation passed.");
})().catch(e=>{console.error(e);process.exitCode=1;});
