"""Real WebView2 video capture + real local model; isolated data, no remote page."""
import ctypes
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    data=root/'.test-ocr'/'browser';data.mkdir(parents=True,exist_ok=True)
    os.environ['LOCALAPPDATA']=str(data)
    from PySide6.QtCore import QTimer,QSettings
    from PySide6.QtWidgets import QApplication
    from main import Main,STYLE
    import genshinimpactvt.subtitles as subtitles
    original_video_image=subtitles.video_image
    capture_errors=[]
    def diagnostic_video_image(image,metadata):
        try: return original_video_image(image,metadata)
        except ValueError:
            entry={'image':[image.width(),image.height()],'rect':metadata['rect'],'viewport':metadata['viewport']}
            if entry not in capture_errors:
                capture_errors.append(entry);print('capture_bounds',entry,flush=True)
            raise
    subtitles.video_image=diagnostic_video_image
    settings=QSettings(str(data/'app'/'settings.ini'),QSettings.Format.IniFormat)
    settings.setValue('mouse/enabled',False);settings.setValue('episode_keys/enabled',False)
    settings.setValue('compass/enabled',True);settings.setValue('subtitles/enabled',True)
    settings.setValue('subtitles/mode','ocr');settings.setValue('subtitles/region','null');settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None)
    app=QApplication([]);app.setStyleSheet(STYLE);win=Main(data/'app')
    import psutil
    result={'checks':{},'latencies_ms':[],'worker_peak_rss_mb':0};start=time.monotonic();stage=0;stage_start=start
    last_samples=0
    def check(name,value):
        result['checks'][name]=bool(value);print(name,bool(value),flush=True)
    def finish():
        proc=win.subtitles._process
        result['samples']=win.subtitles.samples
        result['status']=win.subtitles.page.status.text()
        win.close()
        check('worker_released',proc is None or not getattr(proc,'_popen',None) or proc._closed or not proc.is_alive())
        (data/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        app.quit()
    def step():
        nonlocal stage,stage_start,last_samples
        service=win.subtitles;now=time.monotonic()
        if service.samples>last_samples:
            result['latencies_ms'].append(service.last_latency_ms);last_samples=service.samples
        if service._process:
            try:
                process=psutil.Process(service._process.pid)
                rss=process.memory_info().rss+sum(p.memory_info().rss for p in process.children(recursive=True))
                result['worker_peak_rss_mb']=max(result['worker_peak_rss_mb'],round(rss/1024**2,1))
            except psutil.Error: pass
        if now-start>65:
            check('finished_before_timeout',False);timer.stop();finish();return
        if stage==0 and win.browser.web and win.browser.web.CoreWebView2:
            win.browser.navigate((root/'tests'/'ocr_fixture.html').as_uri());stage=1;stage_start=now
        elif stage==1 and win.compass.active=={'东'}:
            check('hard_subtitle_east',True);check('no_dom_caption',not service._metadata['text'])
            win.resize(920,620);win.browser.execute_script("window.caption='往西南方向走'")
            stage=2;stage_start=now
        elif stage==2 and win.compass.active=={'西','南'}:
            check('resize_and_southwest',True)
            win.select(service.page_index)
            win.browser.execute_script("window.caption='捡起这个东西'");stage=3;stage_start=now
        elif stage==3 and '东西' in service.page.text.text() and not win.compass.active:
            check('non_direction_filtered',True)
            # An actual navigation must invalidate pending OCR jobs.
            generation=service.generation
            win.select(0)
            win.browser.navigate((root/'fixture.html').as_uri())
            result['generation_before_navigation']=generation;stage=4;stage_start=now
        elif stage==4 and now-stage_start>1:
            check('navigation_clears',not win.compass.active and service.generation>result['generation_before_navigation'])
            service.page.enabled.setChecked(False)
            check('disable_stops_worker',service._process is None)
            service.page.enabled.setChecked(True);service.page.mode.setCurrentIndex(service.page.mode.findData('dom'))
            win.browser.execute_script("(()=>{let v=document.querySelector('video');let t=v.addTextTrack('subtitles','test','zh');t.mode='hidden';t.addCue(new VTTCue(0,10,'向北走'));v.play()})()")
            stage=5;stage_start=now
        elif stage==5 and win.compass.active=={'北'}:
            check('dom_still_works',True);timer.stop();finish()
    timer=QTimer();timer.timeout.connect(step);timer.start(200)
    app.exec();ole.OleUninitialize()
    return 0 if len(result['checks'])==8 and all(result['checks'].values()) else 1


if __name__=='__main__':
    multiprocessing.freeze_support()
    sys.exit(main())
