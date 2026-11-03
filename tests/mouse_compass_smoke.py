"""Test side-button hook delivery against the local test video."""
import ctypes
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['LOCALAPPDATA'] = str(Path(__file__).resolve().parents[1] / '.test-mouse')
from PySide6.QtCore import QTimer, QSettings
from PySide6.QtWidgets import QApplication
from main import Main, STYLE
import genshinimpactvt.enhancements as enhancements

enhancements.on_bilibili = lambda window: True
ole = ctypes.OleDLL('ole32'); ole.OleInitialize(None)
app = QApplication([]); app.setStyleSheet(STYLE)
test_dir = Path(os.environ['LOCALAPPDATA']) / 'app'; test_dir.mkdir(parents=True, exist_ok=True)
settings = QSettings(str(test_dir / 'settings.ini'), QSettings.Format.IniFormat); settings.setValue('mouse/mode', 'hook'); settings.sync()
win = Main(test_dir)
win.side_buttons.allow_injected = True  # production ignores injected mouse events
checks = {}
def check(name, value): checks[name] = bool(value); print(name, checks[name], flush=True)
def start():
    check('hook_installed', bool(win.side_buttons.handle))
    win.show_compass(); check('compass_visible', win.compass.isVisible() and win.compass_toggle.isChecked())
    win.browser.execute_script("(()=>{const v=document.querySelector('video');v.currentTime=1.5;v.play()})()")
    win.raise_(); win.activateWindow(); win.address.setFocus()
    QTimer.singleShot(500, pause)
def emit(button):
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    if user32.GetForegroundWindow() != int(win.winId()):
        print('foreground unavailable, did not send mouse input', flush=True); return
    user32.mouse_event(0x0080, 0, 0, button, 0)
    user32.mouse_event(0x0100, 0, 0, button, 0)
def pause():
    emit(2); QTimer.singleShot(400, check_pause)
def check_pause():
    win._mouse_test_task = win.browser.execute_script("document.querySelector('video').paused")
    QTimer.singleShot(300, rewind)
def rewind():
    check('upper_pauses', json.loads(str(win._mouse_test_task.Result)) is True)
    win.browser.execute_script("document.querySelector('video').currentTime=1.5")
    QTimer.singleShot(300, lambda: (emit(1), QTimer.singleShot(400, read_time)))
def read_time():
    win._mouse_test_task = win.browser.execute_script("document.querySelector('video').currentTime")
    QTimer.singleShot(300, finish)
def finish():
    check('lower_rewinds', json.loads(str(win._mouse_test_task.Result)) < .3)
    win.close()
QTimer.singleShot(5500, start); QTimer.singleShot(16000, app.quit)
app.exec(); ole.OleUninitialize(); sys.exit(0 if len(checks)==4 and all(checks.values()) else 1)
