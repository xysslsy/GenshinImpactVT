"""Exercise raw registration and decoded side-button events on a local video."""
import ctypes
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['LOCALAPPDATA'] = str(Path(__file__).resolve().parents[1] / '.test-raw')
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication
from main import Main, STYLE
import genshinimpactvt.enhancements as enhancements
import genshinimpactvt.raw_mouse as raw

enhancements.on_bilibili = lambda window: True
ole = ctypes.OleDLL('ole32'); ole.OleInitialize(None)
app = QApplication([]); app.setStyleSheet(STYLE)
data_dir = Path(os.environ['LOCALAPPDATA']) / 'app'; data_dir.mkdir(parents=True, exist_ok=True)
settings = QSettings(str(data_dir / 'settings.ini'), QSettings.Format.IniFormat)
settings.setValue('mouse/mode', 'raw'); settings.setValue('mouse/enabled', True); settings.sync()
win = Main(data_dir); checks = {}
def check(name, ok): checks[name] = bool(ok); print(name, checks[name], flush=True)
def start():
    check('raw_registration', win.raw_mouse.active and not win.side_buttons.handle)
    win.browser.execute_script("document.querySelector('video').play()")
    # Simulate a successful GetRawInputData call with a correctly packed mouse record.
    packet = raw.RAWINPUT(); packet.header.type = 0; packet.header.size = ctypes.sizeof(packet); packet.mouse.buttons = 0x100
    original = raw.user32.GetRawInputData
    def fake_get(handle, command, target, length, header_size):
        ctypes.memmove(target, ctypes.byref(packet), ctypes.sizeof(packet)); return ctypes.sizeof(packet)
    try:
        raw.user32.GetRawInputData = fake_get; win.raw_mouse.handle_input(0)
    finally: raw.user32.GetRawInputData = original
    QTimer.singleShot(500, read_pause)
def read_pause():
    win._raw_test_task = win.browser.execute_script("document.querySelector('video').paused")
    QTimer.singleShot(300, finish)
def finish():
    check('decoded_xbutton2_pauses', json.loads(str(win._raw_test_task.Result)) is True)
    check('diagnostic_count', win.mouse_count == 1 and '计数 1' in win.mouse_status.text())
    win.mouse_mode.setCurrentIndex(win.mouse_mode.findData('hook'))
    check('switch_to_hook', not win.raw_mouse.active and bool(win.side_buttons.handle))
    win.mouse_mode.setCurrentIndex(win.mouse_mode.findData('raw'))
    check('switch_to_raw', win.raw_mouse.active and not win.side_buttons.handle)
    win.close()
QTimer.singleShot(5500, start); QTimer.singleShot(16000, app.quit)
app.exec(); ole.OleUninitialize(); sys.exit(0 if len(checks)==5 and all(checks.values()) else 1)
