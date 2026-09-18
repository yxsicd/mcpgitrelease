const repoRoot=new URL('./',import.meta.url);
async function readJson(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw new Error(`component registry fetch failed: ${r.status} ${url}`);return r.json()}
export async function resolveComponent(name,{channel='stable'}={}){
  const pointer=await readJson(new URL(`channels/${channel}.json`,repoRoot));
  const registry=await readJson(new URL(pointer.registry,new URL('channels/',repoRoot)));
  const item=registry.components?.[name];
  if(!item)throw new Error(`component not found: ${name}`);
  return {...item,registry:registry.release,channel};
}
export async function loadComponent(name,options={}){
  const resolved=await resolveComponent(name,options);
  await import(resolved.entry);
  return resolved;
}
export const mcpgitComponents={resolve:resolveComponent,load:loadComponent};
globalThis.mcpgitComponents??=mcpgitComponents;
