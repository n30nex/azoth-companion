'use strict';
const $ = id => document.getElementById(id);
let current = null, publicStamp = 0, listingStamp = '', busy = false, review = null, lastPhase = null;
function text(id, value) { $(id).textContent = value; }
function toast(message) { text('toast', message); $('toast').hidden = false; setTimeout(() => $('toast').hidden = true, 7000); }
async function post(route, body = {}) {
  const response = await fetch('/api/' + route, {method:'POST', headers:{'Content-Type':'application/json','X-Azoth-Local':'1'}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The action could not be completed.');
  return data;
}
function el(tag, content, className) { const item = document.createElement(tag); if(content !== undefined) item.textContent = content; if(className) item.className = className; return item; }
function uploadLabel(item){return ({pending:'waiting to upload',sending:'uploading',queued:'uploaded; Azoth is processing',accepted:'accepted',rejected:'rejected','needs-info':'needs information',check_result:'checking upload outcome'})[item.state]||item.state;}
function instructionText(value){return current.plan.mode==='phone'?value.replace(/\bpress F8\b/gi,'tap Done').replace(/\bF8\b/g,'phone'):value.replace(/\bF8\b/g,current.setup.hotkey);}
function allPackets() {
  const map = new Map();
  for(const p of current.catalog.types?.types || []) map.set(p.idx,{idx:p.idx,name:p.name,short:p.name.split('::').pop(),status:p.st,priority:!!p.priority,activity:p.act,what:p.what});
  for(const group of current.catalog.needed?.activities || []) for(const packet of group.packets || []) map.set(packet.idx, packet);
  return [...map.values()].sort((a,b)=>Number(b.priority)-Number(a.priority)||a.idx-b.idx);
}
function missionHistory(id) {
  return (current.sessions||[]).filter(s=>s.marks>0&&(s.targets||[]).includes(id));
}
function attemptSummary(id) {
  if((current.skipped_ids||[]).includes(id))return 'Skipped for now. Choose it again whenever you want to retry.';
  const attempts=missionHistory(id);
  if(!attempts.length)return '';
  const latest=attempts[0],upload=(current.uploads||[]).filter(u=>u.session===latest.name).sort((a,b)=>b.created_ms-a.created_ms)[0];
  const result=upload?.result;
  return `Tried ${attempts.length} time${attempts.length===1?'':'s'} here. Last run: ${new Date(latest.stopped_ms).toLocaleString()} · ${upload?'upload '+upload.state:'saved; upload not tracked here'}${result?.points!=null?' · +'+result.points+' point'+(result.points===1?'':'s'):''}${result?.packets_new!=null?' · '+result.packets_new+' new packets in that capture':''}.`;
}
async function selectPlan(ids) {
  if(current.live.phase==='running')await post('next',{ids,skip:true,expected_ids:current.plan.ids,started_ms:current.live.started_ms,segment:current.live.segment});
  else await post('plan', {ids, mode:$('mode').value});
  await load();
  renderMissions();
  $('mission-picker').open=false;
  $('run-setup').scrollIntoView({behavior:'smooth',block:'start'});
}
function renderMissions() {
  if(!current) return;
  const query = $('search').value.toLowerCase().trim(), category = $('activity').value, filter=$('packet-status').value;
  const matching = allPackets().filter(p => (!category || p.activity === category) && (!filter || (filter==='priority'?p.priority:filter==='untried'?p.status==='wanted'&&!(current.tried_ids||[]).includes(p.idx)&&!missionHistory(p.idx).length:p.status===filter)) && `${p.idx} ${p.short} ${p.what}`.toLowerCase().includes(query));
  $('missions').replaceChildren();
  for(const packet of matching.slice(0, 35)) {
    const item = el('article', undefined, 'mission');
    item.append(el('p', packet.what || packet.short));
    const history=attemptSummary(packet.idx);
    if(history)item.append(el('p',history+(packet.status==='wanted'?' Still wanted by Azoth.':''),'help'));
    const row = el('div', undefined, 'row');
    row.append(el('small', `#${packet.idx} · ${packet.priority?'TOP PRIORITY · ':''}${packet.status.toUpperCase()}`));
    const selected=current.plan.ids.includes(packet.idx);
    const button = el('button', packet.status!=='wanted'?'Already '+packet.status:selected?'Selected':'Choose');
    button.setAttribute('aria-label',`${selected?'Selected':'Choose'} packet ${packet.idx}`);
    button.disabled = selected || current.control?.state==='starting' || busy || packet.status!=='wanted';
    button.onclick = async () => {
      button.disabled=true;try{await selectPlan([packet.idx]);}catch(e){toast(e.message);button.disabled=false;}
    };
    row.append(button); item.append(row); $('missions').append(item);
  }
  if(!matching.length) $('missions').append(el('p','No packets match these filters.','help muted'));
  if(matching.length > 35) $('missions').append(el('p','Narrow the search to see more specific missions.','help muted'));
}
function renderRanks() {
  const name = $('rank-name').value;
  const rank = (current.catalog.ranks?.ranks || []).find(r => r.name === name);
  text('rank-points', rank?.points ?? '—'); text('rank-captures', rank?.captures ?? '—'); text('rank-position', rank?.rank ?? '—');
}
function renderPublic() {
  const publicData = current.catalog;
  text('wanted', `${publicData.stats?.counts?.wanted ?? '—'} wanted`);
  const chosenCategory = $('activity').value;
  $('activity').replaceChildren(el('option','All activities'));
  $('activity').firstElementChild.value = '';
  for(const category of [...new Set(allPackets().map(p => p.activity))].sort()) { const option=el('option',category); option.value=category; $('activity').append(option); }
  $('activity').value = chosenCategory;
  const previous = $('rank-name').value || localStorage.getItem('azoth-discord-name') || '';
  $('rank-name').replaceChildren(el('option','Choose your name')); $('rank-name').firstElementChild.value='';
  for(const rank of publicData.ranks?.ranks || []) { const option=el('option',rank.name); option.value=rank.name; $('rank-name').append(option); }
  $('rank-name').value = previous;
  renderRanks(); renderMissions();
  $('project-counts').replaceChildren(...['solved','captured','wanted','priority'].map(kind=>{
    const box=el('div',undefined,'count');box.append(el('strong',(publicData.stats?.counts?.[kind]??'—').toLocaleString()),el('span',kind==='priority'?'Top priority':kind));return box;
  }));
  text('freshness', publicData.fetched_at ? 'Refreshed ' + new Date(publicData.fetched_at).toLocaleString() : 'Cached mission list');
}
function render() {
  $('pairing').hidden = true; $('workspace').hidden = false;
  if(publicStamp !== current.catalog.fetched_at) { publicStamp = current.catalog.fetched_at; renderPublic(); }
  const ref = current.catalog.stats?.build || 'Unknown';
  $('compat').replaceChildren(el('strong', current.version === ref ? 'Client matches the catalog reference' : 'Client and catalog reference differ'));
  $('compat').append(el('p', `Installed: ${current.version} · Catalog: ${ref}`));
  if(current.version !== ref) $('compat').append(el('p', current.accepted_report + ' The catalog value alone does not establish which versions are accepted.'));
  $('mode').value = current.plan.mode;
  const live = current.live, running = live.phase === 'running', guide = current.guide;
  const setup = current.setup;
  const starting=current.control?.state==='starting', available=current.recorder?.connected&&current.recorder?.ready;
  $('start-run').hidden=running;
  $('start-run').disabled=starting||!available||busy||!current.plan.ids.length;
  text('start-run',starting?'Starting game…':'Start this run');
  $('finish-run').hidden=!running;$('finish-run').disabled=busy;
  $('resume-run').hidden=running||!current.checkpoint?.remaining?.length||JSON.stringify(current.checkpoint.ids)!==JSON.stringify(current.plan.ids);
  $('resume-run').disabled=starting||!available||busy;
  text('recorder-status',current.control?.state==='needs_attention'?current.control.error:starting?'Opening New World for your character…':!available?'Open the Azoth Capture desktop icon first.':running?'Recording · follow the action below':'Ready · leave Steam signed in');
  const connector=current.connector||{}, connected=connector.signed_in&&Date.now()-connector.seen_ms<90000;
  text('upload-status',current.preferences.auto_upload?(connected?'Automatic upload ready.':'Automatic uploads enabled. Connect the Chrome extension and sign in to Azoth.'):'Automatic uploads are off. Review and send each saved capture when ready.');
  $('auto-upload').checked=current.preferences.auto_upload;
  if(document.activeElement!==$('character-name'))$('character-name').value=current.preferences.character;
  if(document.activeElement!==$('world-name'))$('world-name').value=current.preferences.world;
  $('auto-resume').disabled=!current.recovery_ready;
  text('calibration-status',current.calibration.error||(current.calibration.state==='selecting'?'Use the selection window on the PC; press Enter to save or C to cancel.':current.recovery_ready?'Both screens are saved. Automatic return can be enabled.':'Set up both screens to enable automatic return.'));
  text('phone-connection',current.connection.phone_url?`Open ${current.connection.phone_url} and enter PIN ${current.connection.pin}.`:'Phone access is unavailable on the current network. A single Private home-network connection is required.');
  $('auto-resume').checked=current.recovery_enabled;
  const recovery=current.recovery||{};
  const recoveryText={waiting_for_menu:'Waiting for the verified your character character screen…',entering_world:'your character selected · entering your world…',in_world:'your character is in the world.',saving_and_restarting:'Saving this capture, then reopening the game for your character…',complete:'The selected checklist is complete.'};
  text('recovery-status',recovery.error||recoveryText[recovery.state]||'Your character · up to three automatic resumes');
  if(lastPhase !== live.phase) { lastPhase = live.phase; renderMissions(); }
  $('setup-name').value = running ? live.name : setup.name;
  text('setup-activity', setup.activities.join(' + ') || 'Use the selected mission’s activity');
  $('setup-targets').replaceChildren(...setup.targets.map(p => {const item=el('li', `#${p.id} · ${p.name}`),history=attemptSummary(p.id);if(history)item.append(el('p',history,'help'));return item;}));
  text('setup-hint', `${guide.length} planned marks · ${current.plan.mode === 'phone' ? 'Tap the phone after each action' : 'Press ' + setup.hotkey + ' after each action'}. The dashboard sets the session name, activity and packet targets for you.`);
  $('mode').disabled = running||starting; $('pair-plan').disabled = running||starting;
  const kicks=live.connection_evidence?.eac_kicks||[], disconnected=!!live.disconnected;
  $('connection-notice').hidden=!kicks.length;
  if(kicks.length) text('connection-notice',`${live.name}: ${kicks.length} disconnect${kicks.length===1?'':'s'} recorded. ${!running?'Recording ended; see the saved capture and upload result below.':!disconnected?'Play resumed and this recording is continuing.':recovery.state==='needs_attention'?'Automatic return needs attention. Check the session status.':current.recovery_enabled?'Returning to your character; the same recording will continue.':'Automatic return is paused. End session & send, or enable it in Session settings.'}`);
  const paired = current.plan.ids.length === 2 && current.plan.ids.includes(5078) && current.plan.ids.includes(5118);
  const sheath = current.plan.ids.length === 1 && current.plan.ids[0] === 3899;
  const chosenPackets=allPackets().filter(p=>current.plan.ids.includes(p.idx));
  const weaponSwap=current.plan.ids.length===1&&current.plan.ids[0]===3902;
  const fullGather=current.plan.ids.length===1&&current.plan.ids[0]===5195;
  text('mission-meta',`${running?'Current capture':'Next capture'} · ${current.plan.ids.map(id=>'#'+id).join(' + ')}`);
  text('mission-title',!current.plan.ids.length?'All suggested targets tried.':setup.title||(fullGather?'Gather from 3 resource nodes.':weaponSwap?'Swap weapons 5 times.':current.plan.ids.includes(2818)?'Record three knockbacks.':sheath?'Draw and put away your weapon.':paired?'Approach and leave five resource nodes.':chosenPackets.map(p=>p.what||p.short).join(' ')));
  const tried=current.plan.ids.some(id=>missionHistory(id).length),stillWanted=chosenPackets.some(p=>p.status==='wanted');
  text('mission-reason',`${stillWanted?'Still wanted by Azoth.':'Check Azoth’s current need before repeating.'} ${current.plan.ids.some(id=>(current.skipped_ids||[]).includes(id))?'You skipped this target before; you can try it now or skip again.':tried?'You have tried this target before; previous results are under Past runs.':'You haven’t tried this target here.'}`);
  text('where',!current.plan.ids.length?'Choose a different wanted capture below. Previously attempted targets will only repeat if you choose them.':setup.where||(fullGather?'Find three nearby trees, rocks or herbs your tools and skill can gather. Fully collect each resource, then press F8 once. This run needs three completed gathers.':weaponSwap?'Stand anywhere safe. Equip two different weapons, one in each weapon slot. Use your weapon-swap key; check Settings → Keybinds if needed.':current.plan.ids.includes(2818)?'Find a strong enemy whose heavy attack visibly staggers or knocks you back.':sheath ? 'Stand somewhere quiet with one weapon equipped and visibly drawn. Pause about five seconds between actions.' : paired ? 'Find trees, rocks or herbs nearby. Walk close enough for the gather prompt to appear, then away until it disappears.' : chosenPackets.map(p=>p.how_to_capture?.[0]||p.what).join(' ')));
  $('before-start').hidden=running;
  text('where',instructionText($('where').textContent));
  text('marking-summary',current.plan.mode==='phone'?'Follow each action and tap Done when it happens.':`Follow each action and press ${setup.hotkey} when it happens.`);
  $('live-guide').hidden=!running;
  const lastReport=current.reports[0];
  const lastUpload=lastReport?(current.uploads||[]).find(u=>u.ledger_sha256===lastReport.ledger_sha256):null;
  $('last-result').hidden=!lastReport||running;
  if(lastReport){
    text('last-result',lastUpload?`Latest saved run: ${uploadLabel(lastUpload)}${lastUpload.result?.points!=null?' · +'+lastUpload.result.points+' point'+(lastUpload.result.points===1?'':'s'):''}${lastUpload.result?.packets_new!=null?' · '+lastUpload.result.packets_new+' new packets':''}.${lastUpload.notes_correction?' Submitted marker notes need correction; the corrected copy is saved on this PC.':''}`:'Latest saved run: not submitted — marker descriptions need review.');
    if(!lastUpload){const reviewButton=el('button','Review marks');reviewButton.style.marginTop='10px';reviewButton.onclick=()=>openReview(lastReport.id).catch(e=>toast(e.message));$('last-result').append(el('br'),reviewButton);}
  }
  const index = running ? live.index : 0;
  $('next-run').hidden=!running;
  $('next-run').disabled=busy||index<guide.length||disconnected||!current.next_targets?.length;
  $('skip-task').hidden=!current.plan.ids.length;
  $('skip-task').disabled=busy||starting||!current.next_targets?.length;
  text('skip-task',current.plan.ids.length>1?'Skip these packets':'Skip this packet');
  $('skip-hint').hidden=!current.plan.ids.length;
  $('session-note').hidden=!running;
  text('session-note',`${live.completed_tasks||0} task${live.completed_tasks===1?'':'s'} completed in this recording. Next packet keeps the game and recorder running; End session & send uploads the whole recording.`);
  text('live-pill', running ? 'Recording' : 'Ready to collect');
  const entries=(live.connection_evidence?.events||[]).filter(e=>e.kind==='entered_world');
  const worldStart=entries.at(-1)?.t_ms;
  const seconds=running?Math.max(0,Math.floor((Date.now()-(worldStart||live.started_ms))/1000)):0;
  text('clock', running ? `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')} ${worldStart?'in world':'loading'} · ${Math.round((live.ledger_bytes||0)/1024)} KB recorded` : 'Your character');
  text('step-number', guide.length ? `ACTION ${Math.min(index+1,guide.length)} OF ${guide.length}` : 'CHOOSE A MISSION');
  $('progress-bar').style.width = `${guide.length ? Math.min(100,index/guide.length*100) : 0}%`;
  text('next-action', instructionText(guide[index]?.text || (guide.length ? 'The checklist is complete.' : 'Choose a mission to see its instructions.')));
  text('next-detail', !running ? 'Click Start this run above.' : index >= guide.length ? current.next_targets?.length?'Choose Next packet to keep collecting in this game, or End session & send when you are done.':'All suggested targets have been tried. End session & send this recording.' : current.plan.mode === 'phone' ? 'Do the action, then tap the button.' : `Press ${setup.hotkey} once after the action. Wait a few seconds before the next one.`);
  const sameTargets = current.plan.ids.every(id=>live.targets.includes(id));
  $('mark').hidden = current.plan.mode !== 'phone';
  $('mark').disabled = !running || index >= guide.length || !sameTargets || disconnected || busy;
  $('f8-tip').hidden = !running || current.plan.mode !== 'f8' || index >= guide.length || disconnected || !sameTargets;
  $('f8-tip').querySelector('kbd').textContent = setup.hotkey;
  if(running && !sameTargets) {
    text('live-pill', 'Recorder targets do not match');
    text('next-detail', 'Stop the session and select the targets shown in Prepare before starting a new recording.');
  }
  if(running && disconnected) {
    text('live-pill', 'Disconnect recorded');
    const returning=current.recovery_enabled&&recovery.state!=='needs_attention';
    text('next-action', returning?'Returning to your character…':'Collection paused after a disconnect.');
    text('next-detail', recovery.error||(returning?'The same recording and checklist will continue after world entry. Wait to mark another action.':'Click End session & send, or enable automatic resume to continue this recording.'));
  }
  if(running&&!worldStart&&!disconnected){text('live-pill','Loading');text('next-action',current.recovery_enabled?'Returning to your character…':'Select your character in New World.');text('next-detail',recovery.error||'Wait for world entry; loading may take a minute or more. The first action will appear here.');$('mark').disabled=true;$('f8-tip').hidden=true;}
  text('markers', running ? `${Math.min(index,guide.length)} of ${guide.length} actions marked` : '');
  $('checklist').replaceChildren(...guide.map((step,i)=>el('li',instructionText(step.text),i<index?'done':i===index?'current':'')));
  text('watcher', current.watcher.state || 'Watching new exports');
  const stamp = JSON.stringify([current.sessions,current.reports,current.uploads,current.plan,current.tried_ids,current.skipped_ids]);
  if(stamp !== listingStamp) { listingStamp=stamp; renderExports(); renderMissions(); }
}
function renderExports() {
  $('reports').replaceChildren();
  if(!current.reports.length) $('reports').append(el('p','No prepared ZIPs yet. New finished sessions are checked automatically.','muted help'));
  const reportTimes = new Map(current.reports.map(r => [r.id,r.reviewed_ms || r.created_ms]));
  const replaced = new Set(current.reports.filter(r => r.supersedes && reportTimes.get(r.id) > reportTimes.get(r.supersedes)).map(r => r.supersedes));
  for(const report of current.reports) {
    if(replaced.has(report.id)) continue;
    const card=el('div',undefined,'report'); card.append(el('div',report.session,'title'));
    card.append(el('p',`${report.status} · ${report.checks.records.toLocaleString()} records · ${report.checks.marks} marks · 0 decoding errors`,'muted'));
    const upload=(current.uploads||[]).find(item=>item.id===report.id||item.ledger_sha256===report.ledger_sha256);
    if(upload){card.append(el('p',`Upload: ${uploadLabel(upload)}${upload.result?.points!=null?' · +'+upload.result.points+' points':''}`,'badge'));if(upload.error||upload.result?.reason)card.append(el('p',upload.error||upload.result.reason,'help'));}
    if(upload?.state==='accepted'&&upload.result?.packets_new!=null){
      card.append(el('p',`${upload.result.packets_total??'—'} packets reported by Azoth · ${upload.result.packets_new} new · ${upload.result.first_captures??'—'} first captures.`,'help'));
      if(upload.result.packets_new===0)card.append(el('p','No new packet types credited for this run. Check the Wanted list before choosing your next target.','help'));
    }
    if(upload&&upload.id!==report.id)card.append(el('p','An earlier version of these notes was already sent. This review is saved locally.','help'));
    if(upload?.notes_correction)card.append(el('p','The submitted marker notes need correction. A corrected copy is saved locally; contact the project to replace the original notes.','help'));
    if(report.auto_labels) card.append(el('p','Action labels added from the agreed F8 sequence.','muted'));
    if(report.connection_evidence?.eac_kicks?.length) card.append(el('p','Connection evidence: interrupted by Easy Anti-Cheat.','badge'));
    if(report.warnings.length) { const list=el('ul'); for(const warning of report.warnings) list.append(el('li',warning)); card.append(list); }
    const actions=el('div',undefined,'review-actions');
    if(!upload){const send=el('button','Send to Azoth');send.onclick=async()=>{send.disabled=true;try{await post('submit',{id:report.id});await load();toast('Queued for the Chrome connector.');}catch(e){toast(e.message);send.disabled=false;}};actions.append(send);}
    const button=el('button','Review marker labels'); button.onclick=()=>openReview(report.id).catch(e=>toast(e.message)); actions.append(button);
    const link=el('a','Download the two-file ZIP','button-link'); link.href='/download/'+encodeURIComponent(report.id); link.download=report.archive; actions.append(link); card.append(actions); $('reports').append(card);
  }
  $('sessions').replaceChildren();
  for(const session of current.sessions) {
    const card=el('div',undefined,'report'); card.append(el('div',session.name,'title')); card.append(el('small',`${session.marks} recorded marks`));
    const button=el('button','Check & prepare ZIP','full'); button.onclick=async()=>{button.disabled=true;button.textContent='Checking capture…';try{await post('prepare',{id:session.id});await load();toast('ZIP prepared. Review any notes before sending.');}catch(e){toast(e.message);}finally{button.disabled=false;button.textContent='Check & prepare ZIP';}}; card.append(button); $('sessions').append(card);
  }
}
async function openReview(id) {
  review = await post('review', {id});
  text('review-title', review.journal.session); text('review-error','');
  $('review-marks').replaceChildren(...review.journal.steps.map((mark,i)=>{
    const row=el('div',undefined,'review-mark');
    const label=el('label', `Marker ${i+1} · ${new Date(mark.t_ms).toLocaleTimeString()}`); label.htmlFor='review-text-'+i;
    const input=el('textarea');input.id=label.htmlFor;input.value=mark.text;input.required=true;input.maxLength=500;
    const uncertain=el('label',undefined,'uncertain');
    const check=el('input');check.type='checkbox';check.checked=/unconfirmed|unidentified|unknown|uncertain/i.test(mark.text);
    uncertain.append(check,document.createTextNode('I’m unsure what this mark meant'));
    row.append(label,input,uncertain);return row;
  }));
  $('review-dialog').showModal();
}
async function load() {
  const response=await fetch('/api/state?catalog='+encodeURIComponent(current?.catalog?.fetched_at||''));
  if(response.status===401){$('workspace').hidden=true;$('pairing').hidden=false;return;}
  if(!response.ok)throw new Error('The PC is not responding.');
  const updated=await response.json();updated.catalog=updated.catalog||current?.catalog||{};current=updated;render();
}
$('login-form').onsubmit=async e=>{e.preventDefault();try{await post('login',{pin:$('pin').value});$('pin').value='';text('login-error','');await load();}catch(error){text('login-error',error.message);}};
$('activity').onchange=renderMissions;$('search').oninput=renderMissions;
$('packet-status').onchange=renderMissions;
$('pair-plan').onclick=()=>selectPlan([5078,5118]).catch(e=>toast(e.message));
$('mode').onchange=()=>current&&selectPlan(current.plan.ids).catch(e=>toast(e.message));
$('rank-name').onchange=()=>{localStorage.setItem('azoth-discord-name',$('rank-name').value);renderRanks();};
$('mark').onclick=async()=>{if(busy||!current)return;busy=true;$('mark').disabled=true;try{await post('mark',{started_ms:current.live.started_ms,index:current.live.index});await load();}catch(e){toast(e.message);}finally{busy=false;if(current)render();}};
$('refresh').onclick=async()=>{const button=$('refresh');button.disabled=true;try{await post('refresh');await load();toast('Mission list refreshed.');}catch(e){toast(e.message);}finally{button.disabled=false;}};
$('copy-name').onclick=async()=>{
  try {
    if(navigator.clipboard?.writeText) await navigator.clipboard.writeText($('setup-name').value);
    else { $('setup-name').focus();$('setup-name').select();if(!document.execCommand('copy'))throw new Error('Select the session name and copy it using your device’s menu.'); }
    toast('Session name copied. Paste it into Azoth Capture on the PC.');
  } catch(e) { toast(e.message); }
};
$('review-cancel').onclick=()=>$('review-dialog').close();
async function startRun(resume=false){if(busy)return;busy=true;render();try{await post('start',{request_id:'run-'+Date.now()+'-'+Math.random().toString(36).slice(2),resume});await load();$('live-guide').scrollIntoView({behavior:'smooth'});}catch(e){toast(e.message);}finally{busy=false;render();}}
$('start-run').onclick=()=>startRun();$('resume-run').onclick=()=>startRun(true);
async function nextPacket(skip=false){if(busy||!current)return;busy=true;render();try{const result=await post('next',{skip,expected_ids:current.plan.ids,started_ms:current.live.started_ms,segment:current.live.segment});await load();$('run-setup').scrollIntoView({behavior:'smooth',block:'start'});toast((skip?'Skipped. ':'')+(result.continued_recording?'Next target ready. Your game and recording continue.':'Next target ready. Start when you’re ready.'));}catch(e){toast(e.message);}finally{busy=false;render();}}
$('next-run').onclick=()=>nextPacket();$('skip-task').onclick=()=>nextPacket(true);
$('finish-run').onclick=async()=>{if(busy)return;busy=true;render();try{await post('stop',{started_ms:current.live.started_ms});await load();toast('Recording stopped. Checking and preparing the upload…');}catch(e){toast(e.message);}finally{busy=false;render();}};
$('open-overlay').onclick=()=>post('overlay').catch(e=>toast(e.message));
$('auto-resume').onchange=async()=>{try{await post('recovery-mode',{enabled:$('auto-resume').checked});await load();}catch(e){toast(e.message);}};
$('auto-upload').onchange=async()=>{try{await post('preferences',{auto_upload:$('auto-upload').checked});await load();}catch(e){toast(e.message);}};
for(const [id,key] of [['character-name','character'],['world-name','world']])$(id).onchange=()=>post('preferences',{[key]:$(id).value}).then(load).catch(e=>toast(e.message));
for(const screen of ['character','disconnect'])$('calibrate-'+screen).onclick=()=>post('calibrate',{screen}).then(load).catch(e=>toast(e.message));
$('review-form').onsubmit=async event=>{
  event.preventDefault();if(!review)return;
  $('review-save').disabled=true;text('review-error','');
  try {
    const steps=[...$('review-marks').children].map(row=>({text:row.querySelector('textarea').value,unsure:row.querySelector('input').checked}));
    await post('review-save',{id:review.id,revision:review.revision,steps});
    $('review-dialog').close();await load();toast('Reviewed ZIP ready. Original recordings and timestamps are preserved.');
  } catch(e) { text('review-error',e.message); } finally { $('review-save').disabled=false; }
};
load().catch(e=>text('login-error',e.message));
setInterval(()=>load().catch(()=>{if(current)text('live-pill','PC connection interrupted');}),2500);
