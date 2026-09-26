// Only the gateway can assert an account to the owner-hosted coding engine.
export function engineConfigured(env){
  try{const url=new URL(env.ENGINE_ORIGIN);return /^[A-Za-z0-9_-]{43,}$/.test(env.ENGINE_SECRET||'')&&url.protocol==='https:'&&!url.username&&!url.password&&url.pathname==='/'&&!url.search&&!url.hash;}
  catch{return false;}
}
export async function proxyEngine(request,env,account){
  if(!engineConfigured(env))return Response.json({error:'The owner must connect the coding server before cloud projects can run.'},{status:503});
  const origin=new URL(env.ENGINE_ORIGIN);
  if(origin.protocol!=='https:'||origin.username||origin.password||origin.pathname!=='/'||origin.search||origin.hash)
    return Response.json({error:'The owner must configure a valid HTTPS coding-server origin.'},{status:503});
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
    const response=await perform(target,{method:request.method,redirect:'error',signal:AbortSignal.timeout(60000),
      headers:{'X-Sparkle-Relay':env.ENGINE_SECRET,'X-Sparkle-Device':request.headers.get('Authorization').slice(7),'X-Sparkle-Account':encoded,
        ...(payload?{'Content-Type':'application/json'}:{})},...(payload?{body:payload}:{})});
    const headers=new Headers({'Cache-Control':'no-store'});
    for(const key of ['Content-Type','Content-Disposition'])if(response.headers.has(key))headers.set(key,response.headers.get(key));
    return new Response(response.body,{status:response.status,headers});
  }catch{return Response.json({error:'The coding server could not be reached. Saved runs can be resumed when it returns.'},{status:502});}
}
