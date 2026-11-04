"""Read only the supplied video's normal caption data using the app's session.

Uses isolated application settings; the existing WebView2 session is used normally.
No cookies/account identifiers/caption URLs or full subtitles are exported.
"""
import ctypes,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OVERLAY_PROBE = """(() => {
 const h=document.getElementById('genshinimpactvt-caption-overlay'),v=document.querySelector('video');
 if(!h||!v)return false;
 const r=v.getBoundingClientRect(),b=h.getBoundingClientRect();
 return !!h.shadowRoot.querySelector('.caption').textContent&&b.height>100&&
   b.top>=Math.max(0,r.top)-2&&b.bottom<=r.bottom+2&&
   getComputedStyle(h).backgroundColor==='rgba(0, 0, 0, 0)'&&getComputedStyle(h).pointerEvents==='none';
})()"""


def main():
    from PySide6.QtCore import QTimer,QSettings
    from PySide6.QtWidgets import QApplication
    from main import Main
    from genshinimpactvt.subtitle_text import directions
    data=ROOT/'.test-bilibili-light'/'native';data.mkdir(parents=True,exist_ok=True)
    settings=QSettings(str(data/'settings.ini'),QSettings.Format.IniFormat)
    for key in ('mouse/enabled','episode_keys/enabled'):settings.setValue(key,False)
    settings.setValue('subtitles/enabled',True);settings.setValue('subtitles/mode','auto')
    settings.setValue('browser/last_url','https://www.bilibili.com/video/BV1CMHQzsEJV/?p=3');settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None);app=QApplication([])
    start=time.monotonic();window=Main(data);result={'checks':{}};stage=0;last_message='';target=set();diagnosed=False
    probe=None;initial_frame=None;play_start=0
    window.browser.ready.connect(lambda:result.update(browser_ready_seconds=round(time.monotonic()-start,2)))
    def finish():
        s=window.subtitles
        result.update(status=s.page.status.text(),caption_count=len(s.native_feed.timeline.cues),
                      ocr_process_started=s._process is not None,
                      heavy_modules_loaded=[name for name in ('rapidocr','onnxruntime','cv2','numpy') if name in sys.modules])
        window.close();app.quit()
        (data/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True),flush=True)
    def step():
        nonlocal stage,last_message,target,diagnosed,probe,initial_frame,play_start
        s=window.subtitles;feed=s.native_feed
        if feed.message!=last_message:print('feed',feed.message.encode('unicode_escape').decode(),flush=True);last_message=feed.message
        if feed._records and not diagnosed:
            from urllib.parse import urlsplit
            for record in feed._records.values():
                for row in record.get('data',{}).get('subtitle',{}).get('subtitles',[]):
                    url=row.get('subtitle_url','');p=urlsplit('https:'+url if url.startswith('//') else url)
                    print('track_format',{'language':row.get('lan'),'url_length':len(url),'scheme':p.scheme,'host':p.hostname,'path_prefix':p.path.split('/')[:3]},flush=True)
            diagnosed=True
        if time.monotonic()-start>75:result['timeout']=True;timer.stop();finish();return
        if stage==0 and feed.timeline.cues:
            result['checks']['actual_platform_captions']=True
            for begin,end,text in feed.timeline.cues:
                target=directions(text)
                if target:
                    result['direction_test_time']=begin+.05
                    window.browser.execute_script('(()=>{let v=document.querySelector("video");v.pause();v.currentTime='+json.dumps(begin+.05)+'})()')
                    stage=1;break
            else:result['no_direction_cue']=True;timer.stop();finish()
        elif stage==1 and window.compass.active==target:
            result['checks']['native_caption_direction']=True
            result['checks']['live_overlay_caption']=bool(window.subtitle_overlay.current) and directions(window.subtitle_overlay.current)==target
            probe=window.browser.execute_script(OVERLAY_PROBE);stage=11
        elif stage==11 and probe.IsCompleted:
            result['checks']['full_page_visible_transparent_overlay']=json.loads(str(probe.Result)) is True
            s.open_official_player();stage=2
        elif stage==2 and 'player.bilibili.com/' in window.address.text() and feed.timeline.cues and feed.video_key[1]=='32294243227':
            window.browser.execute_script('(()=>{let v=document.querySelector("video");v.pause();v.currentTime='+json.dumps(result['direction_test_time'])+'})()')
            stage=3
        elif stage==3 and window.compass.active==target:
            result['checks']['official_player_captions']=True
            probe=window.browser.execute_script(OVERLAY_PROBE);stage=12
        elif stage==12 and probe.IsCompleted:
            result['checks']['official_player_visible_transparent_overlay']=json.loads(str(probe.Result)) is True
            window.media_action('next');stage=4
        elif stage==4 and 'p=4' in window.address.text() and feed.timeline.cues and feed.video_key[1]!='32294243227':
            result['checks']['official_player_next']=True;window.media_action('previous');stage=5
        elif stage==5 and 'p=3' in window.address.text() and feed.timeline.cues and feed.video_key[1]=='32294243227' and s._metadata and s._metadata['ready']>=2:
            result['checks']['official_player_previous']=True
            probe=window.browser.execute_script('(()=>{let v=document.querySelector("video");v.pause();return {time:v.currentTime,frames:v.getVideoPlaybackQuality().totalVideoFrames}})()')
            stage=6
        elif stage==6 and probe.IsCompleted:
            initial_frame=json.loads(str(probe.Result));window.media_action('pause');play_start=time.monotonic();stage=7
        elif stage==7 and time.monotonic()-play_start>2.5:
            probe=window.browser.execute_script('(()=>{let v=document.querySelector("video");return {time:v.currentTime,frames:v.getVideoPlaybackQuality().totalVideoFrames}})()')
            stage=8
        elif stage==8 and probe.IsCompleted:
            frame=json.loads(str(probe.Result));result['playback_observation']={'seconds_advanced':frame['time']-initial_frame['time'],'decoded_frames_added':frame['frames']-initial_frame['frames']}
            result['checks']['official_video_advances_and_decodes']=frame['time']>initial_frame['time']+.5 and frame['frames']>initial_frame['frames']
            result['checks']['no_ocr_worker']=s._process is None
            timer.stop();finish()
    timer=QTimer();timer.timeout.connect(step);timer.start(200)
    app.exec();ole.OleUninitialize()
    return 0 if len(result['checks'])==10 and all(result['checks'].values()) else 1


if __name__=='__main__':sys.exit(main())
