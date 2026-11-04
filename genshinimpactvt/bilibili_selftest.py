"""Explicit opt-in packaged test, using normal page access only."""
import json
import sys
from PySide6.QtCore import QTimer
from .subtitle_text import directions


def setup_test(window,result,url,finish):
    result['native_subtitles']=False
    service=window.subtitles
    service.page.mode.setCurrentIndex(service.page.mode.findData('auto'))
    service.page.enabled.setChecked(True)
    service.page.show_compass.click()
    window.episode_toggle.setChecked(False);window.mouse_toggle.setChecked(False)
    window.browser.ready.connect(lambda:QTimer.singleShot(400,lambda:window.open_url(url)))
    state={'target':None}
    timer=QTimer(window)
    def poll():
        cues=service.native_feed.timeline.cues
        if not cues:return
        if state['target'] is None:
            for start,end,text in cues:
                target=directions(text)
                if target:
                    state['target']=target
                    window.browser.execute_script('(()=>{let v=document.querySelector("video");v.pause();v.currentTime='+json.dumps(start+.05)+'})()')
                    break
        elif window.compass.active==state['target']:
            result['native_subtitles']=True;result['caption_count']=len(cues)
            result['ocr_worker']=service._process is not None
            result['heavy_modules_loaded']=[name for name in ('rapidocr','onnxruntime','cv2','numpy') if name in sys.modules]
            timer.stop();finish()
    timer.timeout.connect(poll);timer.start(200)
