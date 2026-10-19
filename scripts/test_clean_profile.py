"""Launch the real HTTP service on an isolated profile without starting any game."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as folder:
    profile=Path(folder)
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    env={**os.environ,'AZOTH_COMPANION_DATA':str(profile/'state'),'AZOTH_CAPTURE_DATA':str(profile/'recorder')}
    process=subprocess.Popen([sys.executable,str(root/'AzothCompanion/server.py'),'--host','127.0.0.1','--port',str(port)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            if (profile/'state/running.json').exists():break
            if process.poll() is not None:raise AssertionError(process.communicate()[1].decode())
            time.sleep(.1)
        base=f'http://127.0.0.1:{port}'
        with urllib.request.urlopen(base) as response:
            assert response.status==200
            cookie=response.headers['Set-Cookie'].split(';')[0]
            assert 'HttpOnly' in response.headers['Set-Cookie']
        request=urllib.request.Request(base+'/api/state',headers={'Cookie':cookie})
        with urllib.request.urlopen(request) as response:state=json.load(response)
        assert not state['preferences']['auto_upload'] and not state['recovery_enabled']
        assert state['live']['phase']=='idle' and state['version']=='Not configured'
        assert state['connection']['phone_url']==''
        try:
            urllib.request.urlopen(urllib.request.Request(base+'/api/state',headers={'Host':'evil.example'}))
            raise AssertionError('Untrusted Host accepted')
        except urllib.error.HTTPError as error:assert error.code==403
        assert not (profile/'recorder/draft.json').exists()
        print('PASS: fresh profile boots on loopback, pairs local browser, defaults to no uploads/menu input, and rejects DNS rebinding.')
    finally:
        process.terminate();process.communicate(timeout=10)
