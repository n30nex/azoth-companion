"""Skipping works before/during recording and never restarts the game."""
import copy
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import server

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    server.STATE=root/'state';server.APP_DATA=root/'app';server.READY=root/'ready';server.GAME_LOG=root/'Game.log'
    server.save_json(server.APP_DATA/'settings.json',{'output_dir':str(root/'captures')})
    items=[{'idx':491,'status':'wanted','priority':True,'activity':'Combat','confidence':'likely'}]
    for idx,activity,confidence,status in ((9876,'Inventory & gear','likely','wanted'),
        (9877,'Movement','likely','wanted'),(9878,'Inventory & gear','guess','wanted'),
        (9879,'Inventory & gear','likely','captured'),(9880,'Developer-only','likely','wanted')):
        items.append({'idx':idx,'status':status,'activity':activity,'confidence':confidence,
                      'how_to_capture':['First action.','Second action.']})
    server.save_json(server.STATE/'catalog.json',{'needed':{'activities':[{'packets':items}]}})
    started=1000000
    journal={'phase':'running','name':'skip-test','started_ms':started,'targets':[491],'steps':[]}
    server.save_json(server.APP_DATA/'draft.json',journal)
    server.save_json(server.STATE/'plan.json',{'ids':[491],'mode':'f8'})
    server.save_json(server.STATE/f'run-{started}.json',{'ids':[491],'mode':'f8','guide':server.instructions([491])})
    def forbidden(*args,**kwargs):
        raise AssertionError('Skipping must not start, stop, or control the game/recorder')
    server.recorder_call=server.game_ui=forbidden
    server.recorder_status=lambda:{'capture':'running','ready':True,'connected':True}
    server.game_version=lambda:'test'
    request={'expected_ids':[491],'started_ms':started,'segment':0}
    try:
        server.next_packet(request)
        raise AssertionError('Incomplete task advanced without explicit skip')
    except ValueError:
        pass
    before=(server.APP_DATA/'draft.json').read_bytes()
    result=server.next_packet({**request,'skip':True})
    assert result['continued_recording'] and result['targets']==[9876]
    assert (server.APP_DATA/'draft.json').read_bytes()==before
    assert server.status()['live']['completed_tasks']==0
    assert server.read_json(server.STATE/'mission-history.json')['491']['skipped']
    # Partial marks stay exactly where they were when skipping a second task.
    journal['steps']=[{'t_ms':started+10,'text':'First action.','via':'hotkey'}]
    server.save_json(server.APP_DATA/'draft.json',journal)
    before=copy.deepcopy(journal)
    result=server.next_packet({'expected_ids':[9876],'started_ms':started,'segment':1,'skip':True})
    assert result['targets']==[9877] and server.draft()==before
    assert server.status()['live']['completed_tasks']==0
    assert server.read_json(server.STATE/'mission-history.json')['9876']['skipped']
    # An idle skip changes only the plan/history and cannot modify the saved run.
    journal['phase']='stopped';server.save_json(server.APP_DATA/'draft.json',journal)
    saved_run=server.read_json(server.STATE/f'run-{started}.json')
    request={'expected_ids':[9877],'skip':True}
    result=server.next_packet(request)
    assert not result['continued_recording'] and result['targets']==[9878]
    assert server.read_json(server.STATE/f'run-{started}.json')==saved_run
    assert server.read_json(server.STATE/'mission-history.json')['9877']['session_ms'] is None
    assert {491,9876,9877}<=set(server.status()['skipped_ids'])
    assert server.recommended_targets([9878])==[]
    try:
        server.next_packet(request)
        raise AssertionError('Double click advanced twice')
    except ValueError:
        pass
print('PASS: visible-skip backend works idle and running, preserves partial marks, remembers skips, excludes completed/skipped targets and never controls the game.')
