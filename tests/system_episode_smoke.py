"""Test physical-style 7/8 key events with local, self-owned playlist elements."""
import ctypes
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['LOCALAPPDATA'] = str(Path(__file__).resolve().parents[1] / '.test-system-episodes')
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication
from main import Main, STYLE
import genshinimpactvt.enhancements as enhancements

enhancements.on_bilibili = lambda window: True
ole = ctypes.OleDLL('ole32'); ole.OleInitialize(None)
app = QApplication([]); app.setStyleSheet(STYLE)
data = Path(os.environ['LOCALAPPDATA']) / 'app'; data.mkdir(parents=True, exist_ok=True)
settings = QSettings(str(data / 'settings.ini'), QSettings.Format.IniFormat)
settings.setValue('episode_keys/enabled', True); settings.setValue('episode_keys/mode', 'system'); settings.sync()
win = Main(data); win.episode_keys.allow_injected = True
u = ctypes.windll.user32; u.GetForegroundWindow.restype = ctypes.c_void_p
checks = {}
def check(name, value): checks[name] = bool(value); print(name, checks[name], flush=True)
def start():
    check('system_hotkeys_registered', win.system_episode_keys.active and not win.episode_keys.handle)
    win.browser.execute_script('''(()=>{const p=document.createElement('div');p.id='playlist-test';
      for(let i=0;i<3;i++){const d=document.createElement('div');d.className='video-pod__item'+(i===1?' active':'');
      d.onclick=()=>{document.querySelectorAll('.video-pod__item').forEach(x=>x.classList.remove('active'));d.classList.add('active');document.body.dataset.selected=String(i)};p.append(d)}document.body.append(p)})()''')
    win.raise_(); win.activateWindow(); u.SetForegroundWindow(int(win.winId())); QTimer.singleShot(500, press7)
def key(vk):
    if u.GetForegroundWindow() != int(win.winId()): print('foreground unavailable', flush=True); return
    u.keybd_event(vk, 0, 0, 0); u.keybd_event(vk, 0, 2, 0)
def press7(): key(0x37); QTimer.singleShot(500, read7)
def read7(): win._episode_test = win.browser.execute_script('document.body.dataset.selected'); QTimer.singleShot(300, next_key)
def next_key():
    check('7_previous', json.loads(str(win._episode_test.Result)) == '0')
    key(0x38); QTimer.singleShot(500, read8)
def read8(): win._episode_test = win.browser.execute_script('document.body.dataset.selected'); QTimer.singleShot(300, finish)
def finish():
    check('8_next', json.loads(str(win._episode_test.Result)) == '1')
    win.close()
QTimer.singleShot(3500, start); QTimer.singleShot(15000, app.quit)
app.exec(); ole.OleUninitialize()
from genshinimpactvt.shortcuts import SystemKeys
probe = SystemKeys(None); probe.bindings = win.shortcuts.bindings
released = probe.start(); probe.stop()
check('keys_released_after_exit', released)
sys.exit(0 if len(checks)==4 and all(checks.values()) else 1)
