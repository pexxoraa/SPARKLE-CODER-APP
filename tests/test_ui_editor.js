// Exercise the shipped controller with slow/failing saves, without a DOM library.
"use strict";
const assert=require('node:assert/strict');
const fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');
const controller=source.slice(source.indexOf('function openEditor('),source.indexOf('function renderSupervision('));
function fixture(api){
  const elements=new Map();
  function id(name){if(!elements.has(name))elements.set(name,{value:'',hidden:false,disabled:false,readOnly:false,open:false,showModal(){this.open=true;},close(){this.open=false;},focus(){}});return elements.get(name);}
  const create=new Function('id','api','assert',`
    let projectId='project-a',selectedFile='src/a.txt',fileData={path:'src/a.txt',sha256:'a'.repeat(64),content:'original'},editTarget=null,editorSaving=false,transferBusy=false;
    const busy=()=>false,toast=()=>{},action=fn=>fn(),loadFiles=async()=>{},loadHistory=async()=>{},openFile=async()=>{},window={confirm:()=>true};
    ${controller}
    return {openEditor,saveEditor,deleteSelectedFile,setProject:value=>{projectId=value;},setPreview:value=>{fileData=value;},saving:()=>editorSaving};`);
  return {...create(id,api,assert),id};
}
async function check(){
  let finish,calls=[];
  const f=fixture(async(path,body)=>{calls.push({path,body});await new Promise(resolve=>{finish=resolve;});return {path:body.path};});
  f.openEditor();assert.equal(f.id('editorContent').value,'original');f.id('editorContent').value='edited';
  const save=f.saveEditor();assert.equal(f.saving(),true);assert.equal(f.id('editorContent').readOnly,true);
  f.setProject('project-b');await f.saveEditor();assert.equal(calls.length,1);
  finish();await save;assert.equal(calls[0].path,'/projects/project-a/save-file');assert.equal(calls[0].body.expected_sha256,'a'.repeat(64));
  assert.equal(f.id('editorDialog').open,false);assert.equal(f.saving(),false);
  const bad=fixture(async()=>{throw Error('File changed. Reopen latest version.');});
  bad.openEditor();bad.id('editorContent').value='keep this draft';await bad.saveEditor();
  assert.equal(bad.id('editorDialog').open,true);assert.equal(bad.id('editorContent').value,'keep this draft');
  assert.equal(bad.id('editorError').hidden,false);assert.match(bad.id('editorError').textContent,/File changed/);
  assert.equal(bad.id('editorContent').readOnly,false);
  bad.setPreview({path:'src/other.txt',sha256:'b'.repeat(64),content:'wrong preview'});assert.throws(()=>bad.openEditor(),/Open a complete text file/);
  console.log('File editor: captured project/hash, one save at a time, retained failed drafts and stale previews passed.');
}
check().catch(error=>{console.error(error);process.exitCode=1;});
