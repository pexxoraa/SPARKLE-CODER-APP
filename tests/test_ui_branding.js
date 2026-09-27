const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../sparkle_coder/ui/app.js'),'utf8');

const modelField=source.slice(
  source.indexOf('<label for="modelId">'),
  source.indexOf('<label for="apiKey">')
);
assert.match(modelField,/SPARKLE Core/);
assert.match(modelField,/SPARKLE Fast/);
assert.match(modelField,/SPARKLE Advanced/);
assert.doesNotMatch(modelField,/NVIDIA|Nemotron|nvidia|nemotron/);

const shortSource=source.slice(
  source.indexOf('function shortModel('),
  source.indexOf('async function action(')
);
const shortModel=new Function(shortSource+'; return shortModel;')();
assert.equal(shortModel('nvidia/nemotron-3-super-120b-a12b'),'SPARKLE Core');
assert.equal(shortModel('nvidia/nemotron-3-nano-30b-a3b'),'SPARKLE Fast');
assert.equal(shortModel('nvidia/nemotron-3-ultra-550b-a55b'),'SPARKLE Advanced');
assert.equal(shortModel('nvidia/unknown'),'SPARKLE AI');

console.log('Branding UI: provider model names stay internal and visible labels use SPARKLE AI names.');