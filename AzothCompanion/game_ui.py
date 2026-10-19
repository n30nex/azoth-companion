"""Normal, visible menu navigation for the user's verified character.
No process memory access, game injection, or anti-cheat changes.
"""
import argparse
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import sys
import time
import cv2
import numpy as np
from PIL import ImageGrab
sys.path.insert(0,str(Path(__file__).resolve().parent))
from server import STATE, APP_DATA, app_settings, preferences, read_json, save_json

ROOT=Path(__file__).resolve().parent
GAME=Path(app_settings().get('exe_path',''))
u=ctypes.WinDLL('user32',use_last_error=True)
k=ctypes.WinDLL('kernel32',use_last_error=True)
u.SetProcessDPIAware()
u.GetForegroundWindow.restype=W.HWND
u.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
k.CloseHandle.argtypes=[W.HANDLE]
k.GetExitCodeProcess.argtypes=[W.HANDLE,ctypes.POINTER(W.DWORD)]
k.GetProcessTimes.argtypes=[W.HANDLE,ctypes.POINTER(W.FILETIME),ctypes.POINTER(W.FILETIME),ctypes.POINTER(W.FILETIME),ctypes.POINTER(W.FILETIME)]
u.GetClientRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)]
u.ClientToScreen.argtypes=[W.HWND,ctypes.POINTER(W.POINT)]
u.SetForegroundWindow.argtypes=[W.HWND]
u.SwitchToThisWindow.argtypes=[W.HWND,W.BOOL]
u.ShowWindow.argtypes=[W.HWND,ctypes.c_int]
u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
u.OpenInputDesktop.argtypes=[W.DWORD,W.BOOL,W.DWORD];u.OpenInputDesktop.restype=W.HANDLE
u.GetUserObjectInformationW.argtypes=[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD,ctypes.POINTER(W.DWORD)]
u.CloseDesktop.argtypes=[W.HANDLE]
cv2.setNumThreads(1)

class MouseInput(ctypes.Structure):
    _fields_=[('dx',W.LONG),('dy',W.LONG),('data',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',ctypes.c_size_t)]
class KeyboardInput(ctypes.Structure):
    _fields_=[('vk',W.WORD),('scan',W.WORD),('flags',W.DWORD),('time',W.DWORD),('extra',ctypes.c_size_t)]
class InputUnion(ctypes.Union):
    _fields_=[('mouse',MouseInput),('keyboard',KeyboardInput)]
class Input(ctypes.Structure):
    _fields_=[('type',W.DWORD),('value',InputUnion)]
u.SendInput.argtypes=[W.UINT,ctypes.POINTER(Input),ctypes.c_int]
u.SendInput.restype=W.UINT

def send_input(event):
    if u.SendInput(1,ctypes.byref(event),ctypes.sizeof(event))!=1:
        raise RuntimeError('Windows did not accept the menu input. Check that the game and recorder run at the same permission level.')

def key(hwnd,code,session):
    ensure_session(session)
    if u.GetForegroundWindow()!=hwnd:raise RuntimeError('Game focus changed; no key was sent.')
    scan=u.MapVirtualKeyW(code,0)
    send_input(Input(1,InputUnion(keyboard=KeyboardInput(0,scan,8,0,0))))
    time.sleep(.1)
    send_input(Input(1,InputUnion(keyboard=KeyboardInput(0,scan,10,0,0))))

def normal_desktop():
    desktop=u.OpenInputDesktop(0,False,1)
    if not desktop:return False
    try:
        name=ctypes.create_unicode_buffer(256);needed=W.DWORD()
        return bool(u.GetUserObjectInformationW(desktop,2,name,ctypes.sizeof(name),ctypes.byref(needed))) and name.value.casefold()=='default'
    finally:u.CloseDesktop(desktop)

def activate(hwnd):
    if not normal_desktop():raise RuntimeError('Unlock Windows before automatic game login.')
    u.ShowWindow(hwnd,9);u.SetForegroundWindow(hwnd)
    if u.GetForegroundWindow()!=hwnd:
        # A normal Alt key event gives Windows a user-input context for the requested window switch.
        u.keybd_event(0x12,0,0,0);u.keybd_event(0x12,0,2,0)
        u.SetForegroundWindow(hwnd)
    time.sleep(.15)

def process_birth(pid):
    handle=k.OpenProcess(0x1000,False,pid)
    if not handle:return None
    try:
        created,ended,kernel,user=W.FILETIME(),W.FILETIME(),W.FILETIME(),W.FILETIME()
        if not k.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(ended),ctypes.byref(kernel),ctypes.byref(user)):return None
        return (created.dwHighDateTime<<32)|created.dwLowDateTime
    finally:k.CloseHandle(handle)

def is_game_executable(path):
    try:
        return Path(path).samefile(GAME)
    except OSError:
        return False

def game_window():
    matches=[]
    @ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def visit(hwnd,_):
        if not u.IsWindowVisible(hwnd):return True
        pid=W.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        handle=k.OpenProcess(0x1000,False,pid.value)
        if not handle:return True
        try:
            size=W.DWORD(32768);path=ctypes.create_unicode_buffer(size.value)
            if k.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)) and is_game_executable(path.value):
                rect=W.RECT();u.GetClientRect(hwnd,ctypes.byref(rect))
                if rect.right>500 and rect.bottom>300:matches.append((int(hwnd),pid.value))
        finally:k.CloseHandle(handle)
        return True
    u.EnumWindows(visit,0)
    if len(matches)!=1:raise ValueError('Waiting for one visible New World window.')
    return matches[0]

def frame(hwnd):
    if u.GetForegroundWindow()!=hwnd:raise ValueError('Return New World to the foreground to continue login.')
    rect=W.RECT();point=W.POINT(0,0)
    u.GetClientRect(hwnd,ctypes.byref(rect));u.ClientToScreen(hwnd,ctypes.byref(point))
    image=np.array(ImageGrab.grab(bbox=(point.x,point.y,point.x+rect.right,point.y+rect.bottom),all_screens=True))
    return cv2.cvtColor(image,cv2.COLOR_RGB2BGR),(point.x,point.y)

def locate(image,name):
    path=STATE/'menu-templates'/f'{name}.png'
    if not path.is_file():return None
    template=cv2.imread(str(path))
    if template is None:return None
    height,width=image.shape[:2]
    size=read_json(STATE/'menu-templates/sizes.json').get(name)
    if not size or len(size)!=2 or min(size)<=0 or abs(width/height-size[0]/size[1])>.06:return None
    template=cv2.resize(template,None,fx=width/size[0],fy=height/size[1],interpolation=cv2.INTER_AREA)
    if template.shape[0]>height or template.shape[1]>width:return None
    score=cv2.matchTemplate(image,template,cv2.TM_SQDIFF_NORMED)
    minimum,_,point,_=cv2.minMaxLoc(score)
    if minimum>.025:return None
    # A second separate match is ambiguous; never choose one arbitrarily.
    x,y=point;tw,th=template.shape[1],template.shape[0]
    score[max(0,y-th//2):y+th//2+1,max(0,x-tw//2):x+tw//2+1]=1
    if cv2.minMaxLoc(score)[0]<=.025:return None
    return point[0]+template.shape[1]//2,point[1]+template.shape[0]//2

def ensure_session(session):
    folder=APP_DATA
    state=json.loads((folder/'draft.json').read_text(encoding='utf-8-sig'))
    if state.get('phase')!='running' or state.get('started_ms')!=session or not (folder/'dashboard-bridge.json').is_file():
        raise RuntimeError('The recording ended; login was cancelled.')

def claim_game(session,pid,expected_pid=None,expected_created=None):
    created=process_birth(pid)
    if created is None or created//10000-11644473600000 < session-2000:
        raise RuntimeError('This game process predates the recording; automatic input stopped.')
    if expected_pid is not None and (pid!=expected_pid or created!=expected_created):
        raise RuntimeError('The game process changed; automatic input stopped.')
    owner={'session_ms':session,'pid':pid,'created':created}
    if read_json(STATE/'game-owner.json')!=owner:
        save_json(STATE/'game-owner.json',owner)
    return owner

def world_entered(session):
    events=read_json(STATE/f'connection-{session}.json').get('events',[])
    entered=max((e['t_ms'] for e in events if e['kind']=='entered_world'),default=0)
    left=max((e['t_ms'] for e in events if e['kind'] in ('disconnected','eac_kick','account_warning')),default=0)
    return entered>=session and entered>left


def click(hwnd,offset,point,session):
    ensure_session(session)
    if u.GetForegroundWindow()!=hwnd:raise ValueError('Game focus changed; no click was sent.')
    prior=W.POINT();u.GetCursorPos(ctypes.byref(prior))
    def move(x,y):
        left,top,width,height=(u.GetSystemMetrics(i) for i in (76,77,78,79))
        send_input(Input(0,InputUnion(mouse=MouseInput(round((x-left)*65535/max(1,width-1)),round((y-top)*65535/max(1,height-1)),0,0xC001,0,0))))
    move(offset[0]+point[0],offset[1]+point[1])
    if u.GetForegroundWindow()!=hwnd:raise ValueError('Game focus changed; no click was sent.')
    time.sleep(.12)
    ensure_session(session)
    if u.GetForegroundWindow()!=hwnd:raise RuntimeError('Game focus changed; no click was sent.')
    actual=W.POINT();u.GetCursorPos(ctypes.byref(actual))
    if abs(actual.x-offset[0]-point[0])>3 or abs(actual.y-offset[1]-point[1])>3:
        raise RuntimeError('Windows did not place the pointer on the verified button; no click was sent.')
    send_input(Input(0,InputUnion(mouse=MouseInput(0,0,0,2,0,0))))
    time.sleep(.1)
    send_input(Input(0,InputUnion(mouse=MouseInput(0,0,0,4,0,0))))
    time.sleep(.2)
    if u.GetForegroundWindow()==hwnd:move(prior.x,prior.y)

def calibrate(screen):
    selections={'character':[('character-heading','the Character selection heading'),('character-card','only your character name and world'),('play','the Play button')],
                'disconnect':[('connection-error','the connection error heading'),('expected-eac-kick','the complete expected anti-cheat disconnect reason'),('kick-okay','the dismiss button')]}
    if screen not in selections:raise ValueError('Unknown setup screen.')
    hwnd,_=game_window();activate(hwnd)
    picture,_=frame(hwnd)
    saved={}
    for name,description in selections[screen]:
        title='Azoth setup: select '+description+'; Enter to save, C to cancel'
        x,y,w,h=map(int,cv2.selectROI(title,picture,True,False))
        cv2.destroyAllWindows()
        if w<8 or h<8:raise ValueError('Selection cancelled. Automatic return remains unchanged.')
        saved[name]=picture[y:y+h,x:x+w]
    folder=STATE/'menu-templates';folder.mkdir(parents=True,exist_ok=True)
    sizes=read_json(folder/'sizes.json')
    for name,crop in saved.items():
        okay,encoded=cv2.imencode('.png',crop)
        if not okay:raise ValueError('Could not save the selected menu region.')
        path=folder/(name+'.png');temporary=path.with_suffix('.tmp')
        with temporary.open('wb') as stream:
            stream.write(encoded.tobytes());stream.flush();os.fsync(stream.fileno())
        temporary.replace(path)
        sizes[name]=[picture.shape[1],picture.shape[0]]
    save_json(folder/'sizes.json',sizes)
    result={'state':'saved','screen':screen}
    save_json(STATE/'calibration.json',result)
    return result


def enter(session,resume=False,expected_pid=None,expected_created=None):
    deadline=time.monotonic()+180
    selected=False
    activated=False
    last_focus=0
    play_attempts=0
    continued=False
    merge_dismissed=False
    while time.monotonic()<deadline:
        ensure_session(session)
        settings=STATE/'recovery-settings.json'
        if not read_json(settings).get('enabled',False):
            raise RuntimeError('Automatic login and resume are paused.')
        try:
            hwnd,pid=game_window()
            owner=claim_game(session,pid,expected_pid,expected_created)
            expected_pid,expected_created=pid,owner['created']
            if world_entered(session):
                return {**owner,'state':'in_world'}
            if not activated or (u.GetForegroundWindow()!=hwnd and time.monotonic()-last_focus>8):
                activate(hwnd);activated=True;last_focus=time.monotonic()
            image,offset=frame(hwnd)
            if not merge_dismissed and locate(image,'worlds-merged'):
                okay=locate(image,'merge-okay')
                if okay:
                    click(hwnd,offset,okay,session)
                    time.sleep(2)
                    after,_=frame(hwnd)
                    if locate(after,'worlds-merged'):
                        raise RuntimeError('The world-merge notice did not respond. Automatic login stopped.')
                    merge_dismissed=True
                    continue
            continuation=locate(image,'continue') if not continued else None
            if continuation:
                key(hwnd,0x0D,session)
                continued=True
                time.sleep(2)
                continue
            if resume and locate(image,'connection-error') and locate(image,'expected-eac-kick'):
                okay=locate(image,'kick-okay')
                if okay:
                    key(hwnd,0x1B,session)
                    time.sleep(2)
                    after,_=frame(hwnd)
                    if locate(after,'expected-eac-kick'):
                        raise RuntimeError('The disconnect dialog did not respond. Automatic resume stopped.')
                    resume=False
                    continue
            if locate(image,'character-heading') and locate(image,'character-card'):
                if not selected:
                    click(hwnd,offset,locate(image,'character-card'),session);selected=True
                    time.sleep(1);continue
                play=locate(image,'play')
                if play:
                    click(hwnd,offset,play,session) if play_attempts==0 else key(hwnd,0x0D,session)
                    play_attempts+=1
                    time.sleep(2)
                    after,_=frame(hwnd)
                    if not locate(after,'character-heading') or not locate(after,'play'):
                        return {'state':'entering_world','character':preferences()['character'],'world':preferences()['world'],'pid':pid,'created':process_birth(pid)}
                    if play_attempts>=2:
                        raise RuntimeError('The verified Play button did not respond. Automatic login stopped.')
        except ValueError:
            pass
        time.sleep(2)
    raise ValueError('Could not verify your configured character and the Play button. Select the character manually or repeat setup.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['observe','enter','close','calibrate']);parser.add_argument('--screen',choices=['character','disconnect']);parser.add_argument('--session',type=int,default=0);parser.add_argument('--pid',type=int);parser.add_argument('--created',type=int);parser.add_argument('--resume',type=int,default=0)
    args=parser.parse_args()
    try:
        if args.action=='calibrate':result=calibrate(args.screen)
        elif args.action=='enter':result=enter(args.session,bool(args.resume),args.pid,args.created)
        else:
            hwnd,pid=game_window()
            if args.action=='close':
                if args.pid!=pid:raise ValueError('The game process changed; it was left open.')
                if args.created is not None and process_birth(pid)!=args.created:raise ValueError('This is a different game process; it was left open.')
                u.PostMessageW(hwnd,0x0010,0,0)
                for _ in range(60):
                    time.sleep(.5)
                    handle=k.OpenProcess(0x1000,False,pid)
                    if not handle:break
                    code=W.DWORD()
                    k.GetExitCodeProcess(handle,ctypes.byref(code));k.CloseHandle(handle)
                    if code.value!=259:break
                else:raise ValueError('New World did not close normally. Automatic resume stopped.')
                result={'state':'closed','pid':pid}
            else:
                image,_=frame(hwnd)
                result={'state':'observed','pid':pid,'character_screen':bool(locate(image,'character-heading')),'character':preferences()['character'] if locate(image,'character-card') else None,'play_visible':bool(locate(image,'play'))}
        print(json.dumps(result))
    except Exception as error:
        if args.action=='calibrate':save_json(STATE/'calibration.json',{'state':'needs_attention','error':str(error)})
        print(json.dumps({'state':'needs_attention','error':str(error)}));raise SystemExit(1)
