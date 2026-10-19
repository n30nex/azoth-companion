"""Public defaults, explicit sharing, cached catalog, and isolated profile guards."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
import server
from test_fixture import capture

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    server.STATE=root/'state';server.APP_DATA=root/'app';server.READY=root/'ready';server.GAME_LOG=root/'Game.log'
    server.save_json(server.APP_DATA/'settings.json',{'output_dir':str(root/'captures')})
    server.recorder_status=lambda:{'connected':False,'ready':False}
    assert server.preferences()['auto_upload'] is False
    assert not server.recovery_enabled()
    assert server.game_version()=='Not configured'
    server.save_json(server.STATE/'catalog.json',{'fetched_at':1,'needed':{'activities':[]}})
    assert server.catalog()['fetched_at']==1
    assert 'catalog' in server.status() and 'catalog' not in server.status(False)
    server.save_json(server.STATE/'catalog.json',{'fetched_at':2,'needed':{'activities':[]}})
    assert server.catalog()['fetched_at']==2
    source=capture(root/'captures/synthetic/send')
    journal=json.loads(source.read_text())
    server.save_json(server.STATE/('run-'+str(journal['started_ms'])+'.json'),{'auto_upload':True})
    report=server.prepare(source)
    server.queue_upload(report)
    assert server.read_json(server.STATE/'uploads.json',[])==[], 'Sharing must be opted in on the current profile'
    server.queue_upload(report,explicit=True)
    items=server.read_json(server.STATE/'uploads.json',[])
    assert len(items)==1 and not items[0]['automatic']
    server.queue_upload(report,explicit=True)
    assert len(server.read_json(server.STATE/'uploads.json',[]))==1
    path=server.READY/report['archive']
    original=path.read_bytes();path.write_bytes(b'broken')
    try:
        server.review_source(report['id'])
        raise AssertionError('Modified archive was trusted')
    except (ValueError,server.zipfile.BadZipFile):pass
    path.write_bytes(original)
    assert server.validate_capture(journal,(source.parent/'ledger.bin').read_bytes())['records']==18
    pending={'state':'pending','id':'synthetic'}
    upload_path=server.STATE/'uploads.json'
    server.save_json(upload_path,[pending]);server.save_json(upload_path,[pending])
    upload_path.write_bytes(b'\x00'*100)
    server.recover_dispatches()
    assert server.read_json(upload_path)[0]['state']=='check_result','Recovered pending history must not blindly resend'

manifest=json.loads((server.ROOT/'browser-connector/manifest.json').read_text())
key=base64.b64decode(manifest['key'],validate=True)
identity=''.join(chr(97+int(c,16)) for c in hashlib.sha256(key).hexdigest()[:32])
assert len(identity)==32 and len(key)>200
assert set(manifest['host_permissions'])=={'http://127.0.0.1/*','https://projectazoth.com/*'}
print('PASS: opt-in sharing, manual submission, catalog invalidation, minimal progress responses, private profile defaults and stable connector identity.')
