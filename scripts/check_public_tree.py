"""Fail if source staging contains runtime data, credentials or user-home paths."""
import argparse
import json
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--forbid-file',type=Path)
args=parser.parse_args()
sentinels=json.loads(args.forbid_file.read_text()) if args.forbid_file else []
tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
assert any(tracked),'Stage the source files before running this check.'
denied_names={'access.json','dashboard-bridge.json','draft.json','uploads.json','keylog.txt','Phone connection.txt'}
denied_suffixes={'.exe','.zip','.bin','.log','.dmp','.key','.pem','.pyc','.lnk'}
patterns=[re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(rb'AKIA[A-Z0-9]{16}'),
          re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
          re.compile(rb'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s"\']+',re.I)]
failures=[]
for name in filter(None,tracked):
    path=root/name
    if path.name in denied_names or path.suffix.lower() in denied_suffixes or '/menu-templates/' in name or name.startswith('AzothCapture/'):
        failures.append((name,'runtime/private file'));continue
    data=path.read_bytes()
    if path.suffix.lower() not in {'.png','.ico','.woff2'} and b'\x00' in data:
        failures.append((name,'damaged text file containing NUL bytes'))
    if any(pattern.search(data) for pattern in patterns):failures.append((name,'credential or user-home path'))
    if any(value.encode() in data for value in sentinels if value):failures.append((name,'private local identifier'))
if failures:
    for name,reason in failures:print(name+': '+reason)
    raise SystemExit('Public source check failed. No secret values are printed.')
print(f'PASS: {sum(bool(name) for name in tracked)} staged source files contain no blocked runtime files or detected credentials.')
