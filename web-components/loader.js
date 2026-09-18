const CDN_ROOT='https://cdn.jsdelivr.net/gh/yxsicd/mcpgitrelease@main/web-components/';

async function readResponse(url,options={}){
  const r=await fetch(url,{cache:'no-store',credentials:'omit',...options});
  if(!r.ok)throw new Error(`component fetch failed: ${r.status} ${url}`);
  return r;
}

async function readJson(url){
  return (await readResponse(url)).json();
}

function sriFromDigest(bytes){
  let binary='';
  for(const b of bytes)binary+=String.fromCharCode(b);
  return 'sha256-'+btoa(binary);
}

async function importVerified(url,expectedIntegrity){
  const r=await readResponse(url,{cache:'force-cache'});
  const bytes=await r.arrayBuffer();
  if(expectedIntegrity){
    const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
    const actual=sriFromDigest(digest);
    if(actual!==expectedIntegrity)throw new Error(`component integrity mismatch: ${url}`);
  }
  const blob=URL.createObjectURL(new Blob([bytes],{type:'text/javascript'}));
  try{
    return await import(blob);
  }finally{
    URL.revokeObjectURL(blob);
  }
}

export async function resolveComponent(name,{channel='stable'}={}){
  const pointer=await readJson(new URL(`channels/${channel}.json`,CDN_ROOT));
  const registryUrl=new URL(pointer.registry,new URL('channels/',CDN_ROOT));
  const registry=await readJson(registryUrl);
  const item=registry.components?.[name];
  if(!item)throw new Error(`component not found: ${name}`);
  return {...item,registry:registry.release,channel};
}

export async function loadComponent(name,options={}){
  const resolved=await resolveComponent(name,options);
  await importVerified(resolved.entry,resolved.integrity);
  return resolved;
}

export const mcpgitComponents={resolve:resolveComponent,load:loadComponent};
globalThis.mcpgitComponents??=mcpgitComponents;
