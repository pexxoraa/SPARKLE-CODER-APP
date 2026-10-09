// Only the gateway can assert an account to the owner-hosted coding engine.
function validEngineOrigin(value){
  try{
    const url=new URL(value),host=url.hostname.toLowerCase();
    // Enforce the same public HTTPS origin policy for both saved runtime
    // configuration and environment fallback. Never relay device credentials
    // to loopback, literal IP addresses or localhost aliases.
    const literalIp=/^(?:\d{1,3}\.){3}\d{1,3}$/.test(host)||host.includes(':');
    return url.protocol==='https:'&&!url.username&&!url.password&&url.pathname==='/'&&
      !url.search&&!url.hash&&host.includes('.')&&host!=='localhost'&&
      !host.endsWith('.localhost')&&!literalIp;
  }catch{return false;}
}
async function runtimeEngineOrigin(env){
  if(env.DB){
    try{
      const row=await env.DB.prepare("SELECT value FROM runtime_config WHERE key='engine_origin'").first();
      if(row?.value&&validEngineOrigin(row.value))return row.value;
    }catch{}
  }
  return validEngineOrigin(env.ENGINE_ORIGIN)?env.ENGINE_ORIGIN:null;
}
export async function engineConfigured(env){
  return /^[A-Za-z0-9_-]{43,}$/.test(env.ENGINE_SECRET||'')&&Boolean(await runtimeEngineOrigin(env));
}
export async function proxyEngine(request,env,account){
  const originValue=await runtimeEngineOrigin(env);
  if(!/^[A-Za-z0-9_-]{43,}$/.test(env.ENGINE_SECRET||'')||!originValue)
    return Response.json({error:'The owner must connect the coding server before cloud projects can run.'},{status:503});
  const origin=new URL(originValue);
  if(!['GET','POST'].includes(request.method))return Response.json({error:'Method not allowed.'},{status:405});
  const url=new URL(request.url),path=url.pathname.slice('/api/engine'.length);
  if(!path.startsWith('/')||path.includes('%')||path.includes('\\'))return Response.json({error:'Invalid engine route.'},{status:400});
  const maximum=30*1024*1024;
  if(Number(request.headers.get('Content-Length')||0)>maximum)return Response.json({error:'Import is too large.'},{status:413});
  let payload;
  if(request.method==='POST'){
    if(!request.headers.get('Content-Type')?.startsWith('application/json'))return Response.json({error:'Use JSON.'},{status:415});
    const reader=request.body?.getReader(),chunks=[];let size=0;
    if(!reader)return Response.json({error:'Request body is missing.'},{status:400});
    while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>maximum){await reader.cancel();return Response.json({error:'Import is too large.'},{status:413});}chunks.push(value);}
    payload=new Uint8Array(size);let offset=0;for(const chunk of chunks){payload.set(chunk,offset);offset+=chunk.length;}
  }
  const receipt={id:account.id,name:account.name,email:account.email,status:account.status,ready:true,kind:account.kind,
    device_status:account.device_status,request_id:account.device_id,requested_at:account.device_created,
    balance_tokens:account.balance,held_tokens:account.held,available_tokens:account.balance-account.held};
  const encoded=btoa(Array.from(new TextEncoder().encode(JSON.stringify(receipt)),b=>String.fromCharCode(b)).join(''));
  const target=origin.origin+'/api'+path+url.search;
  try{
    const perform=env.ENGINE?.fetch?.bind(env.ENGINE)||fetch;
    const response=await perform(target,{method:request.method,redirect:'manual',signal:AbortSignal.timeout(60000),
      headers:{'X-Sparkle-Relay':env.ENGINE_SECRET,'X-Sparkle-Device':request.headers.get('Authorization').slice(7),'X-Sparkle-Account':encoded,
        ...(payload?{'Content-Type':'application/json'}:{})},...(payload?{body:payload}:{})});
    // Workers support manual redirects, not redirect:'error'. Never forward relay credentials.
    if(response.status>=300&&response.status<400){await response.body?.cancel();return Response.json({error:'The coding server redirected. The owner must configure its final HTTPS address.'},{status:502});}
    const headers=new Headers({'Cache-Control':'no-store'});
    for(const key of ['Content-Type','Content-Disposition'])if(response.headers.has(key))headers.set(key,response.headers.get(key));
    return new Response(response.body,{status:response.status,headers});
  }catch{return Response.json({error:'The coding server could not be reached. Saved runs can be resumed when it returns.'},{status:502});}
}
