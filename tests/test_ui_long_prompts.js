const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
for(const rel of ['sparkle_coder/ui/app.js','gateway/public/agent.js']){
  const source=fs.readFileSync(path.join(__dirname,'..',rel),'utf8');
  assert.doesNotMatch(source,/id="goal"[^>]*maxlength="12000"/);
  assert.doesNotMatch(source,/field\.maxLength=12000/);
  assert.match(source,/goal\.length>48000/);
  assert.match(source,/new TextEncoder\(\)\.encode\(goal\)\.length>131072/);
  assert.match(source,/No text was removed/);
}
console.log('Large-prompt composer and edit interface keep pasted text intact and validate size explicitly.');
