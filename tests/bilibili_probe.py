"""Read-only public Bilibili page probe; uses an isolated browser profile."""
import ctypes
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['LOCALAPPDATA'] = str(Path(__file__).resolve().parents[1] / '.test-bilibili')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from main import Main, STYLE

ole = ctypes.OleDLL('ole32'); ole.OleInitialize(None)
app = QApplication([]); app.setStyleSheet(STYLE); win = Main(Path(os.environ['LOCALAPPDATA']) / 'app')
result = {}
def open_page(): win.open_url('https://www.bilibili.com/video/BV1RKFjzpEow/?p=2')
def inspect():
    result['url'] = win.address.text(); result['status'] = win.status.text()
    try:
        win._probe = win.browser.execute_script('''(()=>{let v=document.querySelector('video');return {video:!!v,tracks:v?v.textTracks.length:0,next:!!document.querySelector('.bpx-player-ctrl-next'),previous:!!document.querySelector('.bpx-player-ctrl-prev'),subtitles:document.querySelectorAll('.bpx-player-subtitle-panel-text, .bpx-player-subtitle-item-text').length,active:Array.from(document.querySelectorAll('[class*="video-pod"] [class*="active"], .multi-page .on, [class*="video-pod"] [class*="playing"]')).slice(0,4).map(x=>({tag:x.tagName,cls:x.className,outer:x.outerHTML.slice(0,1000)}))}})()''')
        QTimer.singleShot(500, finish)
    except Exception as exc: result['error'] = str(exc); finish()
def finish():
    try: result['page'] = json.loads(str(win._probe.Result))
    except Exception as exc: result['error'] = str(exc)
    win.media_action('previous'); QTimer.singleShot(2500, previous_done)
def previous_done():
    result['after_previous'] = win.address.text(); win.media_action('next'); QTimer.singleShot(2500, next_done)
def next_done():
    result['after_next'] = win.address.text(); print('BILIBILI', json.dumps(result, ensure_ascii=False), flush=True); win.close()
QTimer.singleShot(1500, open_page); QTimer.singleShot(14000, inspect); QTimer.singleShot(25000, app.quit)
app.exec(); ole.OleUninitialize()
