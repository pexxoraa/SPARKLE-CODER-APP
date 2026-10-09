"use strict";
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');
const start=source.indexOf('// Integrated project IDE.');
const end=source.indexOf('function openEditor(create=false)',start);
assert.ok(start>0&&end>start);
const code=source.slice(start,end);
class El{
  constructor(tag='div',cls='',content=''){
    Object.assign(this,{tag,className:cls,textContent:content,value:'',children:[],hidden:false,disabled:false,
      readOnly:false,style:{},dataset:{},selectionStart:0,selectionEnd:0,scrollTop:0,scrollLeft:0,innerHTML:''});
    const state=new Set();this.classList={toggle:(cls,on)=>{if(on)state.add(cls);else state.delete(cls)},contains:cls=>state.has(cls)};
  }
  append(...elems){this.children.push(...elems)}
  replaceChildren(...elems){this.children=[...elems]}
  setAttribute(k,v){this[k]=v}
  focus(){this.focused=true}
  setSelectionRange(a,b){this.selectionStart=a;this.selectionEnd=b}
  setRangeText(t,a,b){this.value=this.value.slice(0,a)+t+this.value.slice(b);this.setSelectionRange(a+t.length,a+t.length)}
}
function fixture(){
  const elements=new Map(),id=k=>{if(!elements.has(k))elements.set(k,new El());return elements.get(k)};
  const calls=[];let actual=new Map([['src/main.js',{content:'const answer = 42;',sha256:'hash1'}],['docs/note.txt',{content:'hello',sha256:'hash2'}]]);
  let running=false,failSave=false,confirmCalls=0,unloadHandler,promptValue='src/new.py';
  const window={prompt:()=>promptValue,confirm:()=>{confirmCalls++;return false},addEventListener:(name,fn)=>{if(name==='beforeunload')unloadHandler=fn}};
  const api=async(route,body)=>{
    calls.push({route,body});
    if(route.includes('/file?path=')){
      const name=decodeURIComponent(route.split('path=')[1]);const value=actual.get(name);
      if(!value)throw Error('not found');return {...value,path:name,binary:false,truncated:false,redacted:false};
    }
    if(route.endsWith('/save-file')){
      if(failSave)throw Error('File changed or hash was omitted');
      const previous=actual.get(body.path);
      if((previous?.sha256||null)!==body.expected_sha256)throw Error('File changed on disk');
      actual.set(body.path,{content:body.content,sha256:'hash'+(1+calls.length)});return {path:body.path};
    }
    throw Error('Unexpected route '+route);
  };
  const node=(tag,cls,content)=>new El(tag,cls,content);
  const f=new Function('id','node','api','window','searchTerms','matchSearch','TextEncoder','busy',`
    let projectId='p1',loadedFilesProjectId='p1',files=['src/main.js','docs/note.txt'],view='ide',fileLoadError='',transferBusy=false;
    let appState={engine:{available:true}};
    function render(){return null}
    async function loadFiles(){return null}
    async function loadHistory(){return null}
    ${code}
    return {openIde,ideOpenFile,ideNewFile,ideClose,ideKeydown,ideInput,ideSaveActive,ideRepaintCode,ideHighlightSource,ideActive,ideHasUnsaved,renderIdeEditor,
      switchProject:p=>{projectId=p},setFiles:(next)=>{files=next;loadedFilesProjectId=projectId},setLoaded:p=>{loadedFilesProjectId=p},
      saveState:()=>({saving:ideSaving,projectId,selected:ideSelected.get(projectId)})};
  `)(id,node,api,window,t=>String(t).toLowerCase().split(/\s+/).filter(Boolean),
    (path,terms)=>terms.every(t=>String(path).toLowerCase().includes(t)),TextEncoder,()=>running);
  return {...f,id,calls,actual,window,setRunning:v=>{running=v},setFail:v=>{failSave=v},setPrompt:v=>{promptValue=v},unload:()=>unloadHandler,confirmationCount:()=>confirmCalls};
}
// The browser executes these functions in a shared scope: our harness's run
// state must live in that scope as a controlled variable.
const original=fs.readFileSync(path.join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');
(async()=>{
  const f=fixture();
  assert.match(original,/data-view="ide"/, 'IDE must appear in workspace navigation');
  assert.match(original,/id="ideView"/, 'IDE is a first-class workspace page');
  assert.match(original,/id="ideCode"/, 'IDE has an accessible source editor');
  await f.openIde();
  assert.equal(f.id('ideTree').children.length,2,'Root folders displayed');
  await f.ideOpenFile('src/main.js');
  assert.equal(f.id('ideCode').value,'const answer = 42;');
  assert.equal(f.id('ideSave').disabled,true);
  assert.equal(f.id('ideLanguage').textContent,'JavaScript');
  assert.match(f.id('ideHighlight').innerHTML,/ide-token-keyword/);
  assert.equal(f.ideHighlightSource('<script>','index.html').includes('&lt;script&gt;'),true,'Untrusted code must be HTML escaped');
  f.id('ideCode').value='const answer = 99;';f.ideInput();
  assert.equal(f.ideHasUnsaved(),true);
  assert.equal(f.id('ideSave').disabled,false);
  await f.ideOpenFile('docs/note.txt');
  assert.equal(f.id('ideCode').value,'hello');
  await f.ideOpenFile('src/main.js');
  assert.equal(f.id('ideCode').value,'const answer = 99;','Unsaved changes survive tab switches');
  f.switchProject('p2');f.setFiles(['src/main.js']);
  assert.equal(f.ideActive(),null,'Tabs are isolated by project');
  f.switchProject('p1');f.setFiles(['src/main.js','docs/note.txt']);
  assert.equal(f.ideActive().content,'const answer = 99;','Switching projects must preserve unsaved documents');
  f.renderIdeEditor();
  f.setFail(true);
  await assert.rejects(f.ideSaveActive(),/File changed/);
  assert.equal(f.ideHasUnsaved(),true,'Conflict never discards local text');
  f.setFail(false);
  await f.ideSaveActive();
  assert.equal(f.actual.get('src/main.js').content,'const answer = 99;');
  assert.equal(f.ideHasUnsaved(),false);
  f.setPrompt('src/new.py');f.ideNewFile();
  assert.equal(f.ideActive().created,true);
  f.id('ideCode').value='print("Hello")';f.ideInput();
  await f.ideSaveActive();assert.equal(f.actual.get('src/new.py').content,'print("Hello")');
  f.id('ideCode').value='new draft';f.ideInput();
  f.ideClose('src/new.py');
  assert.equal(f.ideActive().content,'new draft','Closing dirty tab asks confirmation');
  assert.equal(f.confirmationCount(),1);
  f.id('ideCode').value='x'.repeat(200001);f.ideInput();
  await assert.rejects(f.ideSaveActive(),/200 KB/);
  assert.equal(f.id('ideCode').value.length,200001,'Oversize input is preserved');
  assert.equal(f.actual.get('src/new.py').content,'print("Hello")','Oversize file never saved');
  f.setRunning(true);f.renderIdeEditor();
  assert.equal(f.id('ideCode').readOnly,true,'Agent activity makes the IDE read-only');
  assert.equal(f.id('ideSave').disabled,true,'Cannot save over an active agent');
  await assert.rejects(f.ideSaveActive(),/Wait for the coding agent/);
  f.setRunning(false);f.renderIdeEditor();
  assert.equal(f.id('ideCode').readOnly,false,'Editing resumes after active agent finishes');
  const beforeunload={preventDefault(){this.prevented=true}};f.unload()(beforeunload);
  assert.equal(beforeunload.prevented,true,'Unload warns about unsaved code');
  console.log('IDE: tab persistence, project isolation, syntax escaping, hash-check saving, conflicts, new files, close guard, oversize guard, unload protection passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
