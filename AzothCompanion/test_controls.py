"""Recorder commands and upload delivery, entirely isolated from the live apps."""
import base64
import json
from pathlib import Path
import threading
import time
import sys
import tempfile
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parent))
import server
from test_fixture import capture

fixture_temp=tempfile.TemporaryDirectory()
fixture=Path(fixture_temp.name)
server.STATE=fixture/'state';server.APP_DATA=fixture/'app';server.READY=fixture/'ready';server.GAME_LOG=fixture/'Game.log'
server.save_json(server.APP_DATA/'settings.json',{'output_dir':str(fixture/'captures')})
server.save_json(server.STATE/'catalog.json',{'needed':{'activities':[{'packets':[{'idx':2818,'activity':'Combat','short':'Hit reaction'}]}]}})
server.save_json(server.STATE/'plan.json',{'ids':[2818],'mode':'f8'})
server.save_json(server.STATE/'preferences.json',{'auto_upload':True})
calls=[]
gate=threading.Event()
started=int(time.time()*1000)
def recorder(route,body=None,timeout=4):
    calls.append((route,body))
    if route=='/start':
        gate.wait(3)
        result={'phase':'running','name':body['name'],'started_ms':started,'targets':body['targets'],'steps':[]}
        server.save_json(server.APP_DATA/'draft.json',result);return result
    if route=='/stop':
        result=server.draft();result['phase']='stopped';server.save_json(server.APP_DATA/'draft.json',result);return {'export_error':''}
    raise AssertionError(route)
server.recorder_call=recorder
server.login_character=lambda _:None
first=server.start_run({'request_id':'isolated-start-001'})
assert first['state']=='starting'
assert server.start_run({'request_id':'isolated-start-001'})==first
try:
    server.start_run({'request_id':'isolated-start-002'})
    raise AssertionError('Overlapping start accepted')
except ValueError:pass
gate.set()
for _ in range(30):
    if server.read_json(server.STATE/'control.json').get('state')=='recording':break
    time.sleep(.1)
assert [r for r,b in calls]==['/start']
assert calls[0][1]['targets']==[2818] and calls[0][1]['activity']=='Combat'
snapshot=server.read_json(server.STATE/f'run-{started}.json')
assert len(snapshot['guide'])==3 and snapshot['auto_upload']
swap_start=started-1000
swap_guide=server.instructions([3902])
assert len(swap_guide)==5 and all(step['target']==3902 for step in swap_guide)
server.save_json(server.STATE/f'run-{swap_start}.json',{'ids':[3902],'mode':'f8','guide':swap_guide})
swaps={'started_ms':swap_start,'targets':[3902],'steps':[{'text':f'Step {n+1}','via':'hotkey','t_ms':swap_start+n+1} for n in range(5)]}
labelled,warnings,matched=server.labels_for(swaps,[])
assert matched and not warnings and labelled['steps'][-1]['text']=='Observed weapon swap 5'
assert [s['t_ms'] for s in labelled['steps']]==[s['t_ms'] for s in swaps['steps']]
assert len(server.instructions([3902,2818]))==8
test_journal={'started_ms':started,'targets':[2818],'steps':[{'text':f'Step {i+1}','via':'hotkey','t_ms':t} for i,t in enumerate((started+1,started+150,started+201))]}
labelled,notes,_=server.labels_for(test_journal,[],started+100,[(started+100,started+200)])
assert labelled['steps'][0]['target']==2818
assert 'target' not in labelled['steps'][1]
assert labelled['steps'][2]['text']=='Observed stagger or knockback 2'
assert not server.active_disconnect({'events':[{'kind':'entered_world','t_ms':started+200}],'eac_kicks':[started+100]})
assert server.active_disconnect({'events':[],'eac_kicks':[started+100]})
live=server.draft();live['steps']=[{'text':'Step 1','via':'hotkey','t_ms':started+1}]
server.save_json(server.APP_DATA/'draft.json',live)
server.stop_run({'started_ms':started})
assert len(server.read_json(server.STATE/'checkpoint.json')['remaining'])==2
assert server.parse_game_events('<2026-10-18 17:41:40.271>: Report Error: Reason: Errors::kicked_easyanticheat BannedUntilEpochMS: 123')[0]['kind']=='account_warning'

source=capture(fixture/'captures/synthetic-gathering/send')
journal=server.read_json(source)
marked,_,_=server.labels_for(journal,[])
server.save_json(server.STATE/f"run-{journal['started_ms']}.json",{'ids':[5078,5118],'mode':'f8','auto_upload':True,'guide':[{'text':s['text'],'label':s['text'],'target':s['target']} for s in marked['steps']]})
report=server.prepare(source)
server.queue_upload(report,reviewed=True)
server.queue_upload(report,reviewed=True)
assert len(server.read_json(server.STATE/'uploads.json'))==1

server.CONFIG.update(host='127.0.0.1',port=0,subnet='127.0.0.0/8',pin='123456',token='dashboard-only',connector_token='upload-only',connector_extension_id='a'*32)
httpd=server.LANServer(('127.0.0.1',0),server.Handler);server.CONFIG['port']=httpd.server_port
threading.Thread(target=httpd.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{httpd.server_port}'
def request(path,body,token='upload-only',extension='',origin=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Azoth-Connector':token,'X-Azoth-Extension':extension,'Origin':base if origin is None else origin,'X-Azoth-Local':'1'})
    try:
        with urllib.request.urlopen(req) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
try:
    assert request('/connector/pair',{},'',extension='a'*32,origin='chrome-extension://'+'a'*32)[1]['token']=='upload-only'
    assert request('/connector/pair',{},'',extension='b'*32,origin='chrome-extension://'+'b'*32)[0]==403
    assert request('/connector/pair',{},'',extension='a'*32,origin='https://example.com')[0]==403
    assert request('/connector/pair',{},'')[0]==403
    assert request('/connector/info',{})[1]['pending']==1
    assert request('/connector/poll',{'signed_in':True},'wrong')[0]==401
    assert request('/api/start',{'request_id':'another-test-start'})[0]==401
    assert request('/connector/poll',{'signed_in':False,'uploads':[]})[1]['job'] is None
    code,data=request('/connector/poll',{'signed_in':True,'uploads':[]})
    job=data['job'];assert code==200 and job['id']==report['id']
    assert base64.b64decode(job['base64'])==(server.READY/report['archive']).read_bytes()
    assert request('/connector/poll',{'signed_in':True,'uploads':[]})[1]['job'] is None
    assert request('/connector/result',{'id':job['id'],'status':201})[0]==200
    assert server.read_json(server.STATE/'uploads.json')[0]['state']=='queued'
    assert request('/connector/poll',{'signed_in':True,'uploads':[{'file':job['file'],'status':'accepted','points':1,'packets_new':0}]})[0]==200
    assert server.read_json(server.STATE/'uploads.json')[0]['state']=='accepted'
finally:
    httpd.shutdown();httpd.server_close()
print('PASS: isolated start/configure/idempotency, saved guide, checkpoint resume, account-warning stop, one upload per ledger, scoped connector auth, exact ZIP transport and queued-versus-accepted status.')
