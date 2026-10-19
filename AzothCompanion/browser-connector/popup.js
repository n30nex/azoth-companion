const status=document.getElementById('status');
async function connect(){
  status.textContent='Connecting automatically...';
  await chrome.runtime.sendMessage({action:'sync'});
  const result=await chrome.storage.local.get('status');
  status.textContent=result.status||'Waiting for the local companion. Open Azoth Capture.';
}
document.getElementById('connect').onclick=()=>connect().catch(error=>status.textContent=error.message);
connect().catch(error=>status.textContent=error.message);
