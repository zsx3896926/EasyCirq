/* HDS integration adapter, Apache-2.0. Protocol reviewed against easyeda-viewer
 * a60b22d098d25850d1f28427e51dd2619b008ed9, docs/easyeda-viewer-api.md.
 * No upstream renderer code is copied. */
(function(root){
 'use strict';
 function create(frame, viewerUrl, host){
  const url=new URL(viewerUrl);
  if(!['http:','https:'].includes(url.protocol)||!['localhost','127.0.0.1','[::1]'].includes(url.hostname)||url.username||url.password)throw Error('Loopback viewer required');
  let ready=false;
  const api={onEvent:null,
   send(cmd,payload={}){
    if(!['load','open','fit','select','theme','chrome','lang'].includes(cmd))throw Error('Unsupported viewer command');
    if(!ready)throw Error('Viewer not ready');
    if(cmd==='select'&&(!Array.isArray(payload.designators)||payload.designators.length>1000||payload.designators.some(x=>typeof x!=='string'||x.length>100)))throw Error('Invalid designators');
    if(cmd==='load'&&(!Array.isArray(payload.files)||payload.files.length===0||payload.files.length>1000||payload.files.some(f=>typeof f.name!=='string'||typeof f.dataBase64!=='string')))throw Error('Invalid project files');
    const safe = cmd==='chrome' ? {...payload,chrome:{...(payload.chrome||{}),annotations:false}} : payload;
    frame.contentWindow.postMessage({...safe,source:'easyeda-viewer',cmd},url.origin);
   },
   exportAnnotations(projectId,revision){
    if(host.location.origin!==url.origin)throw Error('Annotations require same origin');
    const a=frame.contentWindow.easyedaViewer;
    if(!a||a.version!=='1.2.0')throw Error('Unsupported annotation API');
    const snapshot=a.exportAnnotations();
    if(snapshot.projectId!==projectId||snapshot.revision!==revision)throw Error('Annotation project/revision mismatch');
    return JSON.parse(JSON.stringify(snapshot));
   },
   destroy(){host.removeEventListener('message',receive);ready=false;}
  };
  function receive(e){
   if(e.source!==frame.contentWindow||e.origin!==url.origin)return;
   const m=e.data;
   if(!m||m.source!=='easyeda-viewer'||!['ready','load-ok','open-result','select-result','error'].includes(m.event))return;
   if(m.event==='ready'){
    ready=true;
    frame.contentWindow.postMessage({source:'easyeda-viewer',cmd:'chrome',chrome:{annotations:false}},url.origin);
   }
   if(api.onEvent)api.onEvent(m);
  }
  host.addEventListener('message',receive);
  url.searchParams.set('annotations','0');frame.src=url.toString();
  return api;
 }
 if(typeof module==='object'&&module.exports)module.exports={create};else root.HdsViewer={create};
})(typeof window==='object'?window:globalThis);
