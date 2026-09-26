// Exercise the shipped file controller across missing/offline/failed/recovered projects.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');
const controller = source.slice(source.indexOf('async function loadFiles('),source.indexOf('function renderFileList('));
function fixture(cloud=true){
  const elements=new Map(),calls=[],views=[];
  const id=name=>{if(!elements.has(name))elements.set(name,{});return elements.get(name);};
  let error='',response={files:['src/main.py']};
  const api=async(path,body)=>{calls.push({path,body});if(error)throw Error(error);return response;};
  const ui=new Function('id','api','isCloud','changeView',`
    let projectId=null,appState={account:{ready:false},engine:{available:false,message:'Request account access.'}},
        selectedFile='old.txt',files=['old.txt'],fileData={content:'old account data'},fileLoadError='';
    function renderFileList(){} function renderFileButtons(){}
    ${controller}
    return {loadFiles,openProjectFiles,setState(value,project){appState=value;projectId=project;},
      snapshot:()=>({files,selectedFile,fileData,fileLoadError})};
  `)(id,api,cloud,name=>views.push(name));
  return {...ui,id,calls,views,fail:message=>{error=message;}};
}
(async()=>{
  const f=fixture();await f.loadFiles();
  assert.equal(f.calls.length,0);assert.equal(f.id('filesState').hidden,false);
  assert.equal(f.id('filesStateAction').textContent,'Open account');
  assert.deepEqual(f.snapshot().files,[]);assert.equal(f.snapshot().fileData,null);
  assert.equal(f.id('dropZone').hidden,true);
  f.setState({account:{ready:true},engine:{available:false,message:'Owner engine offline.'}},null);
  await f.loadFiles();assert.equal(f.id('filesStateTitle').textContent,'Cloud projects are offline');
  assert.equal(f.id('filesStateMessage').textContent,'Owner engine offline.');
  assert.equal(f.id('filesStateAction').textContent,'Refresh workspace');
  f.setState({account:{ready:true},engine:{available:true}},'project-a');
  await f.loadFiles();assert.equal(f.id('filesState').hidden,true);
  assert.deepEqual(f.snapshot().files,['src/main.py']);assert.equal(f.id('fileSearch').disabled,false);
  f.fail('The coding server could not be reached.');
  await assert.rejects(f.loadFiles(),/could not be reached/);
  assert.equal(f.id('filesStateTitle').textContent,'Could not open project files');
  assert.equal(f.id('filesState').hidden,false);assert.deepEqual(f.snapshot().files,[]);
  assert.equal(f.id('fileSearch').disabled,true);
  f.fail('');await f.loadFiles();assert.equal(f.id('filesState').hidden,true);
  const before=f.calls.length;await f.openProjectFiles();
  assert.deepEqual(f.views,['files']);assert.equal(f.calls.length,before,'Cloud folder action must not call the host OS API');
  const desktop=fixture(false);desktop.setState({},'desktop-project');await desktop.openProjectFiles();
  assert.equal(desktop.calls[0].path,'/open-folder');assert.equal(desktop.calls[0].body.project_id,'desktop-project');
  console.log('Project files: offline/account states, stale-file clearing, recovery and cloud folder navigation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
