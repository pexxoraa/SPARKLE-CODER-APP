"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
for(const relative of ["sparkle_coder/ui/app.js","gateway/public/agent.js"]){
  const source=fs.readFileSync(path.join(__dirname,"..",relative),"utf8");
  assert.doesNotMatch(source,/id="previewButton"/,"Preview must not occupy the sidebar");
  assert.match(source,/id="previewReady"[^>]*hidden/,"Contextual Build preview must start hidden");
  assert.match(source,/id="previewFiles"[^>]*hidden/,"Project files preview must start hidden");
  assert.match(source,/\["previewReady","previewFiles"\]/,"Both contextual actions must open existing preview");
  const begin=source.indexOf("function renderContextualPreview() {");
  const end=source.indexOf("function renderFileButtons() {",begin);
  assert.ok(begin>0&&end>begin);
  const els={previewReady:{hidden:true},previewFiles:{hidden:true}};
  const test=new Function("id",`
    let projectId="",loadedFilesProjectId="",fileLoadError="",files=[],isCloud=true,
      appState={engine:{available:true}};
    ${source.slice(begin,end)}
    return (project,loaded,list,available=true,error="")=>{
      projectId=project;loadedFilesProjectId=loaded;files=list;
      appState.engine.available=available;fileLoadError=error;
      renderContextualPreview();
      return [id("previewReady").hidden,id("previewFiles").hidden];
    };
  `)(name=>els[name]);
  assert.deepEqual(test("project-a","project-a",[]),[true,true],"Empty project hides preview");
  assert.deepEqual(test("project-a","project-a",["main.py","package.json","app.jsx"]),[true,true],"Backend/React source without built HTML hides preview");
  assert.deepEqual(test("project-a","project-a",["index.html","styles.css"]),[false,false],"Static website displays preview");
  assert.deepEqual(test("project-b","project-a",["index.html"]),[true,true],"Switch must not reuse previous project's page");
  assert.deepEqual(test("project-b","project-b",["dist/index.HTML"]),[false,false],"Built HTML is previewable");
  assert.deepEqual(test("project-b","project-b",["dist/index.HTML"],false),[true,true],"Offline cloud hides preview");
  assert.deepEqual(test("project-b","project-b",["dist/index.HTML"],true,"Network failure"),[true,true],"Failed file load hides preview");
  assert.deepEqual(test(null,"project-b",["index.html"]),[true,true],"No project hides preview");
  assert.match(source,/loadedFilesProjectId=requestedProject/,"File listing must belong to selected project");
  assert.match(source,/files=\[\];loadedFilesProjectId=""/,"Cleared projects must clear preview capability");
}
console.log("Contextual preview: non-web projects have no preview UI; static HTML projects do, with project-switch and offline safeguards.");
