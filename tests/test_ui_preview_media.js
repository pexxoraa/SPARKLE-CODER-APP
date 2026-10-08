"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const source=fs.readFileSync(require("node:path").join(__dirname,"../sparkle_coder/ui/app.js"),"utf8");
function extract(start,end){
  const begin=source.indexOf(start);assert.ok(begin>=0,"Missing "+start);
  const stop=source.indexOf(end,begin);assert.ok(stop>begin,"Missing "+end);
  return source.slice(begin,stop);
}
class El{
  constructor(tag="div",cls="",value=""){
    this.tag=tag;this.className=cls;this.textContent=value||"";this.children=[];this.value="";
    this.disabled=false;this.open=false;this.dataset={};this._srcdoc="";this.srcdocSets=0;
  }
  append(...items){this.children.push(...items);if(this.tag==="select"&&!this.value&&this.children.length)this.value=this.children[0].value;}
  replaceChildren(...items){this.children=[...items];}
  set srcdoc(value){this._srcdoc=value;this.srcdocSets++;}
  get srcdoc(){return this._srcdoc;}
  removeAttribute(name){if(name==="srcdoc")this._srcdoc="";}
  showModal(){this.open=true;}
  close(){this.open=false;}
  focus(){}
}
const elements=new Map(),id=name=>{
  if(!elements.has(name))elements.set(name,new El(name==="previewEntry"?"select":"div"));
  return elements.get(name);
};
const node=(tag,cls,val)=>new El(tag,cls,val);
let files=["index.html","styles.css","dist/about.html"];
let currentHtml='<!doctype html><html><head><link rel="stylesheet" href="data:text/css;base64,YQ=="></head><body>OK</body></html>';
let called=[],filesLoaded=0,popupUrl="",blocked=false;
const api=async(path,body)=>{
  called.push({path,body});
  if(path.endsWith('/files'))return {files};
  if(path.includes('/site-preview?'))return {entry:decodeURIComponent(path.split('entry=')[1]),
    html:currentHtml,assets:2,warnings:["Scripts disabled"]};
  if(path.includes('/image-search?'))return {results:[
    {title:"Mountain.JPG",url:"https://thumb.wikimedia.org/wikipedia/commons/mountain.jpg",
     source_page:"https://commons.wikimedia.org/wiki/File:Mountain.JPG",
     description:"Mountain photo",license:"CC BY-SA 4.0",creator:"Example Photographer"},
    {title:"Unlicensed.JPG",url:"https://upload.wikimedia.org/wikipedia/commons/other.jpg",
     source_page:"https://commons.wikimedia.org/wiki/File:Unlicensed.JPG",
     description:"Unknown",license:"Check source page",creator:""}
  ]};
  if(path.endsWith('/image/import')){
    if(blocked)throw Error("Engine is busy");
    return {path:"assets/mountain.jpg",source_note:"assets/mountain.jpg.source.txt"};
  }
  if(path.endsWith('/image/create'))return {path:"assets/new-art.svg",message:"Created an SVG illustration."};
  throw Error("Unexpected API call: "+path);
};
let projected="p1";
let interval;
let opened="";
let lastObjectURL="";
class URLClone extends URL{static createObjectURL(blob){lastObjectURL="blob:preview-safe";return lastObjectURL;}static revokeObjectURL(){}}
const fakeWindow={open(url,target,features){opened=url;
  assert.equal(target,"_blank");assert.match(features,/noopener,noreferrer/);
}};
const sandbox=[
 'let projectId="p1",transferBusy=false;',
 'const busy=()=>false;',
 extract('let previewProjectId=', 'function renderProjects()'),
 'return {openSitePreview,refreshSitePreview,previewNewTab,openMediaLibrary,searchProjectImages,importProjectImage,createProjectGraphic,changeProject:p=>{projectId=p;},getPreview:()=>previewData};'
].join("\n");
const apiFixture=new Function("id","node","api","document","URL","Blob","window","btoa","setTimeout","setInterval","loadFiles","toast","action",sandbox)(
 id,node,api,{hidden:false},URLClone,Blob,fakeWindow,global.btoa,
 ()=>{},fn=>{interval=fn;},async()=>{filesLoaded++},()=>{},fn=>fn()
);
(async()=>{
  await apiFixture.openSitePreview();
  assert.equal(id("previewDialog").open,true);
  assert.equal(id("previewEntry").children.length,2);
  assert.equal(id("previewEntry").children[0].value,"index.html");
  assert.equal(id("sitePreviewFrame").srcdocSets,1);
  assert.match(id("sitePreviewFrame").srcdoc,/<!doctype html>/i);
  assert.equal(id("openPreviewTab").disabled,false);
  await apiFixture.refreshSitePreview();
  assert.equal(id("sitePreviewFrame").srcdocSets,1,"No change should preserve the preview state");
  currentHtml=currentHtml.replace("OK","Updated");
  await apiFixture.refreshSitePreview();
  assert.equal(id("sitePreviewFrame").srcdocSets,2);
  assert.match(id("sitePreviewFrame").srcdoc,/Updated/);
  apiFixture.previewNewTab();
  assert.equal(opened,"blob:preview-safe");
  assert.match(lastObjectURL,/blob:/);
  assert.match(source,/sandbox=""/,"Previews must have no allow-scripts or allow-same-origin");
  assert.match(source,/referrerpolicy="no-referrer"/);

  await apiFixture.openMediaLibrary();
  id("imageQuery").value="mountain landscape";
  await apiFixture.searchProjectImages({preventDefault(){}});
  assert.equal(id("imageResults").children.length,2);
  const first=id("imageResults").children[0].children[1];
  assert.equal(first.children[3].disabled,false);
  assert.equal(id("imageResults").children[1].children[1].children[3].disabled,true);
  await first.children[3].onclick();
  assert.equal(filesLoaded,1);
  assert.match(id("mediaResult").textContent,/Attribution note/);
  blocked=true;
  await first.children[3].onclick();
  assert.match(id("mediaResult").textContent,/Engine is busy/);
  blocked=false;
  id("graphicTitle").value="Geometric art";
  id("graphicStyle").value="night";
  id("graphicPrimary").value="#123456";
  id("graphicSecondary").value="#abcdef";
  await apiFixture.createProjectGraphic({preventDefault(){}});
  assert.equal(filesLoaded,2);
  const create=called.find(x=>x.path.endsWith('/image/create'));
  assert.deepEqual(create.body,{title:"Geometric art",style:"night",primary:"#123456",secondary:"#abcdef"});
  apiFixture.changeProject("p2");
  await apiFixture.refreshSitePreview();
  assert.match(id("sitePreviewFrame").srcdoc,/Updated/);
  console.log("UI preview/media: sandboxed page preview, fresh snapshots, detached tab, selected credited images, busy errors and SVG creation passed.");
})().catch(error=>{console.error(error);process.exitCode=1;});
