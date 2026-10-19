"""Check process ownership and manual world entry without sending game input."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import game_ui as ui

with TemporaryDirectory() as folder, patch.object(ui,'STATE',Path(folder)):
    folder=Path(folder)/'menu-templates';folder.mkdir()
    picture=ui.np.random.default_rng(7).integers(20,230,(300,500,3),dtype=ui.np.uint8)
    ui.cv2.imwrite(str(folder/'character-card.png'),picture[80:120,100:180])
    ui.save_json(folder/'sizes.json',{'character-card':[500,300]})
    assert ui.locate(picture,'character-card')==(140,100)
    repeated=picture.copy();repeated[180:220,300:380]=picture[80:120,100:180]
    assert ui.locate(repeated,'character-card') is None
    assert ui.locate(picture,'missing') is None
    assert ui.locate(ui.np.zeros_like(picture),'character-card') is None
    with patch.object(ui,'game_window',return_value=(1,2)),patch.object(ui,'activate'),patch.object(ui,'frame',return_value=(picture,(0,0))),patch.object(ui.cv2,'selectROI',return_value=(0,0,0,0)):
        try:
            ui.calibrate('character')
            raise AssertionError('Cancelled calibration accepted')
        except ValueError:pass
    assert not (folder/'play.png').exists()

with TemporaryDirectory() as folder:
    original=Path(folder)/'NewWorld.exe'
    alias=Path(folder)/'redirected.exe'
    other=Path(folder)/'other.exe'
    original.write_bytes(b'exact installed file');other.write_bytes(original.read_bytes())
    os.link(original,alias)
    with patch.object(ui,'GAME',original):
        assert ui.is_game_executable(alias)
        assert not ui.is_game_executable(other)
        assert not ui.is_game_executable(Path(folder)/'missing.exe')

session=1700000000000
created=(session+1000+11644473600000)*10000
with TemporaryDirectory() as folder, patch.object(ui,'STATE',Path(folder)), patch.object(ui,'process_birth',return_value=created):
    ui.save_json(Path(folder)/'recovery-settings.json',{'enabled':True})
    owner=ui.claim_game(session,42)
    assert ui.read_json(Path(folder)/'game-owner.json')==owner
    for pid,birth in ((43,created),(42,created+1)):
        try:
            ui.claim_game(session,42,pid,birth)
            raise AssertionError('Different process identity accepted')
        except RuntimeError:
            pass
    with patch.object(ui,'process_birth',return_value=created-100000000):
        try:
            ui.claim_game(session,42)
            raise AssertionError('A game older than the session was adopted')
        except RuntimeError:
            pass
    evidence=Path(folder)/f'connection-{session}.json'
    assert not ui.world_entered(session)
    events=[{'kind':'entered_world','t_ms':session+2000}]
    ui.save_json(evidence,{'events':events})
    with patch.object(ui,'ensure_session'), patch.object(ui,'game_window',return_value=(101,42)), patch.object(ui,'activate',side_effect=AssertionError('Input after world entry')):
        result=ui.enter(session)
        assert result['state']=='in_world' and result['pid']==42 and result['created']==created
    events.append({'kind':'eac_kick','t_ms':session+3000})
    ui.save_json(evidence,{'events':events})
    assert not ui.world_entered(session)
    events.append({'kind':'entered_world','t_ms':session+4000})
    ui.save_json(evidence,{'events':events})
    assert ui.world_entered(session)
    events.append({'kind':'disconnected','t_ms':session+5000})
    ui.save_json(evidence,{'events':events})
    assert not ui.world_entered(session)
print('PASS: ownership saved before menu selection; old or changed processes rejected; manual world entry stops menu input; disconnect and return evidence respected.')
