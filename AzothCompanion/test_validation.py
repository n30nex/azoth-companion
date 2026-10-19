"""Validation, packaging and HTTP guards using synthetic records only."""
import copy
import json
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server
import tempfile
from test_fixture import capture

def check():
    temporary=tempfile.TemporaryDirectory()
    root=Path(temporary.name)
    server.STATE=root/'state';server.APP_DATA=root/'app';server.READY=root/'ready';server.GAME_LOG=root/'Game.log'
    server.save_json(server.APP_DATA/'settings.json',{'output_dir':str(root/'captures')})
    source=capture(root/'captures/synthetic/send').parent
    original_steps = source.joinpath('steps.json').read_bytes()
    ledger = source.joinpath('ledger.bin').read_bytes()
    journal = json.loads(original_steps)
    annotated, warnings, paired = server.labels_for(journal, [])
    assert paired and len(annotated['steps']) == 16
    assert annotated['steps'][0]['text'] == 'Resource node 1: gather prompt appeared'
    assert annotated['steps'][-1]['target'] == 5118
    assert [s['t_ms'] for s in annotated['steps']] == [s['t_ms'] for s in journal['steps']]
    sheath = copy.deepcopy(journal)
    sheath['targets'] = [3899]
    sheath['steps'] = sheath['steps'][:6]
    labelled, warnings, paired = server.labels_for(sheath, [])
    assert paired and not warnings
    assert labelled['steps'][0]['text'] == 'Cycle 1: weapon sheathed'
    assert labelled['steps'][-1]['text'] == 'Cycle 3: weapon drawn'
    assert all(s['target'] == 3899 for s in labelled['steps'])
    assert len(server.instructions([3899])) == 6
    seventh = copy.deepcopy(journal['steps'][6])
    sheath['steps'].append(seventh)
    interrupted_at = sheath['steps'][5]['t_ms'] + 1
    labelled, warnings, paired = server.labels_for(sheath, [], interrupted_at)
    assert paired and 'unconfirmed' in labelled['steps'][-1]['text']
    assert 'target' not in labelled['steps'][-1]
    assert labelled['steps'][-2]['text'] == 'Cycle 3: weapon drawn'
    assert [s['t_ms'] for s in labelled['steps']] == [s['t_ms'] for s in sheath['steps']]
    log = '<2026-10-18 17:41:40.271>: GameConnection: Report Error: Reason: Errors::kicked_easyanticheat'
    events = server.parse_game_events(log + '\n' + log + '\n<bad>: unrelated secret text')
    assert events == [{'t_ms':1792345300271, 'kind':'eac_kick'}]
    assert server.parse_game_events(log + ' BannedUntilEpochMS: 0 {}') == events
    assert server.parse_game_events(log + ' BannedUntilEpochMS: 123 {}')[0]['kind']=='account_warning'
    assert server.game_evidence(None)['continuity'] == 'Not established from logs'
    custom = copy.deepcopy(journal)
    custom['steps'][0]['text'] = 'A real custom note'
    changed, warnings, paired = server.labels_for(custom, [])
    assert not paired and changed['steps'][0]['text'] == 'A real custom note' and warnings
    checks = server.validate_capture(annotated, ledger)
    assert checks['records'] == 18 and checks['decode_errors'] == 0
    for bad in (ledger[:-1], ledger + b'\x00', b''):
        try:
            server.validate_capture(annotated, bad)
            raise AssertionError('Damaged ledger was accepted')
        except ValueError:
            pass
    wrong = copy.deepcopy(annotated)
    wrong['steps'][0]['t_ms'] = wrong['started_ms'] - 1
    try:
        server.validate_capture(wrong, ledger)
        raise AssertionError('Out-of-session timestamp was accepted')
    except ValueError:
        pass
    destination = server.STATE / 'self-test-output'
    report = server.prepare(source / 'steps.json', destination)
    with zipfile.ZipFile(destination / report['archive']) as package:
        assert package.namelist() == ['ledger.bin', 'steps.json']
        assert package.read('ledger.bin') == ledger
        assert len(json.loads(package.read('steps.json'))['steps']) == 16
    assert source.joinpath('steps.json').read_bytes() == original_steps
    assert source.joinpath('ledger.bin').read_bytes() == ledger
    server.CONFIG.update(host='127.0.0.1', port=0, subnet='127.0.0.0/8', pin='123456', token='test-cookie-token')
    httpd = server.LANServer(('127.0.0.1', 0), server.Handler)
    server.CONFIG['port'] = httpd.server_port
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{httpd.server_port}'
    def request(path, payload=None, headers=None):
        request_headers = headers or {}
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None:
            request_headers = {'Content-Type':'application/json', 'Origin':base, 'X-Azoth-Local':'1', **request_headers}
        try:
            with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=request_headers)) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()
    try:
        assert request('/api/state')[0] == 401
        assert request('/api/review', {'id':'anything'})[0] == 401
        assert request('/api/login', {'pin':'000000'})[0] == 401
        code, headers, _ = request('/api/login', {'pin':'123456'})
        assert code == 200 and 'HttpOnly' in headers['Set-Cookie'] and 'SameSite=Strict' in headers['Set-Cookie']
        cookie = {'Cookie':'azoth_local=test-cookie-token'}
        assert request('/api/prepare', {'id':'../../etc/passwd'}, cookie)[0] == 400
        assert request('/api/plan', [], cookie)[0] == 400
        assert request('/api/plan', {'ids':[5078]}, {**cookie,'Origin':'http://example.com'})[0] == 403
        assert request('/../server.py', headers=cookie)[0] == 404
        assert not httpd.verify_request(None, ('8.8.8.8', 1234))
        isolated = server.STATE / ('flow-test-' + str(time.time_ns()))
        server.APP_DATA = isolated / 'app'
        server.STATE = isolated / 'state'
        server.READY = isolated / 'prepared'
        server.GAME_LOG = isolated / 'Game.log'
        capture_root = isolated / 'captures'
        server.save_json(server.APP_DATA / 'settings.json', {'output_dir':str(capture_root)})
        server.save_json(server.STATE / 'plan.json', {'ids':[5078,5118], 'mode':'phone'})
        started = int(time.time()*1000)
        server.save_json(server.APP_DATA / 'draft.json', {'phase':'running','started_ms':started,'targets':[5078,5118]})
        assert request('/api/mark', {'started_ms':started,'index':0}, cookie)[0] == 200
        assert request('/api/mark', {'started_ms':started,'index':0}, cookie)[0] == 400
        assert len(server.phone_notes(started)) == 1
        assert server.phone_notes(started)[0]['target'] == 5078
        assert request('/api/plan', {'ids':[5078,5118], 'mode':'f8'}, cookie)[0] == 400
        assert server.plan()['mode'] == 'phone'
        stamp = server.datetime.fromtimestamp((started+1)/1000, server.timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        server.GAME_LOG.write_text(f'<{stamp}>: Report Error: Reason: Errors::kicked_easyanticheat')
        assert request('/api/mark', {'started_ms':started,'index':1}, cookie)[0] == 400
        assert len(server.phone_notes(started)) == 1
        server.save_json(server.APP_DATA / 'draft.json', {'phase':'stopped'})
        assert request('/api/mark', {'started_ms':started,'index':1}, cookie)[0] == 400
        (capture_root / 'weapon-sheath-01').mkdir(parents=True)
        setup = server.run_setup({'ids':[3899]}, {'name':'weapon-sheath-02'})
        assert setup['name'] == 'weapon-sheath-03' and setup['marks'] == 6
        threading.Thread(target=server.watch, daemon=True).start()
        time.sleep(.2)
        export = capture_root / 'new-session' / 'send'
        export.mkdir(parents=True)
        export.joinpath('steps.json').write_bytes(original_steps)
        export.joinpath('ledger.bin').write_bytes(ledger)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and not list(server.READY.glob('*.zip')):
            time.sleep(.4)
        assert len(list(server.READY.glob('*.zip'))) == 1, 'Automatic finished-session processing did not produce a ZIP'
        initial = server.available_reports()[0]
        original_zip = (server.READY / initial['archive']).read_bytes()
        assert request('/api/review', {'id':'../../outside'}, cookie)[0] == 400
        code, _, body = request('/api/review', {'id':initial['id']}, cookie)
        review = json.loads(body)
        assert code == 200 and len(review['journal']['steps']) == 16
        edits = [{'text':s['text'],'unsure':False} for s in review['journal']['steps']]
        edits[0]['text'] = 'Gather prompt appeared at the first tree'
        edits[-1] = {'text':'I cannot recall the last action', 'unsure':True}
        request_body = {'id':review['id'],'revision':review['revision'],'steps':edits}
        assert request('/api/review-save', {**request_body,'revision':'stale'}, cookie)[0] == 400
        tampered = copy.deepcopy(request_body)
        tampered['steps'][0]['t_ms'] = 0
        assert request('/api/review-save', tampered, cookie)[0] == 400
        assert request('/api/review-save', {**request_body,'steps':edits[:-1]}, cookie)[0] == 400
        code, _, body = request('/api/review-save', request_body, cookie)
        revised = json.loads(body)
        assert code == 200 and revised['reviewed'] and revised['supersedes'] == initial['id']
        with zipfile.ZipFile(server.READY / revised['archive']) as package:
            assert package.namelist() == ['ledger.bin','steps.json']
            assert package.read('ledger.bin') == ledger
            revised_steps = json.loads(package.read('steps.json'))
            assert [s['t_ms'] for s in revised_steps['steps']] == [s['t_ms'] for s in journal['steps']]
            assert revised_steps['steps'][0]['text'] == edits[0]['text']
            assert 'unconfirmed' in revised_steps['steps'][-1]['text']
            assert 'target' not in revised_steps['steps'][-1]
        assert (server.READY / initial['archive']).read_bytes() == original_zip
        assert export.joinpath('steps.json').read_bytes() == original_steps
        assert export.joinpath('ledger.bin').read_bytes() == ledger
        count = len(list(server.READY.glob('*.zip')))
        assert request('/api/review-save', request_body, cookie)[0] == 200
        assert len(list(server.READY.glob('*.zip'))) == count, 'Identical review created another ZIP'
    finally:
        httpd.shutdown()
        httpd.server_close()
    print('PASS: synthetic capture validation, exact ZIP contents, original preservation, authentication, origin/file guards, unique run names, locked live plans, disconnect mark guard, automatic export, marker review with fixed timestamps, uncertain actions and duplicate ZIP prevention.')

if __name__ == '__main__':
    check()
