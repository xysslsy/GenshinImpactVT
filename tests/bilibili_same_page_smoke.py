"""Visit the supplied public creator page in the app's normal WebView2 session.

No account identifiers, cookies, page text or private link parameters are saved.
"""
import ctypes,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtWidgets import QApplication
from main import Main,STYLE


def main():
    data=ROOT/'.test-same-page/bilibili';data.mkdir(parents=True,exist_ok=True)
    settings=QSettings(str(data/'settings.ini'),QSettings.Format.IniFormat)
    for key in ('mouse/enabled','episode_keys/enabled','subtitles/enabled','window/compact'):settings.setValue(key,False)
    settings.setValue('browser/last_url','https://space.bilibili.com/431073645');settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([]);app.setStyleSheet(STYLE)
    win=Main(data);checks={};errors=[];handled=[];probe=None;stage=0;core=None;start=time.monotonic()
    win.browser.failed.connect(errors.append)
    def observe(sender,event):handled.append(bool(event.Handled))
    def finish():
        timer.stop()
        if core is not None:core.NewWindowRequested-=observe
        win.close()
    def step():
        nonlocal stage,probe,core
        try:
            if time.monotonic()-start>55:raise TimeoutError('creator page/video link did not become ready')
            if stage==0 and win.browser.web and win.browser.web.CoreWebView2:
                core=win.browser.web.CoreWebView2;core.NewWindowRequested+=observe;stage=1
            elif stage==1 and 'space.bilibili.com/431073645' in win.address.text():
                probe=win.browser.execute_script(r"""(()=>{
                  const a=Array.from(document.links).find(a=>/^https:\/\/(www\.)?bilibili.com\/video\/BV/.test(a.href)&&a.getBoundingClientRect().width>0);
                  window.__givtJumpTest=a;return !!a;
                })()""");stage=2
            elif stage==2 and probe.IsCompleted:
                if json.loads(str(probe.Result)):
                    checks['creator_page_has_real_video_link']=True
                    probe=core.CallDevToolsProtocolMethodAsync('Runtime.evaluate',json.dumps({
                        'expression':'window.__givtJumpTest.click()','userGesture':True}));stage=3
                else:stage=1
            elif stage==3 and '/video/BV' in win.address.text():
                checks['video_opens_in_same_host']=core==win.browser.web.CoreWebView2
                checks['native_new_window_request_handled']=bool(handled) and all(handled)
                win.browser.back();stage=4
            elif stage==4 and 'space.bilibili.com/431073645' in win.address.text():
                checks['back_returns_to_creator']=True;finish()
        except Exception as exc:
            errors.append(str(exc));finish()
    timer=QTimer();timer.timeout.connect(step);timer.start(200)
    app.exec();ole.OleUninitialize()
    result={'checks':checks,'errors':errors};(data/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    return 0 if len(checks)==4 and all(checks.values()) and not errors else 1


if __name__=='__main__':sys.exit(main())
