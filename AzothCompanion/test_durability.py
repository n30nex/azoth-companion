"""Forced-shutdown regressions, with no live state or game changes."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server

with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'uploads.json'
    with patch.object(server.os, 'fsync', wraps=server.os.fsync) as sync:
        server.save_json(path, {'state':'accepted'})
        server.save_json(path, {'state':'new'})
        assert sync.call_count==3
    path.write_bytes(b'\x00'*100)
    assert server.read_json(path)=={'state':'accepted'}
    server.save_json(path, {'state':'recovered'})
    assert json.loads(path.with_name('uploads.json.bak').read_text())=={'state':'accepted'}
    assert server.read_json(path)=={'state':'recovered'}

shim=Path(__file__).resolve().parents[1]/'recorder/internal/capture/embed/azoth_run.py'
spec=importlib.util.spec_from_file_location('dx11_shim',shim)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
exe=r'D:\SteamLibrary\steamapps\common\New World\Bin64\NewWorld.exe'
assert module.dx11_argv(exe)==[exe,'-dx11']
assert module.dx11_argv([exe,'-dx12','-foo','-DX11'])==[exe,'-foo','-dx11']
assert module.dx11_argv(['other.exe','-dx12'])==['other.exe','-dx12']
print('PASS: durable JSON recovery and exact DX11 launch arguments')
