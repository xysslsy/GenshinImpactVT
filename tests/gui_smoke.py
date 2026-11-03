import ctypes, json, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['LOCALAPPDATA'] = str(Path(__file__).resolve().parents[1] / '.test-data')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from main import Main, STYLE

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = ('<html><title>test</title><body><input id="input">' + self.path + '</body></html>').encode()
        self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
server = ThreadingHTTPServer(('127.0.0.1',0), Handler); threading.Thread(target=server.serve_forever, daemon=True).start()
base = 'http://127.0.0.1:' + str(server.server_port)
ole=ctypes.OleDLL('ole32'); ole.OleInitialize(None); app=QApplication([]); app.setStyleSheet(STYLE); win=Main(Path(os.environ['LOCALAPPDATA']) / 'test')
checks={}
def check(name, condition):
    checks[name]=bool(condition); print(name, checks[name], flush=True)
def phase1():
    check('webview_ready', bool(win.browser.web and win.browser.web.CoreWebView2)); win.open_url(base+'/one')
def phase2():
    check('http_first', win.current_url.endswith('/one')); win.add_bookmark(); win.open_url(base+'/two')
def phase3():
    check('http_second', win.current_url.endswith('/two')); win.browser.back()
def phase4():
    check('back', win.address.text().endswith('/one')); win.browser.forward()
def phase5():
    check('forward', win.address.text().endswith('/two')); win.browser.reload(); win.set_topmost(True)
    check('topmost_synced', win.pin.isChecked() and win.floating.pin.isChecked())
    check('bookmark', any(row[2] == base+'/one' for row in win.store.rows('bookmarks'))); check('history', len(win.store.rows('history')) >= 2)
    check('episode_hook', bool(win.episode_keys.handle)); win.toggle_floating()
def phase6():
    check('floating_visible', win.floating.isVisible()); win.close()
for ms,fn in [(3500,phase1),(5000,phase2),(6500,phase3),(8000,phase4),(9500,phase5),(10500,phase6)]: QTimer.singleShot(ms,fn)
QTimer.singleShot(18000,app.quit)
result=app.exec(); ole.OleUninitialize(); server.shutdown(); print('RESULT',json.dumps(checks), flush=True)
sys.exit(0 if len(checks)==10 and all(checks.values()) else 1)
