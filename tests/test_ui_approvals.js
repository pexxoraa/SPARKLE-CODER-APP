const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');

assert.ok(app.includes('SPARKLE needs your permission'),'Local approval UI must remain available.');
assert.ok(app.includes('id("supervisionChoice").hidden=isCloud'));
assert.ok(app.includes('id("approvalCard").hidden=isCloud||'));
assert.ok(app.includes('id("monitorAttention").hidden=isCloud||'));
assert.ok(app.includes('review_edits:isCloud?false:id("reviewEdits").checked'));
assert.ok(app.includes('Normal coding actions run automatically; protected system actions are blocked.'));
assert.ok(app.includes('id("reviewEdits").disabled=isCloud||'));

console.log('Cloud execution UI: no Allow/Don’t allow interruptions; local approval UI remains available.');
