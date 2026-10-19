"""Synthetic record framing only. No real packets, identities, or account data."""
import json
from pathlib import Path
import struct

def capture(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    start=1700000000000
    journal={'schema':1,'app':'azoth-capture test','session':'synthetic-gathering','activity':'Gathering',
        'started_ms':start,'stopped_ms':start+20000,'tz_offset_min':0,'targets':[5078,5118],
        'steps':[{'t_ms':start+(n+1)*1000,'text':f'Step {n+1}','via':'hotkey'} for n in range(16)]}
    records=[]
    for n in range(18):
        payload=b'\x80\x01'+n.to_bytes(2,'big')+b'\x10\x00\x04'+n.to_bytes(2,'big')+b'TEST'
        records.append(struct.pack('<IQBBBBQI',0x4C44574E,start+n*1000,n%2,0,0,0,0,len(payload))+payload)
    (folder/'ledger.bin').write_bytes(b''.join(records))
    (folder/'steps.json').write_text(json.dumps(journal),encoding='utf-8')
    return folder/'steps.json'
