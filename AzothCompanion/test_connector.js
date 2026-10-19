'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const folder=path.join(__dirname,'browser-connector');
const stored={},requests=[],created=[],messages=[];
let tabs=[],pending=1,job=null,version='0.1.0',reloads=0;
const event={addListener(){}};
const chrome={
  runtime:{id:'a'.repeat(32),getManifest:()=>({version}),onStartup:event,onInstalled:event,onMessage:event,reload:()=>reloads++,sendMessage:async()=>({ok:true})},
  storage:{local:{get:async()=>({...stored}),set:async value=>Object.assign(stored,value),remove:async key=>delete stored[key]}},
  alarms:{create:async()=>{},onAlarm:event},action:{setBadgeText:async()=>{}},
  tabs:{query:async()=>tabs,create:async value=>{created.push(value);return {id:7,...value};},reload:async()=>{},onUpdated:event,
    sendMessage:async(id,message)=>{messages.push(message);return message.action==='status'?{signed_in:true,uploads:[]}:{status:201};}}
};
const context=vm.createContext({chrome,AbortSignal,fetch:async(url,options)=>{
  const body=JSON.parse(options.body);requests.push({url,body,headers:options.headers});
  let value;
  if(url.endsWith('/pair'))value={token:'scoped-upload-token'};
  else if(url.endsWith('/info'))value={pending};
  else if(url.endsWith('/poll')){value={job:body.signed_in?job:null};if(body.signed_in)job=null;}
  else if(url.endsWith('/result'))value={ok:true};
  else throw Error(url);
  return {ok:true,status:200,json:async()=>value};
}});
vm.runInContext(fs.readFileSync(path.join(folder,'background.js'),'utf8'),context);
(async()=>{
  await vm.runInContext('Promise.all([sync(),sync()])',context);
  assert.equal(created.length,1);assert.equal(created[0].active,false);assert.equal(created[0].url,'https://projectazoth.com/upload');
  assert.deepEqual(requests.find(r=>r.url.endsWith('/pair')).body,{});
  assert.equal(requests[0].headers['X-Azoth-Extension'],'a'.repeat(32));
  pending=0;
  await vm.runInContext('sync()',context);assert.equal(created.length,1);
  tabs=[{id:7,status:'complete',url:'https://projectazoth.com/upload'}];
  job={id:'capture-id',file:'capture-id.zip',base64:'example'};
  await vm.runInContext('sync()',context);
  assert.equal(messages.filter(m=>m.action==='upload').length,1);
  const result=requests.find(r=>r.url.endsWith('/result'));assert.equal(result.body.id,'capture-id');assert.equal(result.body.status,201);
  assert.equal(requests.filter(r=>r.url.endsWith('/poll')).at(-1).body.version,'0.1.0');
  assert.ok(!fs.readFileSync(path.join(folder,'popup.html'),'utf8').includes('id="pin"'));
  version='1.0.0';
  const elements={status:{},connect:{}};
  const popup=vm.createContext({chrome,document:{getElementById:id=>elements[id]}});
  await vm.runInContext(fs.readFileSync(path.join(folder,'popup.js'),'utf8'),popup);
  assert.equal(reloads,0);
  const manifest=JSON.parse(fs.readFileSync(path.join(folder,'manifest.json'),'utf8'));
  assert.ok(manifest.key&&manifest.key.length>100,'Stable public extension key required');
  assert.equal(manifest.permissions.includes('cookies'),false);
  console.log('PASS: no PIN, stable public extension identity, scoped host access, one inactive upload tab for waiting work, and one submission per claimed job.');
})().catch(error=>{console.error(error);process.exitCode=1;});
