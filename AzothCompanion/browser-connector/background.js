'use strict';
const BASE='http://127.0.0.1:8877';
let busy=false;
async function local(path,body,token) {
  const response=await fetch(BASE+'/connector/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-Azoth-Connector':token||'','X-Azoth-Extension':chrome.runtime.id},body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
  const data=await response.json();if(!response.ok)throw new Error(data.error||'Local connection failed');return data;
}
async function sync() {
  if(busy)return;busy=true;
  try {
    const paired=await local('pair',{});
    const token=paired.token;
    if(typeof token!=='string'||token.length<16)throw new Error('The local companion did not provide a connection.');
    await chrome.storage.local.set({token});
    const info=await local('info',{},token);
    const tabs=await chrome.tabs.query({url:'https://projectazoth.com/upload*'});
    const tab=tabs.find(tab=>tab.status==='complete')||tabs[0];
    if(!tab){
      await local('poll',{signed_in:false,uploads:[],reason:'tab_closed',version:chrome.runtime.getManifest().version},token);
      if(info.pending){await chrome.tabs.create({url:'https://projectazoth.com/upload',active:false});await chrome.storage.local.set({status:'Opening Azoth to send the saved capture…'});}
      else await chrome.storage.local.set({status:'Connected automatically to this PC. The upload page opens when a capture is waiting.'});
      await chrome.action.setBadgeText({text:info.pending?'…':''});return;
    }
    if(tab.status!=='complete')return;
    const account=await chrome.tabs.sendMessage(tab.id,{action:'status'});
    if(account.error)throw new Error(account.error);
    const result=await local('poll',{...account,version:chrome.runtime.getManifest().version},token);
    await chrome.action.setBadgeText({text:account.signed_in?'':'Login'});
    await chrome.storage.local.set({status:account.signed_in?'Connected automatically. Your Azoth account is signed in.':'Sign in on the Azoth upload page. No local PIN is needed.'});
    if(result.job) {
      let sent;
      try {sent=await chrome.tabs.sendMessage(tab.id,{action:'upload',job:result.job});}
      catch(error){sent={status:0,error:'Upload result is uncertain. Check My uploads before retrying.'};}
      await local('result',{id:result.job.id,status:sent?.status||0,error:sent?.error||''},token);
    }
  } catch(error) {
    await chrome.storage.local.set({status:error.message});
    await chrome.action.setBadgeText({text:'!'});
  } finally {busy=false;}
}
async function enable(){
  await chrome.alarms.create('azoth-sync',{periodInMinutes:0.5});
  const saved=await chrome.storage.local.get('refreshUploadPage');
  if(saved.refreshUploadPage){
    await chrome.storage.local.remove('refreshUploadPage');
    for(const tab of await chrome.tabs.query({url:'https://projectazoth.com/upload*'}))await chrome.tabs.reload(tab.id);
  }
  await sync();
}
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='azoth-sync')sync();});
chrome.runtime.onStartup.addListener(enable);
chrome.runtime.onInstalled.addListener(async()=>{await chrome.storage.local.set({refreshUploadPage:true});await enable();});
chrome.tabs.onUpdated.addListener((id,change,tab)=>{if(change.status==='complete'&&tab.url?.startsWith('https://projectazoth.com/upload'))sync();});
chrome.runtime.onMessage.addListener((message,sender,sendResponse)=>{
  if(sender.id!==chrome.runtime.id)return;
  if(message.action==='pair' && !sender.tab) {
    sync().then(()=>sendResponse({ok:true}));return true;
  }
  if(message.action==='sync'){sync().then(()=>sendResponse({ok:true}));return true;}
});
