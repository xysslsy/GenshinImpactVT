"""Check topmost and background controls with a separate foreground window."""
import ctypes
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['LOCALAPPDATA'] = str(Path(__file__).resolve().parents[1] / '.test-background')
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from main import Main, STYLE
import genshinimpactvt.enhancements as enhancements

enhancements.on_bilibili = lambda window: True
ole = ctypes.OleDLL('ole32'); ole.OleInitialize(None)
app = QApplication([]); app.setStyleSheet(STYLE)
data = Path(os.environ['LOCALAPPDATA']) / 'app'; data.mkdir(parents=True, exist_ok=True)
settings = QSettings(str(data / 'settings.ini'), QSettings.Format.IniFormat)
settings.remove('window/topmost')  # Verify the first-run default, without changing user data.
settings.setValue('mouse/mode', 'hook')
settings.setValue('episode_keys/enabled', True)
settings.sync()
win = Main(data); win.side_buttons.allow_injected = True; win.episode_keys.allow_injected = True
other = QWidget(); other.setWindowTitle('MaBao background input test'); QVBoxLayout(other).addWidget(QLabel('Test foreground'))
checks = {}
u = ctypes.windll.user32
u.GetForegroundWindow.restype = ctypes.c_void_p
u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]; u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]; u.GetWindow.restype = ctypes.c_void_p
u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
def check(name, ok): checks[name] = bool(ok); print(name, checks[name], flush=True)
def start():
    win.browser.execute_script("""(()=>{document.querySelector('video').play();const p=document.createElement('div');for(let i=0;i<2;i++){let x=document.createElement('div');x.className='video-pod__item'+(i===1?' active':'');x.onclick=()=>document.body.dataset.previous='yes';p.append(x)}document.body.append(p)})()""")
    other.show(); other.raise_(); other.activateWindow(); u.SetForegroundWindow(int(other.winId()))
    QTimer.singleShot(700, inspect)
def inspect():
    print('episode_hook', bool(win.episode_keys.handle), flush=True)
    check('other_is_foreground', u.GetForegroundWindow() == int(other.winId()))
    check('main_topmost_style', bool(u.GetWindowLongPtrW(int(win.winId()), -20) & 0x8))
    handle = u.GetWindow(int(win.winId()), 0); found = []
    while handle and len(found) < 500:
        found.append(handle); handle = u.GetWindow(handle, 2)
    check('main_above_other', int(win.winId()) in found and int(other.winId()) in found and found.index(int(win.winId())) < found.index(int(other.winId())))
    if checks['other_is_foreground']:
        u.keybd_event(0x37, 0, 0, 0); u.keybd_event(0x37, 0, 2, 0)
    QTimer.singleShot(500, read_pause)
def read_pause():
    win._background_task = win.browser.execute_script("document.body.dataset.previous || ''")
    QTimer.singleShot(300, after_pause)
def after_pause():
    check('keyboard_previous_in_background', json.loads(str(win._background_task.Result)) == 'yes')
    print('foreground_before_mouse', u.GetForegroundWindow() == int(other.winId()), flush=True)
    if u.GetForegroundWindow() == int(other.winId()):
        u.mouse_event(0x0080, 0, 0, 2, 0); u.mouse_event(0x0100, 0, 0, 2, 0)
    QTimer.singleShot(500, read_resume)
def read_resume():
    win._background_task = win.browser.execute_script("document.querySelector('video').paused")
    QTimer.singleShot(300, finish)
def finish():
    check('mouse_pauses_in_background', json.loads(str(win._background_task.Result)) is True)
    other.close(); win.close()
QTimer.singleShot(5500, start); QTimer.singleShot(16000, app.quit)
app.exec(); ole.OleUninitialize(); sys.exit(0 if len(checks)==5 and all(checks.values()) else 1)
