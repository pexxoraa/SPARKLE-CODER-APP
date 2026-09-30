const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const agent=fs.readFileSync(path.join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');

assert.match(agent,/id="workspaceModeSwitch"/);
assert.match(agent,/class="workspace-mode-label">Cloud</);
assert.match(agent,/id="topAccountButton"[^>]*>Account</);
assert.doesNotMatch(agent,/Browser files/);
assert.doesNotMatch(agent,/browserWorkspaceMode/);
assert.doesNotMatch(agent,/browserWorkspacePanel/);
assert.doesNotMatch(agent,/openBrowserFilesInline/);
assert.doesNotMatch(agent,/setWorkspaceSurface/);
assert.doesNotMatch(agent,/sparkleWorkspaceMode/);
assert.doesNotMatch(agent,/scratch\?embedded=1/);
assert.doesNotMatch(agent,/Open browser scratch files/);
assert.doesNotMatch(agent,/Use browser files here/);
assert.match(agent,/id\("workspaceModeSwitch"\)\.hidden=false/);
assert.match(agent,/id\("topAccountButton"\)\.onclick=openAccount/);
assert.match(agent,/No cloud projects yet/);
assert.match(agent,/Reconnecting cloud projects…/);
assert.match(agent,/function scheduleCloudReconnect/);
assert.match(agent,/setTimeout\(async\(\)=>\{/);
assert.match(agent,/Cloud projects reconnected/);
assert.match(agent,/appState\.account\?\.ready&&appState\.engine\?\.available/);
assert.match(agent,/isCloud&&!\(appState\.account\?\.ready&&appState\.engine\?\.available\)/);

console.log('Cloud workspace UI: only Cloud and Account are exposed; Browser files mode is removed.');
