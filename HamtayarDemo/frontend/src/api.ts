export async function api<T=any>(path:string, options?:RequestInit):Promise<T>{
 const r=await fetch('/api'+path,options);const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;
}
export function post(path:string,body?:unknown){return api(path,{method:'POST',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});}
export function download(name:string,value:unknown){const u=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download=name;a.click();URL.revokeObjectURL(u);}
