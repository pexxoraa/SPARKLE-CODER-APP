const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const agent=fs.readFileSync(path.join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');
const scratch=fs.readFileSync(path.join(__dirname,'../gateway/public/app.js'),'utf8');
const scratchCss=fs.readFileSync(path.join(__dirname,'../gateway/public/app.css'),'utf8');

assert.match(agent,/id="workspaceModeSwitch"/);
assert.match(agent,/id="cloudWorkspaceMode"[^>]*>Cloud</);
assert.match(agent,/id="browserWorkspaceMode"[^>]*>Browser files</);
assert.match(agent,/id="topAccountButton"[^>]*>Account</);
assert.match(agent,/id="browserWorkspacePanel"/);
assert.match(agent,/src="\/scratch\.html\?embedded=1"/);
assert.doesNotMatch(agent,/Open browser scratch files/);
assert.match(agent,/if\(!available\)setWorkspaceSurface\("browser",\{remember:false\}\)/);
assert.match(agent,/id\("topAccountButton"\)\.onclick=openAccount/);
assert.match(scratch,/embedded=1/);
assert.match(scratchCss,/html\.embedded \.topbar\{display:none\}/);

console.log('Cloud/browser workspace: local files stay inside the main SPARKLE page with account access retained.');