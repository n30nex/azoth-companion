"""Task changes preserve one recorder; uploads do not gate the next target."""
import copy
import tempfile
import sys
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import server

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    server.STATE=root/'state';server.APP_DATA=root/'app';server.READY=root/'ready';server.GAME_LOG=root/'Game.log'
    server.save_json(server.APP_DATA/'settings.json',{'output_dir':str(root/'captures')})
    catalog={'needed':{'activities':[{'packets':[{'idx':idx,'activity':'Gathering' if idx in (5195,3379) else 'Inventory & gear','status':'wanted','short':str(idx)} for idx in (5195,5755,663,3173,3175,3379)]}]}}
    server.save_json(server.STATE/'catalog.json',catalog)
    started=1000000
    journal={'phase':'running','name':'continuous-test','started_ms':started,'targets':[5195],'activity':'Gathering',
        'steps':[{'t_ms':started+n,'text':f'Step {n}','via':'hotkey'} for n in range(1,5)]}
    original=copy.deepcopy(journal)
    server.save_json(server.APP_DATA/'draft.json',journal)
    server.save_json(server.STATE/'plan.json',{'ids':[5195],'mode':'f8'})
    server.save_json(server.STATE/f'run-{started}.json',{'ids':[5195],'mode':'f8','guide':server.instructions([5195]),'auto_upload':True})
    calls=[]
    def recorder(route,body=None,timeout=4):
        calls.append(route)
        assert route=='/stop'
        current=server.draft();current['phase']='stopped';server.save_json(server.APP_DATA/'draft.json',current)
        return {'export_error':''}
    server.recorder_call=recorder
    server.recorder_status=lambda:{'capture':'running','ready':True,'connected':True}
    server.game_ui=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Task changes must not operate or close the game'))
    server.game_version=lambda:'test'
    request={'expected_ids':[5195],'started_ms':started,'segment':0}
    result=server.next_packet(request)
    assert result['continued_recording'] and result['targets']==[5755] and calls==[]
    assert server.draft()==original
    try:
        server.next_packet(request)
        raise AssertionError('A duplicate next command advanced again')
    except ValueError:
        pass
    journal['steps'] += [{'t_ms':started+n,'text':f'Step {n}','via':'hotkey'} for n in (5,6)]
    server.save_json(server.APP_DATA/'draft.json',journal)
    state=server.status()
    assert state['live']['index']==2 and state['live']['targets']==[5755] and state['live']['segment']==1
    labelled,warnings,_=server.labels_for(journal,[])
    assert labelled['targets']==[5195,5755] and labelled['activity']=='Other'
    assert [s.get('target') for s in labelled['steps']]==[5195,5195,5195,None,5755,5755]
    assert 'unconfirmed' in labelled['steps'][3]['text'] and warnings
    assert [s['t_ms'] for s in labelled['steps']]==[s['t_ms'] for s in journal['steps']]
    server.save_json(server.STATE/'uploads.json',[{'id':'older','state':'pending'}])
    server.stop_run({'started_ms':started})
    assert calls==['/stop'] and server.plan()['ids']==[3173,3175]
    assert {5195,5755} <= server.attempted_targets()
    assert server.read_json(server.STATE/'uploads.json')[0]['state']=='pending'
    # Phone marks have a separate boundary, so a second task starts at zero.
    started+=10000
    server.save_json(server.STATE/'mission-history.json',{})
    journal={'phase':'running','name':'phone-test','started_ms':started,'targets':[663],'steps':[]}
    server.save_json(server.APP_DATA/'draft.json',journal)
    server.save_json(server.STATE/'plan.json',{'ids':[663],'mode':'phone'})
    server.save_json(server.STATE/f'run-{started}.json',{'ids':[663],'mode':'phone','guide':server.instructions([663]),'auto_upload':True})
    notes=[{'t_ms':started+n,'text':f'Used quick-bar item {n}','target':663,'via':'phone'} for n in range(1,4)]
    server.save_json(server.STATE/f'phone-{started}.json',notes)
    server.next_packet({'expected_ids':[663],'started_ms':started,'segment':0})
    assert server.status()['live']['index']==0 and server.plan()['ids']==[5755]
    notes.append({'t_ms':started+4,'text':'Opened inventory','target':5755,'via':'phone'})
    server.save_json(server.STATE/f'phone-{started}.json',notes)
    assert server.status()['live']['index']==1
    assert server.labels_for(journal,notes)[0]['targets']==[663,5755]
    if '--serve-ui' in sys.argv:
        server.game_evidence=lambda *args:{'events':[{'kind':'entered_world','t_ms':started+1}],'eac_kicks':[],'continuity':'Isolated UI fixture'}
        server.save_json(server.STATE/'control.json',{'state':'needs_attention','error':'TEST ONLY — simulated recording; no game or real upload.'})
        server.CONFIG.update(host='127.0.0.1',port=0,subnet='127.0.0.0/8',pin='123456',token='fixture-only',connector_token='fixture-upload')
        httpd=server.LANServer(('127.0.0.1',0),server.Handler)
        server.CONFIG['port']=httpd.server_port
        timer=threading.Timer(180,httpd.shutdown);timer.daemon=True;timer.start()
        print(f'UI_FIXTURE http://127.0.0.1:{httpd.server_port}',flush=True)
        try:httpd.serve_forever()
        finally:httpd.server_close();timer.cancel()
print('PASS: next task makes no start/stop/game call, extra marks stay with the old task, labels and timestamps survive, phone progress resets correctly, finish advances despite pending uploads.')
