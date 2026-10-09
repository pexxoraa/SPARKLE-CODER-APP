// Verify that large/active projects are always exportable from both shipped UIs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
for (const rel of ['sparkle_coder/ui/app.js', 'gateway/public/agent.js']) {
  const source = fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
  const start = source.indexOf('function renderContextualPreview()');
  const end = source.indexOf('function openEditor(', start);
  assert.ok(start >= 0 && end > start, `${rel} includes file action state`);
  const fn = source.slice(start, end);
  const elements = new Map();
  const id = name => {
    if (!elements.has(name)) elements.set(name, {disabled: false, title: '', textContent: ''});
    return elements.get(name);
  };
  const ui = new Function('id', `
    let projectId='project-a', loadedFilesProjectId='', files=[], transferBusy=false, fileLoadError='', selectedFile='', fileData=null;
    let running=true, connected=true, isCloud=true;
    let appState={account:{ready:true},engine:{available:true}};
    function busy(){return running;}
    ${fn}
    return {renderFileButtons,setRunning:v=>{running=v;},setConnected:v=>{appState.engine.available=v;},
      setLoadError:v=>{fileLoadError=v;},setProject:v=>{projectId=v;},setTransfer:v=>{transferBusy=v;}};
  `)(id);
  ui.renderFileButtons();
  assert.equal(id('downloadProject').disabled, false, `${rel}: ZIP during active work`);
  assert.equal(id('newFile').disabled, true, `${rel}: editing still blocked during work`);
  assert.match(id('downloadProject').textContent, /current ZIP/i);
  ui.setLoadError('Too many files to display'); ui.renderFileButtons();
  assert.equal(id('downloadProject').disabled, false, `${rel}: listing failures must not block ZIP`);
  ui.setRunning(false); ui.setLoadError(''); ui.renderFileButtons();
  assert.equal(id('downloadProject').disabled, false, `${rel}: ZIP after completion`);
  ui.setConnected(false); ui.renderFileButtons();
  assert.equal(id('downloadProject').disabled, true, `${rel}: offline protects user`);
  ui.setConnected(true); ui.setTransfer(true); ui.renderFileButtons();
  assert.equal(id('downloadProject').disabled, true, `${rel}: import still protects file consistency`);
  ui.setTransfer(false); ui.setProject(null); ui.renderFileButtons();
  assert.equal(id('downloadProject').disabled, true, `${rel}: project needed`);
  const cloud = source.slice(source.indexOf('function renderCloudState()'), source.indexOf('if(isCloud){', source.indexOf('function renderCloudState()')));
  assert.ok(!cloud.includes('"downloadProject"])id(name).disabled=!available||!!busy()'),
    `${rel}: cloud state must not disable download during a running task`);
}
console.log('ZIP exports remain enabled during active generation and file-list errors, with offline/edit safeguards.');
