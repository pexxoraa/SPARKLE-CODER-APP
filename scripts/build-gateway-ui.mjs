// The full browser app is built from the same UI as the Python engine.
// Keep the standalone scratch editor available for existing browser-only files.
import {readFile,writeFile,copyFile} from 'node:fs/promises';
const source=new URL('../sparkle_coder/ui/',import.meta.url);
const target=new URL('../gateway/public/',import.meta.url);
for(const name of ['app.js','app.css'])await copyFile(new URL(name,source),new URL(name==='app.js'?'agent.js':'agent.css',target));
let html=await readFile(new URL('index.html',source),'utf8');
html=html.replace('<html lang="en">','<html lang="en" data-runtime="cloud">')
  .replace('/app.css','/agent.css')
  .replace('<script src="/app.js" defer></script>','<link rel="manifest" href="/manifest.webmanifest">\n  <meta name="theme-color" content="#0b0f14">\n  <script src="/cloud-adapter.js" defer></script>\n  <script src="/agent.js" defer></script>')
  .replace('Build, inspect, and verify software on your own computer.','Build, inspect, and verify software in your cloud project.');
await writeFile(new URL('index.html',target),html);
console.log('Gateway UI built from the shared full agent interface.');
