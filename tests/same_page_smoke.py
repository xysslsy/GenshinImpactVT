"""Real WebView2: target=_blank, named windows and window.open stay in one host."""
import ctypes
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
DATA=ROOT/'.test-same-page';DATA.mkdir(exist_ok=True);os.environ['LOCALAPPDATA']=str(DATA)
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtWidgets import QApplication
from main import Main,STYLE


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body=b'''<!doctype html><title>local navigation fixture</title>
          <a id="blank" href="/blank" target="_blank">blank</a>
          <a id="named" href="/named" target="guide">named</a>
          <button id="popup" onclick="window.open('/popup','_blank')">popup</button>'''
        self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(server.server_port)
    settings=QSettings(str(DATA/'app/settings.ini'),QSettings.Format.IniFormat)
    for key in ('mouse/enabled','episode_keys/enabled','subtitles/enabled','window/compact'):settings.setValue(key,False)
    settings.setValue('browser/last_url',base+'/start');settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([]);app.setStyleSheet(STYLE)
    win=Main(DATA/'app');checks={};errors=[];handled=[]
    win.browser.failed.connect(errors.append)

    def until(condition):
        deadline=time.monotonic()+12
        while not condition():
            if time.monotonic()>deadline:raise TimeoutError('navigation wait timed out')
            yield

    def steps():
        yield from until(lambda:win.current_url==base+'/start')
        core=win.browser.web.CoreWebView2;handle=win.browser._handle
        def observe(sender,event):handled.append(bool(event.Handled))
        core.NewWindowRequested+=observe
        for element,path in [('blank','/blank'),('named','/named'),('popup','/popup')]:
            task=core.CallDevToolsProtocolMethodAsync('Runtime.evaluate',json.dumps({
                'expression':f'document.getElementById({json.dumps(element)}).click()', 'userGesture':True}))
            yield from until(lambda:task.IsCompleted)
            yield from until(lambda:win.current_url==base+path)
            checks[element+'_same_host']=core==win.browser.web.CoreWebView2 and handle==win.browser._handle
        win.browser.back();yield from until(lambda:win.current_url==base+'/named');checks['back']=True
        win.browser.forward();yield from until(lambda:win.current_url==base+'/popup');checks['forward']=True
        checks['address_and_history']=win.address.text()==base+'/popup' and len(win.store.rows('history'))>=4
        checks['all_requests_handled']=handled==[True,True,True]
        checks['uninstall_entry_in_source_disabled']=not win.uninstall_button.isEnabled()
        core.NewWindowRequested-=observe

    iterator=steps();start=time.monotonic()
    def tick():
        try:
            if time.monotonic()-start>50:raise TimeoutError('overall timeout')
            next(iterator);return
        except StopIteration:pass
        except Exception as exc:errors.append(str(exc))
        timer.stop();win.close()
    timer=QTimer();timer.timeout.connect(tick);timer.start(50)
    app.exec();ole.OleUninitialize();server.shutdown()
    result={'checks':checks,'errors':errors}
    (DATA/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
    return 0 if len(checks)==8 and all(checks.values()) and not errors else 1


if __name__=='__main__':sys.exit(main())
