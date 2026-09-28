"use strict";
const CACHE="sparkle-web-v5";
const SHELL=["/","/agent.css","/agent.js","/cloud-adapter.js","/qrcode.js","/scratch.html","/app.css","/app.js","/favicon.svg","/icon-192.png","/icon-512.png","/manifest.webmanifest"];
self.addEventListener("install",event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener("activate",event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith("sparkle-web-")&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener("fetch",event=>{
  const url=new URL(event.request.url);
  // Only the public app shell is available offline. Never cache admin or API data.
  if(event.request.method!=="GET"||url.origin!==self.location.origin||!SHELL.includes(url.pathname)||url.search)return;
  const network=fetch(event.request);
  event.waitUntil(network.then(async response=>{
    if(response.ok&&!response.redirected){const copy=response.clone(),cache=await caches.open(CACHE);await cache.put(event.request,copy);}
  }).catch(()=>{}));
  event.respondWith(network.catch(async()=>{
    const cache=await caches.open(CACHE),cached=await cache.match(event.request);
    return cached||new Response("Offline: this file is not cached.",{status:503,headers:{"Content-Type":"text/plain"}});
  }));
});
