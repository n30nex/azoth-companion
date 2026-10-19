'use strict';
chrome.runtime.onMessage.addListener((message,sender,sendResponse)=>{
  if(sender.id!==chrome.runtime.id || location.origin!=='https://projectazoth.com' || location.pathname!=='/upload')return;
  (async()=>{
    if(message.action==='status') {
      const response=await fetch('/upload/mine',{headers:{Accept:'application/json'},credentials:'same-origin',signal:AbortSignal.timeout(10000)});
      if(response.status===401)return {signed_in:false,uploads:[],reason:'signed_out'};
      if(!response.ok)throw new Error('Could not check your Azoth uploads (HTTP '+response.status+').');
      const data=await response.json();return {signed_in:true,uploads:(data.uploads||[]).slice(0,100)};
    }
    if(message.action==='upload') {
      const job=message.job;
      if(!document.getElementById('u-file'))return {status:401,error:'Sign in to Azoth again.'};
      if(!job||!/^[A-Za-z0-9_-]+\.zip$/.test(job.file)||typeof job.base64!=='string'||job.base64.length>14*1024*1024)throw new Error('Invalid local capture package.');
      const bytes=Uint8Array.from(atob(job.base64),c=>c.charCodeAt(0));
      try {
        const response=await fetch('/upload/zip?name='+encodeURIComponent(job.file),{method:'POST',headers:{'Content-Type':'application/zip','X-Azoth':'1'},credentials:'same-origin',body:bytes,signal:AbortSignal.timeout(45000)});
        const data=await response.json().catch(()=>({}));
        return {status:response.status,error:data.error||''};
      } catch(error) {return {status:0,error:'Upload result is uncertain. Check My uploads before retrying.'};}
    }
    throw new Error('Unknown connector action.');
  })().then(sendResponse).catch(error=>sendResponse({error:error.message}));
  return true;
});
chrome.runtime.sendMessage({action:'sync'}).catch(()=>{});
