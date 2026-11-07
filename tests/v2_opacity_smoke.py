"""Real HWND alpha and screen-pixel composition, using only our own test windows."""
import ctypes,json,os,sys,time
from ctypes import wintypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
DATA=ROOT/'.test-v2/opacity';DATA.mkdir(parents=True,exist_ok=True);os.environ['LOCALAPPDATA']=str(DATA)
from PySide6.QtCore import QSettings,QTimer,Qt
from PySide6.QtWidgets import QApplication,QWidget
from main import Main

def main():
    settings=QSettings(str(DATA/'app/settings.ini'),QSettings.Format.IniFormat);settings.clear()
    for key in ('subtitles/enabled','mouse/enabled','episode_keys/enabled'):settings.setValue(key,False)
    settings.sync();ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([])
    background=QWidget(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
    background.setStyleSheet('background:rgb(0,0,255)');background.setGeometry(40,40,1200,850);background.show()
    win=Main(DATA/'app');win.move(80,80);checks={};errors=[]
    u=ctypes.WinDLL('user32');g=ctypes.WinDLL('gdi32')
    u.GetDC.argtypes=[wintypes.HWND];u.GetDC.restype=wintypes.HDC
    u.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
    g.GetPixel.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int];g.GetPixel.restype=wintypes.DWORD
    u.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    u.GetLayeredWindowAttributes.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(ctypes.c_ubyte),ctypes.POINTER(wintypes.DWORD)]
    u.GetForegroundWindow.restype=wintypes.HWND;u.SetForegroundWindow.argtypes=[wintypes.HWND]
    def check(name,value):checks[name]=bool(value);print(name,bool(value),flush=True)
    def delay(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:yield
    def js(script):
        task=win.browser.execute_script(script)
        while not task.IsCompleted:yield
        return json.loads(str(task.Result))
    def pixel(position=None):
        rect=wintypes.RECT();u.GetWindowRect(win.browser._handle,ctypes.byref(rect))
        dc=u.GetDC(None)
        x,y=(rect.left+8,rect.top+8) if position is None else (rect.left+round(position[0]*(rect.right-rect.left)),rect.top+round(position[1]*(rect.bottom-rect.top)))
        try:color=g.GetPixel(dc,x,y)
        finally:u.ReleaseDC(None,dc)
        return (color&255,(color>>8)&255,(color>>16)&255)
    def press(key):
        win.raise_();win.activateWindow();u.SetForegroundWindow(int(win.winId()));yield from delay(.2)
        if u.GetForegroundWindow()==int(win.winId()):
            u.keybd_event(key,0,0,0);u.keybd_event(key,0,2,0)
        else:
            # Do not send any keys to the user's foreground program.
            from unittest.mock import patch
            from genshinimpactvt.episode_keys import KeyData
            event=KeyData(key,0,0,0,0)
            with patch('genshinimpactvt.shortcuts.user32.GetAsyncKeyState',return_value=0),patch('genshinimpactvt.shortcuts.user32.CallNextHookEx',return_value=0):
                win.episode_keys._hook(0,0x100,ctypes.addressof(event));win.episode_keys._hook(0,0x101,ctypes.addressof(event))
            print('key_input_mode synthetic_hook_callback',flush=True)
        yield from delay(.2)
    def steps():
        yield from delay(4)
        hwnd=int(win.winId());browser=win.browser._handle
        yield from js("document.documentElement.style.background='red';document.body.style.background='red';true")
        position=yield from js("(()=>{const v=document.querySelector('video');v.pause();v.currentTime=.5;const r=v.getBoundingClientRect();return [(r.x+r.width*.5)/innerWidth,(r.y+r.height*.25)/innerHeight]})()")
        win.raise_();yield from delay(.4);before=pixel();video_before=pixel(position)
        win.window_opacity.set_percent(50);yield from delay(.5);after=pixel();video_after=pixel(position)
        alpha=ctypes.c_ubyte();key=wintypes.DWORD();flags=wintypes.DWORD()
        ok=u.GetLayeredWindowAttributes(hwnd,ctypes.byref(key),ctypes.byref(alpha),ctypes.byref(flags))
        check('native_alpha_is_half',ok and 120<=alpha.value<=135)
        print('own_test_pixels',{'opaque':before,'half':after},flush=True)
        check('browser_surface_blends_with_background',before[0]>220 and before[2]<40 and 85<after[0]<180 and 85<after[2]<180)
        expected=(video_before[0]/2,video_before[1]/2,video_before[2]/2+127.5)
        check('video_pixels_also_blend',all(abs(value-target)<18 for value,target in zip(video_after,expected)))
        check('qt_and_webview_handles_unchanged',int(win.winId())==hwnd and win.browser._handle==browser)
        win.episode_toggle.setChecked(True);win.episode_keys.allow_injected=True
        yield from press(0x71);check('F2_decreases',win.window_opacity.percent==40)
        yield from press(0x72);check('F3_increases',win.window_opacity.percent==50)
        yield from press(0x73);check('F4_resets',win.window_opacity.percent==100)
        for _ in range(10):win.media_action('opacity_down')
        check('minimum_is_visible',win.window_opacity.percent==20)
        win.media_action('opacity_reset');check('reset_restores_opaque',win.window_opacity.percent==100)
        win.window_opacity.set_percent(70);win.settings.sync()
        check('settings_and_slider_sync',settings.value('window/opacity_percent',type=int)==70 and win.opacity_slider.value()==70)
        yield from js("(()=>{window.framesSeen=0;const v=document.querySelector('video');function observed(){window.framesSeen++;if(window.framesSeen<15)v.requestVideoFrameCallback(observed)}v.requestVideoFrameCallback(observed);v.play();return true})()")
        yield from delay(1.5)
        check('transparent_video_still_decodes',(yield from js('window.framesSeen'))>=5)
    it=steps();start=time.monotonic()
    def tick():
        try:
            if time.monotonic()-start>25:raise TimeoutError('Opacity smoke timeout')
            next(it);return
        except StopIteration:pass
        except Exception as exc:errors.append(str(exc));print(errors[-1],flush=True)
        timer.stop();background.close();win.close()
    timer=QTimer();timer.timeout.connect(tick);timer.start(50);app.exec();ole.OleUninitialize()
    result={'checks':checks,'errors':errors};(DATA/'result.json').write_text(json.dumps(result),encoding='utf-8')
    return 0 if len(checks)==11 and all(checks.values()) and not errors else 1
if __name__=='__main__':sys.exit(main())
