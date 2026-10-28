export async function api<T=any>(path:string, options?:RequestInit):Promise<T>{
 let r:Response;
 try{r=await fetch('/api'+path,options);}catch{throw Error('ارتباط با backend قطع شد. وضعیت http://127.0.0.1:8000/api/health و لاگ backend را بررسی کنید.');}
 const text=await r.text();let data:any;
 try{data=JSON.parse(text);}catch{throw Error(`پاسخ نامعتبر از سرور (HTTP ${r.status}). لاگ backend و proxy را بررسی کنید.`);}
 if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;
}
export function uploadArchive(file:File,onProgress:(percent:number)=>void):Promise<any>{
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest();xhr.open('POST','/api/projects/upload?'+new URLSearchParams({filename:file.name}));
  xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.timeout=30*60*1000;
  xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.round(e.loaded/e.total*100));};
  xhr.onerror=()=>reject(Error('اتصال آپلود قطع شد. زنده‌بودن backend، فضای دیسک و لاگ backend را بررسی کنید؛ سپس دوباره تلاش کنید.'));
  xhr.ontimeout=()=>reject(Error('مهلت انتقال فایل تمام شد. وضعیت شبکه و لاگ backend را بررسی کنید.'));
  xhr.onabort=()=>reject(Error('آپلود لغو شد.'));
  xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch{reject(Error(`پاسخ نامعتبر آپلود (HTTP ${xhr.status})`));return;}if(xhr.status>=200&&xhr.status<300)resolve(data);else reject(Error(data.detail||`Upload HTTP ${xhr.status}`));};
  xhr.send(file);
 });
}
export function post(path:string,body?:unknown){return api(path,{method:'POST',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});}
export function download(name:string,value:unknown){const u=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download=name;a.click();URL.revokeObjectURL(u);}
