import ctypes, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['LOCALAPPDATA'] = str(Path(__file__).resolve().parents[1] / '.test-video')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from main import Main, STYLE
ole=ctypes.OleDLL('ole32'); ole.OleInitialize(None); app=QApplication([]); app.setStyleSheet(STYLE); win=Main(Path(os.environ['LOCALAPPDATA']) / 'app'); result={}
def start():
    try:
        win.browser.execute_script('''(()=>{const v=document.querySelector('video'); window.proof={frames:0,colors:[],times:[]}; const c=document.createElement('canvas'); c.width=16;c.height=16;let ctx=c.getContext('2d');function frame(now,meta){window.proof.frames++;window.proof.times.push(meta.mediaTime);ctx.drawImage(v,0,0,16,16);window.proof.colors.push(Array.from(ctx.getImageData(2,2,1,1).data));if(window.proof.frames<40)v.requestVideoFrameCallback(frame)};v.requestVideoFrameCallback(frame);v.play()})()''')
    except Exception as exc: print('ERROR',exc,flush=True)
def read():
    try: win._test_task=win.browser.execute_script('window.proof')
    except Exception as exc: print('ERROR',exc,flush=True); win.close(); return
    QTimer.singleShot(500,finish)
def finish():
    try:
        data=json.loads(str(win._test_task.Result)); result.update(data)
        ok=data['frames']>=5 and len({tuple(x) for x in data['colors']})>=2 and len(set(data['times']))>=5
        print('VIDEO', json.dumps({'frames':data['frames'],'unique_colors':len({tuple(x) for x in data['colors']}),'unique_times':len(set(data['times'])),'success':ok}),flush=True)
    except Exception as exc: print('ERROR',exc,flush=True)
    win.close()
QTimer.singleShot(5500,start); QTimer.singleShot(8000,read); QTimer.singleShot(16000,app.quit)
app.exec(); ole.OleUninitialize(); sys.exit(0 if result.get('frames',0)>=5 and len({tuple(x) for x in result.get('colors',[])})>=2 and len(set(result.get('times',[])))>=5 else 1)
