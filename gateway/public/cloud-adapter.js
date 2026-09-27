"use strict";
// Transport for the shared full UI. Account access stays on the Worker; all
// project/agent routes go through its authenticated engine proxy.
window.SparkleCloud=(()=>{
  let info={},account=null,version=0;
  function secret(){
    let value=localStorage.getItem('sparkle_device_secret');
    if(!value){value=btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(48)))).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');localStorage.setItem('sparkle_device_secret',value);}
    return value;
  }
  async function send(path,body){return fetch(path,{method:body===undefined?'GET':'POST',cache:'no-store',redirect:'error',
    headers:{Authorization:'Bearer '+secret(),...(body===undefined?{}:{'Content-Type':'application/json'})},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});}
  async function read(response){
    let value;try{value=await response.json();}catch{throw new Error('The server returned an unreadable response. Retry in this browser.');}
    if(!response.ok||value?.error)throw new Error(value?.error||'Request failed ('+response.status+').');
    if(!value||Array.isArray(value)||typeof value!=='object')throw new Error('The server did not confirm this request.');
    return value;
  }
  function receipt(value){
    if(typeof value.id!=='string'||!value.id||!['active','pending'].includes(value.device_status)||!['signup','recovery'].includes(value.kind)||typeof value.ready!=='boolean')throw new Error('The server did not confirm your account request. Retry here to preserve the same request identity.');
    return {...info,...value,enabled:true,enrolled:true};
  }
  async function status(){
    const expected=version,response=await send('/api/me');
    const value=response.status===401?{...info,enabled:true,enrolled:false,ready:false}:receipt(await read(response));
    if(expected===version)account=value;
    return account||value;
  }
  function waiting(message){return {version:'0.8.0',projects:[],selected_project:null,active_run:null,experience:'simple',storage:{},account,
    engine:{available:false,message},settings:{base_url:location.origin+'/v1',cloud_gateway_url:location.origin+'/v1',model:'nvidia/nemotron-3-super-120b-a12b',key_configured:true,connected:false,execution:'docker',efficiency:'efficient',max_steps:24,max_seconds:900,max_total_tokens:200000,command_timeout:120,max_tokens:8192,context_chars:24000}};}
  async function request(path,body){
    if(path==='/state'){
      info=await read(await send('/api/info'));await status();
      if(!account.ready)return Response.json(waiting(account.password_required?'Create a login password in Account to continue.':account.enrolled?'Account request received. Open Account to check purchase or recovery approval.':'Open Account to request access to your cloud workspace.'));
      if(!info.engine_configured)return Response.json(waiting('Your account is ready. The owner must connect the coding server to enable cloud projects.'));
      try{
        const result=await read(await send('/api/engine/state'));
        if(!Array.isArray(result.projects)||!result.settings)throw new Error('The coding server returned an incomplete workspace.');
        return Response.json({...result,account});
      }catch(error){return Response.json(waiting(error.message));}
    }
    if(path==='/account')return Response.json(await status());
    if(path==='/account/enroll'){
      version++;const result=receipt(await read(await send('/api/enroll',body)));account=result;return Response.json(result);
    }
    if(path==='/account/login'){
      version++;const result=receipt(await read(await send('/api/login',body)));account=result;return Response.json(result);
    }
    if(path==='/account/password'){
      await read(await send('/api/account/password',body));return Response.json(await status());
    }
    if(path==='/account/coupon')return Response.json(await read(await send('/api/coupons/quote',body)));
    if(path==='/account/payment'){
      const result=await read(await send('/api/payments',body));
      if(typeof result.id!=='string'||!['pending','approved','rejected'].includes(result.status))throw new Error('Payment reference not confirmed. Retry the same reference.');
      account={...account,payments:[{...result,utr:result.payment_required===false?'Coupon claim':body.utr.replace(/\s/g,'').toUpperCase()},...(account?.payments||[]).filter(p=>p.id!==result.id)]};
      return Response.json(account);
    }
    if(path==='/account/reconnect'){
      if(body?.confirm!==true)throw new Error('Confirm sign-out first.');
      localStorage.removeItem('sparkle_device_secret');version++;account={...info,enabled:true,enrolled:false,ready:false};return Response.json(account);
    }
    if(!path.startsWith('/')||path.startsWith('//')||path.includes('://'))throw new Error('Invalid workspace route.');
    return send('/api/engine'+path,body);
  }
  return {request};
})();
