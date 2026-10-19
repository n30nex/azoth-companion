"""Allowlisted portable Windows package; source and user state are never swept in."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path,required=True)
parser.add_argument('--version',default='0.1.0');parser.add_argument('--out',type=Path,default=root/'artifacts')
args=parser.parse_args()
if not args.exe.is_file():raise SystemExit('Build the recorder first.')
allowed=['Start-Azoth.cmd','Start-Azoth.ps1','README.md','LICENSE','NOTICE.md','PRIVACY.md',
         'docs/GETTING-STARTED.md','docs/TROUBLESHOOTING.md','docs/AUDIT.md',
         'AzothCompanion/server.py','AzothCompanion/game_ui.py','AzothCompanion/Overlay.ps1',
         'AzothCompanion/Start-Companion.ps1','AzothCompanion/Stop-Companion.ps1','AzothCompanion/Allow-Phone-Access.ps1']
for folder in ('AzothCompanion/dist','AzothCompanion/browser-connector','recorder/third_party/licenses'):
    allowed += [str(p.relative_to(root)).replace('\\','/') for p in (root/folder).rglob('*') if p.is_file()]
allowed += ['recorder/LICENSE','recorder/NOTICE.md']
allowed += [str(p.relative_to(root)).replace('\\','/') for p in (root/'recorder/frontend/fonts').rglob('*.txt')]
files={name:(root/name).read_bytes() for name in allowed}
files['AzothCapture/AzothCapture.Companion.exe']=args.exe.read_bytes()
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
files['BUILD-INFO.json']=(json.dumps({'version':args.version,'source_commit':commit,
    'recorder_sha256':hashlib.sha256(files['AzothCapture/AzothCapture.Companion.exe']).hexdigest(),
    'source_url':'https://github.com/n30nex/azoth-companion/tree/'+commit},indent=2)+'\n').encode()
args.out.mkdir(parents=True,exist_ok=True)
archive=args.out/f'AzothCompanion-{args.version}-windows-x64.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as package:
    for name,data in sorted(files.items()):
        info=zipfile.ZipInfo('AzothCompanion/'+name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        package.writestr(info,data)
with zipfile.ZipFile(archive) as package:
    assert package.testzip() is None
    assert len(package.namelist())==len(files)
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(args.out/'SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
print(archive.name,digest)
