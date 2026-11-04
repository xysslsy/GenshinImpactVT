"""Decode a locally recorded video, then actually seek backwards and forwards."""
import ctypes,json,multiprocessing,os,sys,time
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    data=root/'.test-ocr'/'seek';data.mkdir(parents=True,exist_ok=True);os.environ['LOCALAPPDATA']=str(data)
    from PySide6.QtCore import QTimer,QSettings
    from PySide6.QtWidgets import QApplication
    from main import Main
    settings=QSettings(str(data/'app'/'settings.ini'),QSettings.Format.IniFormat)
    for key in ('mouse/enabled','episode_keys/enabled','subtitles/enabled'):settings.setValue(key,False)
    settings.setValue('subtitles/mode','ocr');settings.setValue('browser/last_url','');settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([]);win=Main(data/'app')
    result={};stage=0;start=time.monotonic();probe=None;generation=0
    def finish():
        result['status']=win.subtitles.page.status.text();win.close()
        (data/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');app.quit()
    def step():
        nonlocal stage,probe,generation
        s=win.subtitles
        if time.monotonic()-start>45:result['timeout']=True;timer.stop();finish();return
        if stage==0 and win.browser.web and win.browser.web.CoreWebView2:
            win.browser.navigate((root/'tests'/'ocr_recorded_fixture.html').as_uri());stage=1
        elif stage==1:
            if probe is None:probe=win.browser.execute_script("document.querySelector('video')?.readyState>=2")
            elif probe.IsCompleted:
                ready=json.loads(str(probe.Result));probe=None
                if ready:
                    win.browser.execute_script("document.querySelector('video').currentTime=.5")
                    s.page.enabled.setChecked(True);stage=2
        elif stage==2 and win.compass.active=={'东'}:
            result['decoded_east']=True;generation=s.generation
            win.browser.execute_script("document.querySelector('video').currentTime=2.5");stage=3
        elif stage==3 and win.compass.active=={'北'}:
            result['forward_seek_north']=True;result['forward_invalidated']=s.generation>generation
            generation=s.generation;win.browser.execute_script("document.querySelector('video').currentTime=.5");stage=4
        elif stage==4 and win.compass.active=={'东'}:
            result['backward_seek_east']=True;result['backward_invalidated']=s.generation>generation
            timer.stop();finish()
    timer=QTimer();timer.timeout.connect(step);timer.start(200);app.exec();ole.OleUninitialize()
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return 0 if len(result)==6 and all(v for k,v in result.items() if k!='status') else 1


if __name__=='__main__':multiprocessing.freeze_support();sys.exit(main())
