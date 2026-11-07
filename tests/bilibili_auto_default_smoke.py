"""The user's reported P6: default auto, manual retry recovery and three attempts.

Uses normal WebView2 session; exports only counts/boolean checks, no account data.
"""
import ctypes,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QTimer,QSettings
from PySide6.QtWidgets import QApplication
from main import Main

def main():
    data=ROOT/'.test-bilibili-light/auto-default';data.mkdir(parents=True,exist_ok=True)
    settings=QSettings(str(data/'settings.ini'),QSettings.Format.IniFormat);settings.clear()
    settings.setValue('mouse/enabled',False);settings.setValue('episode_keys/enabled',False)
    settings.setValue('subtitles/enabled',False);settings.setValue('subtitles/mode','dom')
    base='https://www.bilibili.com/video/BV1PyxQ6sEbH/'
    settings.setValue('browser/last_url',base+'?p=6');settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([]);win=Main(data)
    service=win.subtitles;feed=service.native_feed;checks={};errors=[];reloads=0;inject={'left':0}
    original=win.browser.execute_script
    def execute(script):
        if 'const token =' in script and inject['left']:
            inject['left']-=1;raise RuntimeError('Synthetic transient read failure')
        return original(script)
    win.browser.execute_script=execute
    original_reload=win.browser.reload
    def reload():
        nonlocal reloads
        reloads+=1;return original_reload()
    win.browser.reload=reload
    def check(name,value):checks[name]=bool(value);print(name,bool(value),flush=True)
    def delay(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:yield
    def ready(page):
        deadline=time.monotonic()+70
        while not (feed.timeline.cues and feed._loaded_page and feed._loaded_page[1]==page):
            if time.monotonic()>deadline:raise TimeoutError(feed.message)
            yield
    def js(script):
        task=original(script)
        while not task.IsCompleted:yield
        return json.loads(str(task.Result))
    def steps():
        check('startup_overrides_old_dom_disabled_settings',service.mode=='auto' and service.enabled and service.auto_on_video)
        yield from ready(6)
        check('reported_p6_loads_without_click',feed.video_key[0]=='BV1PyxQ6sEbH')
        check('p6_live_media_cid_matches',not feed._context['player_cid'] or feed._context['player_cid']==feed.video_key[1])
        yield from js("document.querySelector('video').pause();true")
        before=yield from js("(()=>{let v=document.querySelector('video');return {id:v.__givtId,time:v.currentTime}})()")
        service.page.mode.setCurrentIndex(service.page.mode.findData('dom'));service.page.enabled.setChecked(False)
        service.page.refresh.click();yield from ready(6)
        after=yield from js("(()=>{let v=document.querySelector('video');return {id:v.__givtId,time:v.currentTime}})()")
        check('button_switches_manual_disabled_back_to_auto',service.mode=='auto' and service.enabled)
        check('button_preserves_playback_instance',before['id']==after['id'] and abs(before['time']-after['time'])<.25 and reloads==0)
        service.page.mode.setCurrentIndex(service.page.mode.findData('dom'));service.page.enabled.setChecked(False)
        inject['left']=2;win.open_url(base+'?p=5');yield from ready(5)
        check('new_part_forces_auto',service.mode=='auto' and service.enabled)
        check('two_failures_then_third_attempt_succeeds',inject['left']==0 and feed._attempts==3)
        expected=list(feed.timeline.cues)
        check('p5_gameplay_content_not_hotpot',len(expected)>250 and
              sum(any(w in row[2] for w in ('宝箱','传送','锚点','神瞳','怪物')) for row in expected)>10 and
              not any('火锅' in row[2] for row in expected))
        for _ in range(3):
            service.page.refresh.click();yield from ready(5)
            check('p5_repeated_refresh_keeps_exact_content',feed.timeline.cues==expected and feed.video_key[1]=='43324604601')
        print('p5_content_checks',{'count':len(expected),'game_lines':sum(any(w in r[2] for w in ('宝箱','传送','锚点','神瞳','怪物')) for r in expected)},flush=True)
        yield from delay(.5);check('stops_after_verified_success',not feed.timer.isActive())
        win.open_url(base+'?p=6');yield from ready(6)
        check('return_p6_automatically_recovers',feed.video_key[0]=='BV1PyxQ6sEbH')
        check('never_reloads_video_for_captions',reloads==0)
        print('provided_p6_caption_count',len(feed.timeline.cues),flush=True)
    it=steps();started=time.monotonic()
    def tick():
        try:
            if time.monotonic()-started>200:raise TimeoutError('auto mode smoke timeout')
            next(it);return
        except StopIteration:pass
        except Exception as exc:errors.append(str(exc));print(errors[-1],flush=True)
        timer.stop();win.close()
    timer=QTimer();timer.timeout.connect(tick);timer.start(80);app.exec();ole.OleUninitialize()
    result={'checks':checks,'errors':errors};(data/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return 0 if len(checks)==12 and all(checks.values()) and not errors else 1
if __name__=='__main__':sys.exit(main())
