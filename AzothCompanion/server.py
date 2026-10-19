"""LAN companion for guided capture, verified menu return and saved uploads."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import zipfile
from collections import Counter
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT.parent
STATE = Path(os.environ.get('AZOTH_COMPANION_DATA', str(Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'AzothCompanion')))
ENGINE = Path(os.environ.get('AZOTH_ENGINE_DIR',str(OUTPUTS / 'AzothCapture' / 'Aeternum-World' / 'Tools' / 'nw_capture')))
APP_DATA = Path(os.environ.get('AZOTH_CAPTURE_DATA', str(STATE / 'recorder')))
READY = STATE / 'prepared'
LOCK = threading.RLock()
VERSION_CACHE = {}
PAIR_IDS = {5078, 5118}
CONFIG = {}
GAME_LOG = Path(os.environ.get('LOCALAPPDATA', '')) / 'AGS' / 'New World' / 'Game.log'
GAME_EVENT_CACHE = {'signature': None, 'events': []}
RECORDER_LOCK = threading.Lock()
CATALOG_CACHE = {}
RECOVERED_FILES = set()


def read_json(path, default=None):
    path=Path(path)
    for candidate in (path,path.with_name(path.name+'.bak')):
        try:
            value=json.loads(candidate.read_text(encoding='utf-8-sig'))
            if candidate!=path:
                RECOVERED_FILES.add(str(path))
            return value
        except (OSError, ValueError):
            pass
    return {} if default is None else default


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    def write_durable(target, body):
        handle,temp=tempfile.mkstemp(prefix=target.name+'.',suffix='.tmp',dir=target.parent)
        try:
            with os.fdopen(handle,'wb') as stream:
                stream.write(body);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,target)
        finally:
            Path(temp).unlink(missing_ok=True)
    try:
        previous=path.read_bytes()
        json.loads(previous.decode('utf-8-sig'))
    except (OSError,ValueError):
        previous=None
    if previous is not None:
        write_durable(path.with_name(path.name+'.bak'),previous)
    write_durable(path,(json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode('utf-8'))


def app_settings():
    return read_json(APP_DATA / 'settings.json')


def preferences():
    return {'auto_upload':False,'character':'','world':'',**read_json(STATE/'preferences.json')}


def recovery_ready():
    folder=STATE/'menu-templates'
    return all((folder/(name+'.png')).is_file() for name in
               ('character-heading','character-card','play','connection-error','expected-eac-kick','kick-okay'))


def recovery_enabled():
    return recovery_ready() and read_json(STATE/'recovery-settings.json').get('enabled',False)


def start_calibration(screen):
    if screen not in ('character','disconnect'):
        raise ValueError('Choose the character screen or disconnect dialog.')
    previous=read_json(STATE/'calibration.json')
    if previous.get('state')=='selecting' and time.time()*1000-previous.get('started_ms',0)<180000:
        raise ValueError('Finish or cancel the selection window already open on the PC.')
    save_json(STATE/'calibration.json',{'state':'selecting','screen':screen,'started_ms':int(time.time()*1000)})
    subprocess.Popen([sys.executable,str(ROOT/'game_ui.py'),'calibrate','--screen',screen],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def game_version():
    configured=app_settings().get('exe_path')
    if not configured:
        return 'Not configured'
    path = Path(configured)
    try:
        key = (str(path), path.stat().st_mtime_ns)
        if key not in VERSION_CACHE:
            quoted = str(path).replace("'", "''")
            cmd = f"(Get-Item -LiteralPath '{quoted}').VersionInfo.FileVersion"
            result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', cmd],
                                    capture_output=True, text=True, timeout=15,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            version = result.stdout.strip()
            VERSION_CACHE[key] = version if re.fullmatch(r'\d+(?:\.\d+){3}', version) else 'Unknown'
        return VERSION_CACHE[key]
    except (OSError, subprocess.SubprocessError):
        return 'Unknown'


def catalog():
    path=STATE/'catalog.json'
    try:
        stamp=(str(path),path.stat().st_mtime_ns,path.stat().st_size)
    except OSError:
        stamp=(str(path),None)
    if CATALOG_CACHE.get('stamp')!=stamp:
        CATALOG_CACHE.update(stamp=stamp,value=read_json(path))
    return CATALOG_CACHE['value']


def packets():
    return {p['idx']: p for group in catalog().get('needed', {}).get('activities', [])
            for p in group.get('packets', [])}


def refresh_catalog():
    previous = catalog()
    if time.time() * 1000 - previous.get('fetched_at', 0) < 60000:
        return
    fresh = dict(previous)
    etags=dict(previous.get('etags',{}))
    for kind in ('needed', 'stats', 'ranks', 'types'):
        request = urllib.request.Request('https://projectazoth.com/api/' + kind,
                                        headers={'User-Agent': 'AzothCompanion/0.1.0','If-None-Match':etags.get(kind,'')})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                fresh[kind] = json.load(response)
                etags[kind]=response.headers.get('ETag','')
        except urllib.error.HTTPError as error:
            if error.code!=304 or kind not in previous:
                raise
    fresh['etags']=etags
    fresh['fetched_at'] = int(time.time() * 1000)
    with LOCK:
        save_json(STATE / 'catalog.json', fresh)
        if not (STATE/'plan.json').exists():
            save_json(STATE/'plan.json',{'ids':recommended_targets(),'mode':'f8'})


def draft():
    return read_json(APP_DATA / 'draft.json')


def parse_game_events(text):
    """Retain only timestamps and connection events, never raw game log lines."""
    events = set()
    for line in text.splitlines():
        if 'Report Error:' in line and (re.search(r'BannedUntilEpochMS:\s*[1-9]',line) or re.search(r'Reason:\s*[^\s]*(?:banned|suspended)[^\s]*',line,re.I)):
            kind = 'account_warning'
        elif 'Report Error: Reason: Errors::kicked_easyanticheat' in line:
            kind = 'eac_kick'
        elif 'Update state ' in line and 'to new state InGame' in line:
            kind = 'entered_world'
        elif 'Update state ' in line and 'to new state Disconnected' in line:
            kind = 'disconnected'
        else:
            continue
        stamp = re.match(r'^<([0-9-]+ [0-9:.]+)>', line)
        if not stamp:
            continue
        try:
            # This game's log uses UTC; the journal separately stores the local offset.
            moment = datetime.strptime(stamp[1], '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
            events.add((int(moment.timestamp() * 1000), kind))
        except ValueError:
            continue
    return [{'t_ms': stamp, 'kind': kind} for stamp, kind in sorted(events)]


def game_evidence(started_ms, stopped_ms=None):
    empty = {'events': [], 'eac_kicks': [], 'continuity': 'Not established from logs'}
    if not started_ms:
        return empty
    end = stopped_ms or int(time.time() * 1000)
    with LOCK:
        stored_path = STATE / f'connection-{int(started_ms)}.json'
        stored = read_json(stored_path, empty)
        try:
            stat = GAME_LOG.stat()
            key = (str(GAME_LOG), stat.st_size, stat.st_mtime_ns)
            if GAME_EVENT_CACHE['signature'] != key:
                with GAME_LOG.open('rb') as stream:
                    # ponytail: bounded tail; retain observed events per session across rollover.
                    stream.seek(max(0, stat.st_size - 4 * 1024 * 1024))
                    events = parse_game_events(stream.read().decode('utf-8', errors='replace'))
                GAME_EVENT_CACHE.update(signature=key, events=events)
        except OSError:
            events = []
        else:
            events = GAME_EVENT_CACHE['events']
        corrected_kicks = {item['t_ms'] for item in events if item['kind']=='eac_kick'}
        joined = {(item['t_ms'], item['kind']) for item in stored.get('events', []) + events
                  if not (item['kind']=='account_warning' and item['t_ms'] in corrected_kicks)
                  if started_ms <= item['t_ms'] <= end}
        result = {'events': [{'t_ms': t, 'kind': k} for t, k in sorted(joined)]}
        result['eac_kicks'] = [e['t_ms'] for e in result['events'] if e['kind'] == 'eac_kick']
        result['continuity'] = 'Interrupted by Easy Anti-Cheat' if result['eac_kicks'] else 'Not established from logs'
        # An absence of recorded kicks is not a claim of uninterrupted or EAC-approved operation.
        if result != stored:
            save_json(stored_path, result)
        return result


def interruptions(evidence):
    entries=[e['t_ms'] for e in evidence.get('events',[]) if e['kind']=='entered_world']
    return [(kick,next((t for t in entries if t>kick),float('inf'))) for kick in evidence.get('eac_kicks',[])]


def active_disconnect(evidence):
    return any(end==float('inf') for _,end in interruptions(evidence))


def ledger_bytes(session):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',str(session or '')):
        return 0
    try:
        # Open the file: Windows directory entries can retain a stale zero size while a writer holds it.
        with (ENGINE/'captures'/session/'dtls'/'ledger.bin').open('rb') as stream:
            stream.seek(0,2)
            return stream.tell()
    except OSError:
        return 0


def plan():
    return read_json(STATE / 'plan.json', {'ids': [], 'mode': 'f8'})


def instructions(ids):
    if set(ids) <= {3173,3175} and ids:
        result=[]
        for n in range(1,3):
            if 3173 in ids:
                result.append({'text':f'Bait {n}: open the bait box and press F8 once while it is open. Choose a different bait for this round.', 'label':f'Opened bait box, round {n}','target':3173})
            if 3175 in ids:
                result.append({'text':f'Bait {n}: apply your bait, close the bait box, then press F8 once.', 'label':f'Closed bait box after applying bait, round {n}','target':3175})
        return result
    simple={
        5755:[('Open your inventory. Press F8 once when your bag contents appear.','Opened inventory'),('Walk to a settlement storage shed and open it. Press F8 once when the stored items appear.','Opened settlement storage')],
        663:[(f'Use food or a potion from your quick bar, then press F8 after it is actually used. Use {n} of 3; wait for its cooldown if needed.',f'Used quick-bar item {n}') for n in range(1,4)],
        3379:[(f'Gather {n} of 3: hold the interact key through a full gather, then press F8 when it finishes.',f'Completed uninterrupted gathering {n}') for n in range(1,4)]}
    if any(idx in simple for idx in ids):
        return [step for idx in ids for step in ([{'text':text,'label':label,'target':idx} for text,label in simple[idx]] if idx in simple else instructions([idx]))]
    if 5195 in ids:
        result = []
        for idx in ids:
            if idx == 5195:
                result += [{'text': f'Gather {n} of 3: fully collect from a different tree, rock or herb. Press F8 once when you receive the resource.',
                            'label': f'Finished gathering resource node {n}', 'target': 5195} for n in range(1, 4)]
            else:
                result += instructions([idx])
        return result
    if 3902 in ids:
        result = []
        for idx in ids:
            if idx == 3902:
                result += [{'text': f'Swap {n} of 5: switch to your other equipped weapon. Press F8 once when the weapon changes.',
                            'label': f'Observed weapon swap {n}', 'target': 3902} for n in range(1, 6)]
            else:
                result += instructions([idx])
        return result
    if 2818 in ids or 491 in ids:
        result = []
        for idx in ids:
            if idx == 2818:
                result += [{'text': f'Knockback {n} of 3: let an enemy heavy attack stagger or knock you back. Press F8 immediately when it happens.',
                            'label': f'Observed stagger or knockback {n}', 'target': idx} for n in range(1, 4)]
            elif idx == 491:
                result += [{'text': 'On the respawn screen, try an unavailable or cooldown respawn point. Press F8 only if the game actually shows a respawn error. If the option cannot be clicked, skip this target.',
                            'label': 'Observed a respawn request error', 'target': idx}]
            else:
                result += instructions([idx])
        return result
    if set(ids) == {3899}:
        return [{'text': f'Cycle {n}: put your drawn weapon away using your sheathe/draw key.',
                 'label': f'Cycle {n}: weapon sheathed', 'target': 3899}
                if side == 0 else
                {'text': f'Cycle {n}: draw your weapon again using the same key.',
                 'label': f'Cycle {n}: weapon drawn', 'target': 3899}
                for n in range(1, 4) for side in range(2)]
    if set(ids) == PAIR_IDS:
        return [{'text': f'Node {n}: walk closer until the [E] gather prompt appears.',
                 'label': f'Resource node {n}: gather prompt appeared', 'target': 5078}
                if side == 0 else
                {'text': f'Node {n}: walk away until the [E] gather prompt disappears.',
                 'label': f'Resource node {n}: gather prompt disappeared', 'target': 5118}
                for n in range(1, 6) for side in range(2)]
    result = []
    for idx in ids:
        packet = packets().get(idx, {})
        for text in packet.get('how_to_capture', []):
            result.append({'text': text, 'label': text, 'target': idx})
    return result


def mission_segments(run, current):
    return run.get('segments') or [{'ids':run.get('ids',current.get('targets',[])),
        'guide':run.get('guide',[]),'mark_start':0,'phone_start':0,'started_ms':current.get('started_ms',0)}]


def session_targets(journal):
    run=read_json(STATE/f"run-{journal.get('started_ms')}.json")
    return list(dict.fromkeys(idx for segment in mission_segments(run,journal) for idx in segment['ids']))


def attempted_targets():
    tried={int(idx) for idx in read_json(STATE/'mission-history.json')}
    for path in session_files().values():
        journal=read_json(path)
        if journal.get('steps') or phone_notes(journal.get('started_ms')):
            tried.update(session_targets(journal))
    return tried


def recommended_targets(exclude=()):
    tried=attempted_targets()|set(exclude)
    wanted=packets()
    # Short, concrete tasks with guides; unavailable or attempted targets are skipped.
    for group in ((5755,),(3173,3175),(663,),(3379,),(5195,),(3902,),(3899,),(5078,5118),(2818,),(491,)):
        available=[idx for idx in group if idx in wanted and wanted[idx].get('status','wanted')=='wanted' and idx not in tried]
        if available:
            return available
    # Continue with Azoth's published guides after the short starter list.
    activities={'Inventory & gear':0,'Movement':1,'Gathering':2,'Chat':3,'Combat':4,'Crafting':5,'Fishing':6,'Camping':7}
    remaining=[p for p in wanted.values() if p['idx'] not in tried and p.get('status','wanted')=='wanted'
               and p.get('how_to_capture') and p.get('activity')!='Developer-only']
    remaining.sort(key=lambda p:(not p.get('priority'),p.get('confidence')!='likely',
        activities.get(p.get('activity'),8),len(p['how_to_capture']),p['idx']))
    if remaining:
        return [remaining[0]['idx']]
    return []


def remember_attempt(current, run, skipped=False):
    segment=mission_segments(run,current)[-1]
    count=len(current.get('steps',[]))-segment['mark_start']+len(phone_notes(current.get('started_ms')))-segment['phone_start']
    if count<=0 and not skipped:
        return
    history=read_json(STATE/'mission-history.json')
    for idx in segment['ids']:
        history[str(idx)]={'session_ms':current.get('started_ms'),'at_ms':int(time.time()*1000),'skipped':skipped}
    save_json(STATE/'mission-history.json',history)


def next_packet(body):
    if not RECORDER_LOCK.acquire(blocking=False):
        raise ValueError('A recorder command is already in progress.')
    try:
        current,chosen=draft(),plan()
        if body.get('expected_ids')!=chosen['ids']:
            raise ValueError('The next target is already selected. Refresh the page.')
        run=read_json(STATE/f"run-{current.get('started_ms')}.json")
        segments=mission_segments(run,current)
        active=segments[-1]
        running=current.get('phase')=='running'
        if running:
            if not run or body.get('started_ms')!=current.get('started_ms') or body.get('segment')!=len(segments)-1:
                raise ValueError('The recording or task changed. Refresh the page.')
            if recorder_status().get('capture')!='running':
                raise ValueError('The recorder has ended. Finish & send this recording first.')
            marks=phone_notes(current['started_ms'])[active['phone_start']:] if chosen['mode']=='phone' else current.get('steps',[])[active['mark_start']:]
            gaps=interruptions(game_evidence(current['started_ms']))
            completed=sum(not any(begin<=mark['t_ms']<end for begin,end in gaps) for mark in marks)
            if completed<len(active['guide']) and not body.get('skip'):
                raise ValueError('Finish the displayed actions, or choose Skip this packet.')
        ids=body.get('ids') if 'ids' in body else recommended_targets(chosen['ids'])
        if not isinstance(ids,list) or len(ids)>4 or len(ids)!=len(set(ids)) or any(type(idx) is not int or idx not in packets() for idx in ids):
            raise ValueError('Choose listed wanted targets.')
        if running and not ids:
            raise ValueError('No untried guided targets remain. Finish & send this recording, then choose another target.')
        if ids and not instructions(ids):
            raise ValueError('That target has no capture guide.')
        if running:
            remember_attempt(current,run,skipped=bool(body.get('skip')))
            active['ended_ms']=int(time.time()*1000)
            active['skipped']=bool(body.get('skip'))
            segments.append({'ids':ids,'guide':instructions(ids),'mark_start':len(current.get('steps',[])),
                             'phone_start':len(phone_notes(current['started_ms'])),'started_ms':int(time.time()*1000)})
            run['segments']=segments
            save_json(STATE/f"run-{current['started_ms']}.json",run)
        elif body.get('skip'):
            history=read_json(STATE/'mission-history.json')
            for idx in chosen['ids']:
                history[str(idx)]={'session_ms':None,'at_ms':int(time.time()*1000),'skipped':True}
            save_json(STATE/'mission-history.json',history)
        save_json(STATE/'plan.json',{**chosen,'ids':ids,'finished_session':chosen.get('finished_session') if running else current.get('started_ms')})
        if not running:
            save_json(STATE/'control.json',{'state':'ready','next_targets':ids})
        return {'ok':True,'continued_recording':running,'targets':ids}
    finally:
        RECORDER_LOCK.release()


def run_setup(chosen, current):
    ids = chosen['ids']
    base = 'weapon-sheath' if set(ids) == {3899} else 'gathering-proximity' if set(ids) == PAIR_IDS else 'packet-' + '-'.join(map(str, ids))
    names = {p.parent.parent.name.casefold() for p in session_files().values()}
    names.add(str(current.get('name', '')).casefold())
    output = Path(app_settings().get('output_dir', str(OUTPUTS / 'Captures')))
    if output.is_dir():
        names.update(p.name.casefold() for p in output.iterdir() if p.is_dir())
    raw = ENGINE / 'captures'
    if raw.is_dir():
        names.update(p.name.casefold() for p in raw.iterdir() if p.is_dir())
    number = 1
    while f'{base}-{number:02d}'.casefold() in names:
        number += 1
    known = packets()
    selected = [known.get(idx, {}) for idx in ids]
    activities = sorted({p['activity'] for p in selected if p.get('activity')})
    descriptions={5755:('Open your bag and town storage.','Go to any settlement storage shed. You will mark opening your bag, then opening the storage—two F8 marks.'),663:('Use 3 quick-bar items.','Put food or potions on your quick bar. Stand somewhere safe and wait for cooldowns between uses.'),3379:('Hold through 3 full gathers.','Use three nearby resource nodes. Hold the interact key through each gather; mark only when it finishes.')}
    title,where=descriptions.get(ids[0],('','')) if len(ids)==1 else ('','')
    if ids and set(ids)<={3173,3175}:
        title,where='Open and close the bait box.','Equip a fishing pole and have two kinds of bait available. Follow the open/apply/close actions; no fish catch is required.'
    return {'name': f'{base}-{number:02d}', 'activities': activities,'title':title,'where':where,
            'targets': [{'id': idx, 'name': p.get('short', 'Mission ' + str(idx))} for idx, p in zip(ids, selected)],
            'marks': len(instructions(ids)), 'hotkey': app_settings().get('hotkey', 'F8')}


def phone_notes(started_ms):
    return read_json(STATE / f'phone-{int(started_ms or 0)}.json', [])


def session_files():
    root = Path(app_settings().get('output_dir', str(OUTPUTS / 'Captures')))
    return {hashlib.sha256(str(p.resolve()).encode()).hexdigest()[:16]: p
            for p in root.glob('*/send/steps.json') if p.is_file()}


def signature(path):
    try:
        return tuple((p.stat().st_size, p.stat().st_mtime_ns)
                     for p in (path, path.with_name('ledger.bin')))
    except OSError:
        return None


def labels_for(source, notes, interrupted_at=None, gaps=None):
    result = copy.deepcopy(source)
    marks = result.get('steps', [])
    warnings = []
    defaults = [bool(re.fullmatch(r'Step\s+\d+', str(s.get('text', '')))) for s in marks]
    targets = set(source.get('targets', []))
    saved_plan = read_json(STATE / f"run-{int(source.get('started_ms', 0))}.json")
    segments=mission_segments(saved_plan,source)
    if saved_plan.get('segments') and set(saved_plan.get('ids',[]))==targets:
        result['targets']=list(dict.fromkeys(idx for segment in segments for idx in segment['ids']))
        if len({packets().get(idx,{}).get('activity') for idx in result['targets']})>1:
            result['activity']='Other'
    if saved_plan and set(saved_plan.get('ids', [])) == targets and saved_plan.get('mode') == 'f8' and marks and all(defaults) and all(s.get('via') == 'hotkey' for s in marks) and not notes:
        for position,segment in enumerate(segments):
            guide,index=segment['guide'],0
            start=segment['mark_start']
            end=segments[position+1]['mark_start'] if position+1<len(segments) else len(marks)
            if not 0<=start<=end<=len(marks):
                raise ValueError('The saved task boundaries need review.')
            for mark in marks[start:end]:
                in_gap=any(begin<=mark['t_ms']<finish for begin,finish in gaps) if gaps is not None else interrupted_at is not None and mark['t_ms']>=interrupted_at
                if index >= len(guide) or in_gap:
                    mark['text'] = 'Action unconfirmed: extra marker or marker after the observed disconnect.'
                    mark.pop('target', None)
                    warnings.append('An extra or post-disconnect marker needs review.')
                else:
                    mark.update(text=guide[index]['label'], target=guide[index]['target'])
                    index+=1
        result['steps'] = marks
        return result, list(dict.fromkeys(warnings)), True
    paired = (targets in (PAIR_IDS, {3899}) and marks and all(defaults)
              and all(s.get('via') == 'hotkey' for s in marks) and not notes)
    if paired:
        # ponytail: infer labels only for the agreed alternating two-action task.
        for index, step in enumerate(marks):
            if interrupted_at is not None and step['t_ms'] >= interrupted_at:
                step['text'] = 'F8 marker after an observed disconnect; action unconfirmed. Review before submitting.'
                step.pop('target', None)
                continue
            entering = index % 2 == 0
            if targets == {3899}:
                step['text'] = f'Cycle {index // 2 + 1}: weapon ' + ('sheathed' if entering else 'drawn')
                step['target'] = 3899
            else:
                step['text'] = f'Resource node {index // 2 + 1}: gather prompt ' + ('appeared' if entering else 'disappeared')
                step['target'] = 5078 if entering else 5118
        action_count = sum(interrupted_at is None or step['t_ms'] < interrupted_at for step in marks)
        if action_count < len(marks):
            warnings.append('Markers after the observed disconnect were left unconfirmed instead of assigned gameplay labels.')
        if action_count % 2:
            warnings.append('The final action has no matching second action; review the last step.')
    elif any(defaults):
        warnings.append('Some F8 marks still need descriptions. Automatic F8 labels cover gathering approach/leave and weapon sheathe/draw.')
    result['steps'] = sorted(marks + copy.deepcopy(notes), key=lambda s: s['t_ms'])
    return result, warnings, bool(paired)


def validate_capture(steps, ledger):
    if steps.get('schema') != 1 or not isinstance(steps.get('steps'), list):
        raise ValueError('Unrecognized journal format.')
    start, stop = steps.get('started_ms', 0), steps.get('stopped_ms', 0)
    if not isinstance(start, int) or not isinstance(stop, int) or stop <= start:
        raise ValueError('The journal has no completed session interval.')
    if not steps['steps']:
        raise ValueError('There are no activity marks to describe the capture.')
    times = [s.get('t_ms') for s in steps['steps']]
    if any(not isinstance(t, int) or t < start or t > stop for t in times) or times != sorted(times):
        raise ValueError('Journal timestamps are outside the session or out of order.')
    if not ledger:
        raise ValueError('The capture is empty.')
    sys.path.insert(0, str(ENGINE)) if str(ENGINE) not in sys.path else None
    from decode_dtls_ledger import iter_ledger, decode_record
    counts, builds, total_bytes, errors = Counter(), set(), 0, 0
    first, last = None, None
    STATE.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=STATE, suffix='.bin')
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(ledger)
        for idx, direction, stamp, pointer, payload in iter_ledger(Path(temp_name)):
            if direction not in (0, 1):
                raise ValueError('Invalid capture direction.')
            total_bytes += 28 + len(payload)
            first = stamp if first is None else min(first, stamp)
            last = stamp if last is None else max(last, stamp)
            decoded = decode_record(idx, direction, stamp, pointer, payload)
            errors += bool(decoded.error)
            counts['in' if direction == 0 else 'out'] += 1
            for message in decoded.messages:
                for match in re.findall(rb'NewWorld\.(\d+\.\d+\.\d+\.\d+)', message.payload):
                    builds.add(match.decode('ascii'))
    finally:
        Path(temp_name).unlink(missing_ok=True)
    if total_bytes != len(ledger):
        raise ValueError('The ledger is truncated or contains unparsed trailing bytes.')
    if errors or not counts['in'] or not counts['out']:
        raise ValueError(f'Capture validation failed: {errors} decode errors; both directions are required.')
    if first < start - 30000 or last > stop + 30000:
        raise ValueError('Capture times do not match this journal. Check that the files belong together.')
    return {'records': sum(counts.values()), 'in': counts['in'], 'out': counts['out'],
            'decode_errors': errors, 'bytes': len(ledger), 'first_ms': first, 'last_ms': last,
            'builds': sorted(builds), 'marks': len(times),
            'packet_types_verified': False}


def prepare(path, destination=None):
    path, destination = Path(path), Path(READY if destination is None else destination)
    before = signature(path)
    original = read_json(path)
    active = draft()
    if active.get('phase') == 'running' and active.get('started_ms') == original.get('started_ms'):
        raise ValueError('This session is still running. Stop it in Azoth Capture first.')
    ledger = path.with_name('ledger.bin').read_bytes()
    if before is None or signature(path) != before:
        raise ValueError('The recorder is still saving these files. Try again in a moment.')
    evidence = game_evidence(original.get('started_ms'), original.get('stopped_ms'))
    cutoff = min(evidence['eac_kicks']) if evidence['eac_kicks'] else None
    annotated, warnings, paired = labels_for(original, phone_notes(original.get('started_ms')), cutoff, interruptions(evidence))
    if cutoff is not None:
        warnings.append('The game log records an Easy Anti-Cheat kick during this session. Saved data is preserved; uninterrupted capture is not established.')
    return package_capture(annotated, ledger, warnings, evidence, paired, destination)


def package_capture(annotated, ledger, warnings, evidence, paired=False, destination=None, reviewed=False, replaces=None):
    destination = Path(READY if destination is None else destination)
    checks = validate_capture(annotated, ledger)
    if any(s['t_ms'] > checks['last_ms'] for s in annotated['steps']):
        warnings.append('One or more marks fall after the final network record; review the ending around a disconnect.')
    body = (json.dumps(annotated, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    digest = hashlib.sha256(ledger + body).hexdigest()
    slug = re.sub(r'[^A-Za-z0-9_-]', '-', str(annotated.get('session', 'capture')))[:60].strip('-') or 'capture'
    stem = f'{slug}-{digest[:12]}'
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / (stem + '.zip')
    temporary = destination / (stem + '.zip.part')
    if not archive.exists():
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
            zipped.writestr('ledger.bin', ledger)
            zipped.writestr('steps.json', body)
    with zipfile.ZipFile(temporary if temporary.exists() else archive) as zipped:
        if zipped.namelist() != ['ledger.bin', 'steps.json'] or zipped.testzip():
            raise ValueError('ZIP verification failed.')
        if zipped.read('ledger.bin') != ledger or zipped.read('steps.json') != body:
            raise ValueError('ZIP contents differ from the validated files.')
    if temporary.exists():
        with temporary.open('r+b') as saved:
            saved.flush();os.fsync(saved.fileno())
        temporary.replace(archive)
    previous = read_json(destination / (stem + '.json'))
    if not reviewed and previous.get('reviewed'):
        return previous  # Re-checking an unchanged export must not erase its review.
    report = {'id': stem, 'session': annotated.get('session'), 'archive': archive.name,
              'status': ('Reviewed with notes' if warnings else 'Reviewed') if reviewed else 'Review notes' if warnings else 'Prepared', 'checks': checks,
              'warnings': warnings, 'auto_labels': paired, 'created_ms': previous.get('created_ms', int(time.time() * 1000)),
              'reviewed': reviewed, 'reviewed_ms': int(time.time() * 1000) if reviewed else None,
              'supersedes': replaces if replaces != stem else previous.get('supersedes'),
              'connection_evidence': evidence,
              'ledger_sha256': hashlib.sha256(ledger).hexdigest(),
              'note': 'Local validation checks record framing, decoding and timestamps. It does not prove wanted packet types or server acceptance.'}
    save_json(destination / (stem + '.json'), report)
    return report


def available_reports():
    return sorted([read_json(p) for p in READY.glob('*.json')],
                  key=lambda r: r.get('reviewed_ms') or r.get('created_ms', 0), reverse=True)


def review_source(key):
    report = next((r for r in available_reports() if r.get('id') == key), None)
    if not report or report.get('archive') != key + '.zip':
        raise ValueError('That prepared capture is unavailable.')
    with zipfile.ZipFile(READY / report['archive']) as archive:
        if sorted(archive.namelist()) != ['ledger.bin', 'steps.json']:
            raise ValueError('Unexpected files in the prepared ZIP.')
        ledger, body = archive.read('ledger.bin'), archive.read('steps.json')
    if hashlib.sha256(ledger).hexdigest() != report.get('ledger_sha256'):
        raise ValueError('The prepared recording has changed. Check the original files.')
    return report, json.loads(body), ledger, hashlib.sha256(ledger + body).hexdigest()


def save_review(body):
    report, journal, ledger, revision = review_source(body.get('id'))
    if body.get('revision') != revision:
        raise ValueError('This capture changed. Open its review again.')
    edits = body.get('steps')
    if not isinstance(edits, list) or len(edits) != len(journal['steps']):
        raise ValueError('Review every existing marker. Markers and times cannot be added or removed here.')
    uncertain = 0
    for mark, edit in zip(journal['steps'], edits):
        if not isinstance(edit, dict) or set(edit) != {'text', 'unsure'}:
            raise ValueError('Only marker descriptions and uncertainty can be edited.')
        text = edit['text']
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500 or type(edit['unsure']) is not bool:
            raise ValueError('Each marker needs a description of 1–500 characters.')
        mark['text'] = text.strip()
        if edit['unsure']:
            uncertain += 1
            if not re.search(r'(?i)unconfirmed|unidentified|unknown|uncertain', mark['text']):
                mark['text'] = 'Action unconfirmed: ' + mark['text']
            mark.pop('target', None)
    warnings = [f'{uncertain} marker(s) have uncertain actions; these are not assigned to packet targets.'] if uncertain else []
    evidence = report.get('connection_evidence', {})
    if evidence.get('eac_kicks'):
        warnings.append('The game log records an Easy Anti-Cheat kick during this session.')
    return package_capture(journal, ledger, warnings, evidence, reviewed=True, replaces=report['id'])


def status(include_catalog=True):
    current, chosen, public = draft(), plan(), catalog()
    evidence = game_evidence(current.get('started_ms'), current.get('stopped_ms'))
    notes = phone_notes(current.get('started_ms'))
    marks = current.get('steps', [])
    saved_plan = read_json(STATE / f"run-{int(current.get('started_ms', 0))}.json")
    segments=mission_segments(saved_plan,current)
    active=segments[-1]
    running=current.get('phase')=='running'
    guide = active['guide'] or instructions(chosen['ids']) if running else instructions(chosen['ids'])
    if running:
        marks=marks[active['mark_start']:]
        notes=notes[active['phone_start']:]
    gaps=interruptions(evidence)
    index = len(notes) if chosen.get('mode') == 'phone' else sum(not any(begin<=m['t_ms']<end for begin,end in gaps) for m in marks)
    listings = []
    for key, path in session_files().items():
        data = read_json(path)
        listings.append({'id': key, 'name': data.get('session', path.parent.parent.name),
                         'targets': session_targets(data),
                         'marks': len(data.get('steps', [])) + len(phone_notes(data.get('started_ms'))),
                         'stopped_ms': data.get('stopped_ms', 0)})
    recorder = recorder_status()
    return {'version': game_version(), **({'catalog':public} if include_catalog else {}), 'plan': chosen, 'guide': guide,
            'recorder': recorder, 'control': read_json(STATE / 'control.json'),
            'uploads': read_json(STATE / 'uploads.json', []), 'connector': read_json(STATE / 'connector-status.json'),
            'checkpoint': read_json(STATE / 'checkpoint.json'),
            'recovery': read_json(STATE / 'recovery.json'),
            'recovery_enabled': recovery_enabled(),'recovery_ready':recovery_ready(),'preferences':preferences(),
            'calibration':read_json(STATE/'calibration.json'),
            'connection':{'phone_url':f"http://{CONFIG.get('host')}:{CONFIG.get('port')}" if CONFIG.get('host')!='127.0.0.1' else '',
                          'pin':CONFIG.get('pin','')},
            'tried_ids':sorted(attempted_targets()), 'next_targets':recommended_targets(chosen['ids']),
            'skipped_ids':sorted(int(idx) for idx,item in read_json(STATE/'mission-history.json').items() if item.get('skipped')),
            'setup': run_setup(chosen, current),
            'live': {'phase': current.get('phase', 'idle'), 'name': current.get('name', ''),
                     'started_ms': current.get('started_ms'), 'marks': len(marks), 'phone_marks': len(notes),
                     'targets': active['ids'] if running else current.get('targets', []), 'index': index,
                     'segment':len(segments)-1,'completed_tasks':sum(not segment.get('skipped') for segment in segments[:-1]),
                     'connection_evidence': evidence,
                     'disconnected':active_disconnect(evidence), 'ledger_bytes':ledger_bytes(current.get('name')),
                     'last_mark': (notes if chosen.get('mode') == 'phone' else marks)[-1:]},
            'sessions': sorted(listings, key=lambda item: item['stopped_ms'], reverse=True),
            'reports': available_reports(), 'watcher': read_json(STATE / 'watcher.json'),
            'accepted_report': 'The catalog reference alone does not establish which client versions Azoth accepts.',
            'reference_note': 'The catalog build is a reference value, not a verified allowlist of accepted client versions.'}


def recorder_call(route, body=None, timeout=4):
    bridge = read_json(APP_DATA / 'dashboard-bridge.json')
    url = urllib.parse.urlsplit(bridge.get('url', ''))
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port:
        raise ValueError('Open the updated Azoth Capture desktop icon first.')
    request = urllib.request.Request(bridge['url'] + route,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization':'Bearer ' + bridge['token'], 'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(json.loads(error.read()).get('error', 'The recorder rejected the command.')) from error


def recorder_status():
    try:
        result = recorder_call('/state', timeout=1)
        return {'connected':True, 'ready':result['ready'], 'capture':result['capture'],
                'hotkey_error':result['hotkey_error'], 'phase':result['state']['phase']}
    except (OSError, ValueError, KeyError):
        return {'connected':False, 'ready':False}


def start_run(body, recovery_attempt=0):
    control = read_json(STATE / 'control.json')
    request_id = body.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch('[a-zA-Z0-9_-]{8,80}', request_id):
        raise ValueError('Refresh the dashboard before starting.')
    if control.get('request_id') == request_id:
        return control
    if not RECORDER_LOCK.acquire(blocking=False):
        raise ValueError('A recorder command is already in progress.')
    try:
        if draft().get('phase') == 'running':
            raise ValueError('Finish the current recording first.')
        chosen = plan()
        if any(idx not in packets() for idx in chosen['ids']):
            raise ValueError('One selected packet is no longer listed as wanted. Refresh and choose a wanted target.')
        setup = run_setup(chosen, draft())
        guide = instructions(chosen['ids'])
        if not guide:
            raise ValueError('This target has no capture instructions yet.')
        if body.get('resume'):
            previous = read_json(STATE / 'checkpoint.json')
            if previous.get('ids') != chosen['ids'] or not previous.get('remaining'):
                raise ValueError('There is no matching unfinished checklist to resume.')
            guide = previous['remaining']
        pending = {'state':'starting','name':setup['name'],'request_id':request_id}
        save_json(STATE / 'control.json',pending)
    except Exception:
        RECORDER_LOCK.release()
        raise
    def launch():
        try:
            activities = setup['activities']
            result = recorder_call('/start', {'name':setup['name'],'activity':activities[0] if len(activities)==1 else 'Other','targets':chosen['ids']}, timeout=60)
            save_json(STATE / f"run-{result['started_ms']}.json", {**chosen,'guide':guide,'auto_upload':preferences()['auto_upload'],'auto_recover':recovery_enabled(),'attempt':recovery_attempt})
            save_json(STATE / 'control.json',{**pending,'state':'recording','started_ms':result['started_ms']})
            if recovery_enabled():
                threading.Thread(target=login_character,args=(result['started_ms'],),daemon=True).start()
            else:
                save_json(STATE/'recovery.json',{'state':'manual','session_ms':result['started_ms']})
        except Exception as error:
            message=str(error)
            if 'Close New World normally' in message:
                message='New World is already open without an active recording. It was left open. Use Next packet while recording to keep collecting; a fresh recording needs the collector to launch the game.'
            save_json(STATE / 'control.json',{**pending,'state':'needs_attention','error':message})
        finally:
            RECORDER_LOCK.release()
    threading.Thread(target=launch,daemon=True).start()
    return pending


def stop_run(body):
    if not RECORDER_LOCK.acquire(blocking=False):
        raise ValueError('A recorder command is already in progress.')
    try:
        current = draft()
        if current.get('phase') != 'running' or current.get('started_ms') != body.get('started_ms'):
            raise ValueError('That recording is not running.')
        saved = read_json(STATE / f"run-{current['started_ms']}.json")
        active=mission_segments(saved,current)[-1]
        evidence = game_evidence(current['started_ms'])
        gaps = interruptions(evidence)
        marks = phone_notes(current['started_ms'])[active['phone_start']:] if saved.get('mode') == 'phone' else current.get('steps', [])[active['mark_start']:]
        completed = sum(not any(begin<=mark['t_ms']<end for begin,end in gaps) for mark in marks)
        save_json(STATE / 'checkpoint.json', {'ids':active['ids'],'remaining':active['guide'][completed:]})
        result = recorder_call('/stop', {'started_ms':current['started_ms']}, timeout=15)
        save_json(STATE / 'control.json', {'state':'stopped','name':current.get('name'),'export_error':result.get('export_error')})
        remember_attempt(current,saved)
        save_json(STATE/'plan.json',{'ids':recommended_targets(active['ids']),'mode':saved.get('mode','f8'),'finished_session':current['started_ms']})
        return result
    finally:
        RECORDER_LOCK.release()


def start_overlay():
    running = read_json(STATE / 'overlay.json')
    # The overlay writes a heartbeat. Avoid taking focus or duplicating it.
    if time.time() - running.get('seen_at',0) < 10:
        return
    subprocess.Popen(['powershell.exe','-NoProfile','-File',str(ROOT/'Overlay.ps1')],
                     env={**os.environ,'AZOTH_COMPANION_DATA':str(STATE)},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def game_ui(action, **options):
    args=[sys.executable,str(ROOT/'game_ui.py'),action]
    for name,value in options.items():
        args += ['--'+name,str(value)]
    result=subprocess.run(args,capture_output=True,text=True,timeout=195,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    data=json.loads(result.stdout)
    if result.returncode:
        raise ValueError(data.get('error','Could not operate the verified game menu.'))
    return data


def login_character(started, resume=False, owner=None):
    save_json(STATE/'recovery.json',{'session_ms':started,'state':'waiting_for_menu','character':preferences()['character'],'world':preferences()['world']})
    try:
        identity={'pid':owner['pid'],'created':owner['created']} if owner else {}
        result=game_ui('enter',session=started,resume=int(resume),**identity)
        save_json(STATE/'game-owner.json',{'session_ms':started,'pid':result['pid'],'created':result.get('created')})
        save_json(STATE/'recovery.json',{'session_ms':started,**result})
        if result.get('state')=='in_world':
            start_overlay()
    except Exception as error:
        if draft().get('phase')!='running' or draft().get('started_ms')!=started:
            save_json(STATE/'recovery.json',{'session_ms':started,'state':'stopped'})
        else:
            save_json(STATE/'recovery.json',{'session_ms':started,'state':'needs_attention','error':str(error)})


def recover_watch():
    handled=set()
    while True:
        try:
            current=draft()
            started=current.get('started_ms')
            run=read_json(STATE/f'run-{started}.json')
            enabled=recovery_enabled()
            if current.get('phase')=='running' and run and not RECORDER_LOCK.locked() and recorder_status().get('capture') in ('done','error'):
                stop_run({'started_ms':started})
                save_json(STATE/'recovery.json',{'state':'stopped','message':'Recorder ended; available data was saved.'})
                continue
            if current.get('phase')=='running' and run.get('auto_recover') and enabled:
                evidence=game_evidence(started)
                login=read_json(STATE/'recovery.json')
                if any(e['kind']=='account_warning' for e in evidence['events']):
                    handled.add(('account',started))
                    save_json(STATE/'recovery-settings.json',{'enabled':False})
                    save_json(STATE/'recovery.json',{'state':'needs_attention','error':'An account warning was logged. Automatic resume is stopped.'})
                elif active_disconnect(evidence) and ('kick',max(evidence['eac_kicks'])) not in handled:
                    owner=read_json(STATE/'game-owner.json')
                    if owner.get('session_ms')!=started or not owner.get('pid') or not owner.get('created'):
                        raise ValueError('The game process for this recording could not be verified. Finish it manually.')
                    handled.add(('kick',max(evidence['eac_kicks'])))
                    if run.get('attempt',0)>=3:
                        stop_run({'started_ms':started})
                        save_json(STATE/'recovery.json',{'state':'needs_attention','error':'Three automatic resumes have been used. Your remaining steps are saved.'})
                    else:
                        run['attempt']=run.get('attempt',0)+1
                        save_json(STATE/f'run-{started}.json',run)
                        save_json(STATE/'checkpoint.json',{'ids':run['ids'],'guide':run['guide'],'session_ms':started})
                        login_character(started,resume=True,owner=owner)
                elif not active_disconnect(evidence) and any(e['kind']=='entered_world' for e in evidence['events']) and login.get('state')=='entering_world':
                    save_json(STATE/'recovery.json',{**login,'state':'in_world'})
                    start_overlay()
        except Exception as error:
            save_json(STATE/'recovery.json',{'state':'needs_attention','error':str(error)})
        time.sleep(2)


def catalog_watch():
    while True:
        try:
            refresh_catalog()
        except Exception:
            pass  # Keep the last successful snapshot and its visible timestamp.
        time.sleep(900)


def queue_upload(report, reviewed=False, explicit=False):
    _, journal, _, _ = review_source(report['id'])
    run = read_json(STATE / f"run-{journal['started_ms']}.json")
    if not explicit and (not run.get('auto_upload') or not preferences()['auto_upload']):
        return  # Existing captures are never silently submitted again.
    if not reviewed and (any(re.search(r'(?i)unconfirmed|unidentified|unknown|uncertain|^Step\s+\d+$', s['text']) for s in journal['steps']) or any(s['t_ms'] > report['checks']['last_ms'] for s in journal['steps'])):
        return
    items = read_json(STATE/'uploads.json', [])
    existing=next((item for item in items if item['ledger_sha256']==report['ledger_sha256'] and item['state'] not in ('rejected','needs-info')),None)
    if existing:
        if explicit and existing['state']=='pending':
            existing['automatic']=False
            save_json(STATE/'uploads.json',items)
        if reviewed and existing['state']=='pending':
            existing.update(id=report['id'],file=report['archive'],session=report['session'])
            save_json(STATE/'uploads.json',items)
        return
    items.append({'id':report['id'],'file':report['archive'],'session':report['session'],
                  'ledger_sha256':report['ledger_sha256'],'state':'pending','automatic':not explicit,'created_ms':int(time.time()*1000)})
    save_json(STATE/'uploads.json',items)


def watch():
    seen = {}  # Catch exports saved while the dashboard was closed; uploads remain deduplicated.
    pending = {}
    save_json(STATE / 'watcher.json', {'state': 'Watching new exports', 'started_ms': int(time.time() * 1000)})
    while True:
        try:
            current = draft()
            game_evidence(current.get('started_ms'), current.get('stopped_ms'))
            for path in session_files().values():
                key, stamp = str(path), signature(path)
                if stamp is None or seen.get(key) == stamp:
                    continue
                previous, since = pending.get(key, (None, time.monotonic()))
                if previous != stamp:
                    pending[key] = (stamp, time.monotonic())
                    continue
                if time.monotonic() - since < 3:
                    continue
                data, current = read_json(path), draft()
                if current.get('phase') == 'running' and current.get('started_ms') == data.get('started_ms'):
                    continue
                seen[key] = stamp
                try:
                    with LOCK:
                        report = prepare(path)
                        queue_upload(report)
                        run=read_json(STATE/f"run-{data.get('started_ms')}.json")
                        active=mission_segments(run,data)[-1]
                        if run.get('auto_upload') and draft().get('phase')!='running' and plan()['ids']==active['ids'] and plan().get('finished_session')!=data.get('started_ms'):
                            remember_attempt(data,run)
                            save_json(STATE/'plan.json',{'ids':recommended_targets(active['ids']),'mode':run.get('mode','f8'),'finished_session':data.get('started_ms')})
                    save_json(STATE / 'watcher.json', {'state': 'Prepared ' + report['session'], 'updated_ms': int(time.time()*1000)})
                except Exception as error:
                    save_json(STATE / 'watcher.json', {'state': 'Needs attention', 'error': str(error), 'updated_ms': int(time.time()*1000)})
        except Exception as error:
            save_json(STATE / 'watcher.json', {'state': 'Needs attention', 'error': str(error)})
        time.sleep(2)


class LANServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def verify_request(self, request, client_address):
        if request is not None:
            request.settimeout(10)
        return (self.server_address[0] == '127.0.0.1' and client_address[0] == '127.0.0.1') or ipaddress.ip_address(client_address[0]) in ipaddress.ip_network(CONFIG['subnet'])


class Handler(BaseHTTPRequestHandler):
    attempts = {}

    def log_message(self, *args):
        pass  # No request URLs, cookies, or capture payloads in logs.

    def respond(self, value, code=200, kind='application/json', cookie=None):
        body = json.dumps(value).encode() if kind == 'application/json' else value
        self.send_response(code)
        for name, val in {'Content-Type': kind, 'Content-Length': str(len(body)), 'Cache-Control': 'no-store',
                          'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                          'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"}.items():
            self.send_header(name, val)
        if cookie:
            self.send_header('Set-Cookie', cookie)
        origin = self.headers.get('Origin', '')
        if self.path.startswith('/connector/') and origin == 'chrome-extension://' + CONFIG.get('connector_extension_id',''):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Azoth-Connector, X-Azoth-Extension')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
        try:
            self.end_headers()
            self.wfile.write(body)
        except ConnectionError:
            pass

    def do_OPTIONS(self):
        if self.path.startswith('/connector/') and self.client_address[0] == '127.0.0.1':
            return self.respond({})
        return self.respond({'error':'Not available'},403)

    def connector(self):
        if self.client_address[0] != '127.0.0.1' or self.headers.get('Host') != f"127.0.0.1:{CONFIG['port']}":
            return self.respond({'error':'Connect from the browser on this PC.'},403)
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 262144 or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Invalid connector request.')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body,dict):
                raise ValueError('Invalid connector request.')
            if self.path == '/connector/pair':
                expected=CONFIG.get('connector_extension_id','')
                origin=self.headers.get('Origin','')
                if not re.fullmatch('[a-p]{32}',expected) or self.headers.get('X-Azoth-Extension')!=expected or origin not in ('','chrome-extension://'+expected):
                    return self.respond({'error':'Use the installed Azoth Local Capture Connector on this PC.'},403)
                return self.respond({'token':CONFIG['connector_token']})
            if not hmac.compare_digest(self.headers.get('X-Azoth-Connector',''),CONFIG['connector_token']):
                return self.respond({'error':'Pair the connector first.'},401)
            with LOCK:
                items = read_json(STATE/'uploads.json',[])
                if self.path == '/connector/info':
                    return self.respond({'pending':sum(item['state']=='pending' for item in items)})
                if self.path == '/connector/poll':
                    signed_in = body.get('signed_in') is True
                    save_json(STATE/'connector-status.json',{'connected':True,'signed_in':signed_in,'reason':str(body.get('reason',''))[:80],
                        'version':str(body.get('version','1.0.0'))[:20],'seen_ms':int(time.time()*1000)})
                    mine = body.get('uploads',[])
                    if not isinstance(mine,list) or len(mine)>100:
                        raise ValueError('Invalid upload history.')
                    for item in items:
                        match = next((u for u in mine if isinstance(u,dict) and u.get('file')==item['file']),None)
                        if match and match.get('status') in ('queued','accepted','rejected','needs-info'):
                            item.update(state=match['status'],error='',result={k:match[k] for k in ('id','points','packets_new','packets_total','first_captures','reason','rank','total_points') if k in match})
                    job = next((i for i in items if i['state']=='pending' and (not i.get('automatic') or preferences()['auto_upload'])),None) if signed_in else None
                    if job:
                        archive = READY/job['file']
                        if archive.stat().st_size>10*1024*1024:
                            job.update(state='needs-info',error='This ZIP exceeds the helper’s 10 MB limit. Use Azoth’s upload page.')
                            job=None
                        else:
                            job['state']='sending'
                    save_json(STATE/'uploads.json',items)
                    if job:
                        return self.respond({'job':{'id':job['id'],'file':job['file'],'base64':base64.b64encode((READY/job['file']).read_bytes()).decode()}})
                    return self.respond({'job':None})
                if self.path == '/connector/result':
                    item = next((i for i in items if i['id']==body.get('id')),None)
                    if not item or item['state']!='sending':
                        raise ValueError('There is no matching upload in progress.')
                    code = body.get('status')
                    item['state'] = 'queued' if code==201 else 'pending' if code==401 else 'check_result'
                    item['error'] = str(body.get('error',''))[:500]
                    save_json(STATE/'uploads.json',items)
                    return self.respond({'ok':True})
            return self.respond({'error':'Not found'},404)
        except (OSError,ValueError,KeyError,TypeError) as error:
            return self.respond({'error':str(error)},400)

    def authorized(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            return 'azoth_local' in cookie and hmac.compare_digest(cookie['azoth_local'].value, CONFIG['token'])
        except Exception:
            return False

    def valid_host(self):
        return self.headers.get('Host') in (f"{CONFIG['host']}:{CONFIG['port']}",f"127.0.0.1:{CONFIG['port']}")

    def do_GET(self):
        if not self.valid_host():
            return self.respond({'error': 'Use the local IP address shown by the launcher.'}, 403)
        route = urllib.parse.urlsplit(self.path).path
        if route in ('/', '/app.js'):
            name = 'index.html' if route == '/' else 'app.js'
            cookie=f"azoth_local={CONFIG['token']}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200" if route=='/' and self.client_address[0]=='127.0.0.1' else None
            return self.respond((ROOT / 'dist' / name).read_bytes(), kind='text/html; charset=utf-8' if route == '/' else 'text/javascript; charset=utf-8',cookie=cookie)
        if not self.authorized():
            return self.respond({'error': 'Enter the pairing PIN.'}, 401)
        if route == '/api/state':
            seen=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('catalog',[''])[0]
            return self.respond(status(include_catalog=seen!=str(catalog().get('fetched_at'))))
        if route == '/api/live':
            value=status(False)
            return self.respond({key:value[key] for key in ('live','guide','plan','setup','recovery_enabled','preferences')})
        if route.startswith('/download/'):
            key = route.removeprefix('/download/')
            report = next((r for r in available_reports() if r.get('id') == key), None)
            if report:
                return self.respond((READY / report['archive']).read_bytes(), kind='application/zip')
        return self.respond({'error': 'Not found'}, 404)

    def do_POST(self):
        if self.path.startswith('/connector/'):
            return self.connector()
        origin = 'http://'+self.headers.get('Host','')
        if not self.valid_host() or self.headers.get('Origin') != origin or self.headers.get('X-Azoth-Local') != '1':
            return self.respond({'error': 'Local requests only.'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Invalid request size or type.')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('The request must be a JSON object.')
            route = urllib.parse.urlsplit(self.path).path
            if route == '/api/login':
                attempts = [t for t in self.attempts.get(self.client_address[0], []) if time.monotonic()-t < 60]
                if len(attempts) >= 5:
                    return self.respond({'error': 'Wait one minute before trying again.'}, 429)
                if not hmac.compare_digest(str(body.get('pin', '')), CONFIG['pin']):
                    self.attempts[self.client_address[0]] = attempts + [time.monotonic()]
                    return self.respond({'error': 'That PIN does not match.'}, 401)
                self.attempts[self.client_address[0]] = []
                return self.respond({'ok': True}, cookie=f"azoth_local={CONFIG['token']}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200")
            if not self.authorized():
                return self.respond({'error': 'Enter the pairing PIN.'}, 401)
            with LOCK:
                if route == '/api/plan':
                    if draft().get('phase') == 'running' or RECORDER_LOCK.locked():
                        raise ValueError('Finish the recording before changing the mission or marking method.')
                    ids = body.get('ids', [])
                    valid = set(packets()) | PAIR_IDS
                    if not isinstance(ids, list) or not 1 <= len(ids) <= 4 or any(type(i) is not int or i not in valid for i in ids):
                        raise ValueError('Choose one to four listed missions.')
                    if len(ids)!=len(set(ids)):
                        raise ValueError('Choose each packet only once.')
                    mode = body.get('mode', 'f8')
                    if mode not in ('f8', 'phone'):
                        raise ValueError('Unknown marking mode.')
                    save_json(STATE / 'plan.json', {'ids': ids, 'mode': mode,'finished_session':draft().get('started_ms')})
                    if read_json(STATE/'control.json').get('state')=='needs_attention':
                        save_json(STATE/'control.json',{'state':'ready'})
                elif route == '/api/mark':
                    current, chosen = draft(), plan()
                    active=mission_segments(read_json(STATE/f"run-{current.get('started_ms')}.json"),current)[-1]
                    if current.get('phase') != 'running' or body.get('started_ms') != current.get('started_ms'):
                        raise ValueError('Start a session in Azoth Capture first, then refresh this page.')
                    if read_json(STATE/f"run-{current['started_ms']}.json") and recorder_status().get('capture')!='running':
                        raise ValueError('The recorder is no longer collecting. Finish and save this session first.')
                    if active_disconnect(game_evidence(current.get('started_ms'))):
                        raise ValueError('Wait until your character returns to the world before marking the next action.')
                    if chosen['mode'] != 'phone' or not set(chosen['ids']).issubset(set(active['ids'])):
                        raise ValueError('Use phone mode and select these same targets in Azoth Capture.')
                    notes = phone_notes(current['started_ms'])
                    guide = active['guide'] or instructions(chosen['ids'])
                    index=len(notes)-active['phone_start']
                    if body.get('index') != index or index >= len(guide):
                        raise ValueError('This step was already marked; refresh the page.')
                    action = guide[index]
                    notes.append({'t_ms': int(time.time()*1000), 'text': action['label'], 'target': action['target'], 'via': 'phone'})
                    save_json(STATE / f"phone-{current['started_ms']}.json", notes)
                elif route == '/api/prepare':
                    path = session_files().get(body.get('id'))
                    if not path:
                        raise ValueError('That saved session is unavailable.')
                    return self.respond(prepare(path))
                elif route == '/api/review':
                    report, journal, _, revision = review_source(body.get('id'))
                    return self.respond({'id': report['id'], 'journal': journal, 'revision': revision})
                elif route == '/api/review-save':
                    report = save_review(body)
                    queue_upload(report, reviewed=True)
                    return self.respond(report)
                elif route == '/api/start':
                    return self.respond(start_run(body),202)
                elif route == '/api/next':
                    return self.respond(next_packet(body))
                elif route == '/api/stop':
                    return self.respond(stop_run(body))
                elif route == '/api/overlay':
                    start_overlay()
                elif route == '/api/preferences':
                    if set(body)-{'auto_upload','character','world'}:
                        raise ValueError('Unknown preference.')
                    updated=preferences()
                    for key,value in body.items():
                        if key=='auto_upload':
                            if type(value) is not bool:
                                raise ValueError('Choose whether uploads are automatic.')
                        elif not isinstance(value,str) or len(value)>80 or any(ord(ch)<32 for ch in value):
                            raise ValueError('Use a character or world name up to 80 characters.')
                        updated[key]=value
                    save_json(STATE/'preferences.json',updated)
                    current=draft()
                    if 'auto_upload' in body and current.get('phase')=='running':
                        path=STATE/f"run-{current['started_ms']}.json"
                        run=read_json(path)
                        if run:
                            run['auto_upload']=body['auto_upload'];save_json(path,run)
                elif route == '/api/calibrate':
                    start_calibration(body.get('screen'))
                elif route == '/api/submit':
                    report,_,_,_=review_source(body.get('id'))
                    queue_upload(report,reviewed=report.get('reviewed',False),explicit=True)
                    if not any(item['ledger_sha256']==report['ledger_sha256'] for item in read_json(STATE/'uploads.json',[])):
                        raise ValueError('Review the uncertain markers before sending this capture.')
                elif route == '/api/recovery-mode':
                    if type(body.get('enabled')) is not bool:
                        raise ValueError('Choose whether to resume automatically.')
                    if body['enabled'] and not recovery_ready():
                        raise ValueError('Set up the character and disconnect screens first.')
                    save_json(STATE/'recovery-settings.json',{'enabled':body['enabled']})
                    current=draft()
                    if current.get('phase')=='running':
                        path=STATE/f"run-{current['started_ms']}.json"
                        run=read_json(path)
                        if run:
                            run['auto_recover']=body['enabled'];save_json(path,run)
                elif route == '/api/refresh':
                    refresh_catalog()
                else:
                    return self.respond({'error': 'Not found'}, 404)
            return self.respond({'ok': True})
        except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
            return self.respond({'error': str(error)}, 400)


def recover_dispatches():
    path=STATE/'uploads.json'
    items=read_json(path,[])
    changed=False
    for item in items:
        if item.get('state')=='sending' or (str(path) in RECOVERED_FILES and item.get('state')=='pending'):
            item.update(state='check_result',error='The app restarted during an uncertain upload. Checking My uploads; no automatic retry.')
            changed=True
    if changed:
        save_json(path,items)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--prefix', type=int, default=24)
    parser.add_argument('--port', type=int, default=8877)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.host)
    if address.version != 4 or not any(address in ipaddress.ip_network(block) for block in ('127.0.0.1/32','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise SystemExit('Bind to loopback or one specific private LAN IPv4 address.')
    if not 1<=args.port<=65535 or not 8<=args.prefix<=32:
        raise SystemExit('Invalid port or subnet prefix.')
    STATE.mkdir(parents=True, exist_ok=True)
    CONFIG.update(read_json(STATE / 'access.json'))
    CONFIG.update(host=args.host, port=args.port, subnet=str(ipaddress.ip_network(f'{args.host}/{args.prefix}', strict=False)))
    CONFIG.setdefault('pin', f'{secrets.randbelow(1000000):06d}')
    CONFIG.setdefault('token', secrets.token_urlsafe(32))
    CONFIG.setdefault('connector_token', secrets.token_urlsafe(32))
    manifest=read_json(ROOT/'browser-connector/manifest.json')
    key=base64.b64decode(manifest['key'],validate=True)
    CONFIG['connector_extension_id']=''.join(chr(97+int(ch,16)) for ch in hashlib.sha256(key).hexdigest()[:32])
    save_json(STATE / 'access.json', CONFIG)
    recover_dispatches()
    server = LANServer((args.host, args.port), Handler)
    connector = LANServer(('127.0.0.1', args.port), Handler) if args.host!='127.0.0.1' else None
    save_json(STATE / 'running.json', {'pid': os.getpid(), 'url': f'http://{args.host}:{args.port}', 'started_ms': int(time.time()*1000)})
    threading.Thread(target=watch, daemon=True).start()
    threading.Thread(target=recover_watch, daemon=True).start()
    threading.Thread(target=catalog_watch, daemon=True).start()
    if connector:
        threading.Thread(target=connector.serve_forever, daemon=True).start()
    server.serve_forever()


if __name__ == '__main__':
    main()
