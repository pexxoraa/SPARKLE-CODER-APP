const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');

for(const text of [
  'SPARKLE needs your permission',
  'Why am I seeing this?',
  'not a browser or terminal permission',
  'Technical details',
  'Allow this time',
  'Don’t allow',
  'Why SPARKLE wants this:',
  'SPARKLE asks before protected actions.'
]) assert.ok(app.includes(text),'Missing approval copy: '+text);

for(const oldText of [
  'Permission to run a command',
  'This command runs with your configured permissions',
  '>Deny<',
  '>Allow once<'
]) assert.ok(!app.includes(oldText),'Old terminal-style approval copy returned: '+oldText);

console.log('Approval UI: browser safety prompt uses simple choices and keeps technical details optional.');
