"""Normal logged-in WebView2 session, delayed enable and recovery without reload.

No credentials, subtitle URLs, account fields or full captions are written to disk.
"""
import ctypes,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QTimer,QSettings
from PySide6.QtWidgets import QApplication
from main import Main
from genshinimpactvt.bilibili_subtitles import official_player_url


def main():
    data=ROOT/'.test-bilibili-light/recovery';data.mkdir(parents=True,exist_ok=True)
    settings=QSettings(str(data/'settings.ini'),QSettings.Format.IniFormat)
    for key in ('episode_keys/enabled','mouse/enabled','subtitles/enabled'):settings.setValue(key,False)
    settings.setValue('subtitles/mode','auto');settings.setValue('window/compact',False)
    settings.setValue('subtitles/auto_on_video',False)  # This test deliberately exercises late manual enable.
    base='https://www.bilibili.com/video/BV1CMHQzsEJV/'
    settings.setValue('browser/last_url',base+'?p=3');settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([]);win=Main(data)
    service=win.subtitles;feed=service.native_feed;checks={};errors=[]
    # Deliberately miss response observation to reproduce enabling after metadata has arrived.
    feed.update_subscription=lambda:None
    original_script=win.browser.execute_script;original_reload=win.browser.reload
    injected=0;reloads=0
    def execute(script):
        nonlocal injected
        if 'const token =' in script and not injected:
            injected+=1;raise RuntimeError('Synthetic first request failure')
        return original_script(script)
    win.browser.execute_script=execute
    def reload():
        nonlocal reloads
        reloads+=1;return original_reload()
    win.browser.reload=reload
    def check(name,value):checks[name]=bool(value);print(name,bool(value),flush=True)
    def delay(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:yield
    def js(script):
        task=original_script(script);deadline=time.monotonic()+10
        while not task.IsCompleted:
            if time.monotonic()>deadline:raise TimeoutError('WebView2 task')
            yield
        return json.loads(str(task.Result))
    def ready():
        deadline=time.monotonic()+55
        while not feed.timeline.cues:
            if time.monotonic()>deadline:raise TimeoutError('Captions: '+feed.message)
            yield
    def steps():
        yield from delay(9)
        check('disabled_no_recovery_requests',feed._attempts==0 and not feed._subscribed)
        service.page.enabled.setChecked(True)
        yield from ready()
        check('late_enable_without_refresh',bool(feed.timeline.cues) and reloads==0)
        check('transient_failure_automatically_retried',injected==1 and feed._attempts>=2)
        key3=feed.video_key;count3=len(feed.timeline.cues)
        check('provided_part_has_complete_caption_count',count3>=250)
        yield from js("document.querySelector('video').pause();true")
        before=yield from js("(()=>{let v=document.querySelector('video');return {id:v.__givtId,time:v.currentTime}})()")
        service.refresh_subtitles();yield from ready()
        after=yield from js("(()=>{let v=document.querySelector('video');return {id:v.__givtId,time:v.currentTime}})()")
        check('manual_retry_keeps_video_and_position',reloads==0 and before['id']==after['id'] and abs(before['time']-after['time'])<.25)
        win.open_url(base+'?p=4');yield from ready()
        check('new_part_automatically_loads',feed.video_key[1]!=key3[1] and feed._loaded_page[1]==4)
        win.open_url(base+'?p=3');yield from ready()
        print('return_part_observation',{'initial_cid':key3[1],'return_cid':feed.video_key[1],'initial_cues':count3,'return_cues':len(feed.timeline.cues),'part':feed._loaded_page[1] if feed._loaded_page else None},flush=True)
        check('return_to_previous_part_automatically_loads',feed.video_key==key3 and feed._loaded_page[1]==3 and len(feed.timeline.cues)==count3)
        counts=[]
        for _ in range(2):
            service.refresh_subtitles();yield from ready();counts.append(len(feed.timeline.cues))
        check('repeated_retry_keeps_complete_caption_count',all(count==count3 for count in counts))
        win.open_url(official_player_url(key3[0],3,key3[1]));yield from ready()
        check('official_player_recovers_without_observer',feed.video_key==key3 and bool(feed.timeline.cues))
        yield from delay(.5)
        check('recovery_timer_stops_after_success',not feed.timer.isActive())
        check('no_heavy_inference_loaded',service._process is None and not any(m in sys.modules for m in ('onnxruntime','rapidocr','cv2','numpy')))
        check('zero_page_reloads',reloads==0)
    iterator=steps();start=time.monotonic()
    def tick():
        try:
            if time.monotonic()-start>165:raise TimeoutError('Overall test timeout')
            next(iterator);return
        except StopIteration:pass
        except Exception as exc:errors.append(type(exc).__name__+': '+str(exc));print(errors[-1],flush=True)
        timer.stop();win.close()
    timer=QTimer();timer.timeout.connect(tick);timer.start(100)
    app.exec();ole.OleUninitialize()
    result={'checks':checks,'errors':errors};(data/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return 0 if len(checks)==12 and all(checks.values()) and not errors else 1


if __name__=='__main__':sys.exit(main())
