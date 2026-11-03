"""Exercise video controls and subtitle polling on the self-contained fixture."""
import ctypes
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['LOCALAPPDATA'] = str(Path(__file__).resolve().parents[1] / '.test-guide')
from PySide6.QtCore import QTimer, QSettings
from PySide6.QtWidgets import QApplication
from main import Main, STYLE
import genshinimpactvt.enhancements as enhancements

enhancements.on_bilibili = lambda window: True  # fixture only; no remote website is impersonated
ole = ctypes.OleDLL('ole32'); ole.OleInitialize(None)
app = QApplication([]); app.setStyleSheet(STYLE)
test_dir = Path(os.environ['LOCALAPPDATA']) / 'app'; test_dir.mkdir(parents=True, exist_ok=True)
settings = QSettings(str(test_dir / 'settings.ini'), QSettings.Format.IniFormat)
settings.sync()
win = Main(test_dir)
checks = {}

def check(name, value):
    checks[name] = bool(value); print(name, checks[name], flush=True)

def start():
    win.set_compass(True)
    win.browser.execute_script("(()=>{let v=document.querySelector('video');let t=v.addTextTrack('subtitles','test','zh');t.mode='hidden';t.addCue(new VTTCue(0,2,'向东前进'));v.play()})()")

def inspect():
    check('subtitle_east', '东' in win.compass.active)
    check('episode_hook', bool(win.episode_keys.handle))
    win.media_action('pause')
    QTimer.singleShot(500, check_pause)

def check_pause():
    win._check_task = win.browser.execute_script("document.querySelector('video').paused")
    QTimer.singleShot(300, finish)

def finish():
    check('pause', json.loads(str(win._check_task.Result)) is True)
    win.toggle_immersive(); check('immersive', win.immersive and not win.centralWidget().layout().itemAt(0).widget().isVisible())
    win.toggle_immersive(); check('restore', not win.immersive and win.centralWidget().layout().itemAt(0).widget().isVisible())
    win.close()

QTimer.singleShot(5500, start); QTimer.singleShot(7000, inspect); QTimer.singleShot(15000, app.quit)
app.exec(); ole.OleUninitialize(); sys.exit(0 if len(checks) == 5 and all(checks.values()) else 1)
