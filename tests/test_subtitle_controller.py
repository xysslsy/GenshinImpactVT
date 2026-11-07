import json
import queue
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject,Signal,QSettings
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QWidget
from genshinimpactvt.compass import Compass
from genshinimpactvt.subtitles import SubtitleController,crop_region,video_image


class Browser(QObject):
    ready=Signal()
    source_changed=Signal(str)
    loading=Signal()
    web=SimpleNamespace(Source='https://www.bilibili.com/video/test')
    def execute_script(self,script): raise RuntimeError('not started')


class Task:
    IsCompleted=True
    def __init__(self,metadata): self.Result=json.dumps(metadata)


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.parent=QWidget();self.browser=Browser();self.compass=Compass()
        self.settings=QSettings(str(Path(self.temp.name)/'settings.ini'),QSettings.Format.IniFormat)
        self.service=SubtitleController(self.browser,self.compass,self.settings,self.parent)
        self.service.timer.stop();self.service.enabled=True

    def tearDown(self):
        self.service.close();self.compass.close();self.parent.close()
        del self.service,self.settings
        self.temp.cleanup()

    def test_high_dpi_video_and_roi_mapping(self):
        image=QImage(1600,1000,QImage.Format.Format_RGB32);image.fill(QColor('red'))
        meta={'rect':[100,50,600,400],'viewport':[800,500]}
        video=video_image(image,meta)
        self.assertEqual((video.width(),video.height()),(1200,800))
        crop=crop_region(video,(.1,.5,.8,.25))
        self.assertEqual((crop.width(),crop.height()),(960,200))
        with self.assertRaises(ValueError): video_image(image,{'rect':[-5,0,600,400],'viewport':[800,500]})
        rounded=video_image(image,{'rect':[0,0,800.333,500],'viewport':[800,500]})
        self.assertEqual(rounded.width(),1600)

    def test_seek_clears_and_rejects_late_worker_result(self):
        service=self.service;service.compass.set_text('向东走')
        service._identity='video';service._epoch=0;service._last_time=10;service._last_wall=time.monotonic()
        old_generation=service.generation
        meta={'id':'video','epoch':1,'time':2,'text':'','seeking':False,'ended':False}
        service._page_task=Task(meta);service._page_generation=service.generation
        service.read_page(time.monotonic())
        self.assertGreater(service.generation,old_generation);self.assertFalse(service.compass.active)
        service._replies=queue.Queue();service._worker_ready=True
        service._job=(1,time.monotonic());service._worker_busy=True
        service._replies.put(('result',1,old_generation,'向东走',100))
        service.read_replies(time.monotonic())
        self.assertFalse(service.compass.active)
        service._replies=None

    def test_ocr_failure_retains_web_subtitles(self):
        service=self.service;service.worker_error('测试模型缺失')
        self.assertTrue(service._worker_failed)
        service.deliver('向北走','dom')
        self.assertEqual(service.compass.active,{'北'})

    def test_subtitle_gaps_keep_direction_but_navigation_clears(self):
        service=self.service
        service.deliver('向东北走','platform'); service.deliver('','platform')
        service.deliver('打开宝箱','platform')
        self.assertEqual(service.compass.active,{'东','北'})
        self.assertTrue(service.compass.expiry.isActive())
        service.reset_timeline()
        self.assertFalse(service.compass.active)

    def test_timed_out_page_task_does_not_block_future_reads(self):
        service=self.service
        service._page_task=SimpleNamespace(IsCompleted=False);service._page_started=0
        service.read_page(10)
        self.assertIsNone(service._page_task)

    def test_loader_reset_immediately_clears_previous_direction(self):
        self.service.mode='auto';self.service.deliver('向北走','platform')
        self.assertEqual(self.compass.active,{'北'})
        self.service.native_feed.reset()
        self.assertFalse(self.compass.active);self.assertEqual(self.service._caption_state,('',''))

    def test_region_and_mode_survive_restart(self):
        service=self.service;service.region=(.1,.6,.8,.3);service.save_region()
        service.page.auto_on_video.setChecked(False)
        service.page.mode.setCurrentIndex(service.page.mode.findData('ocr'))
        service.page.enabled.setChecked(True);self.settings.sync()
        other=SubtitleController(self.browser,self.compass,self.settings,self.parent);other.timer.stop()
        self.assertEqual(other.region,(.1,.6,.8,.3));self.assertEqual(other.mode,'ocr');self.assertTrue(other.enabled)
        other.close()

    def test_startup_overrides_saved_manual_mode_by_default(self):
        self.settings.setValue('subtitles/mode','dom');self.settings.setValue('subtitles/enabled',False)
        other=SubtitleController(self.browser,self.compass,self.settings,self.parent)
        self.assertEqual(other.mode,'auto');self.assertTrue(other.enabled)
        self.assertTrue(other.native_feed.enabled);other.close()

    def test_manual_retry_enables_auto_even_when_disabled_in_dom_mode(self):
        s=self.service;s.page.mode.setCurrentIndex(s.page.mode.findData('dom'));s.page.enabled.setChecked(False)
        s.refresh_subtitles()
        self.assertTrue(s.enabled);self.assertEqual(s.mode,'auto');self.assertTrue(s.native_feed.enabled)
        self.assertTrue(s.timer.isActive())

    def test_new_video_rearms_auto_but_tracking_change_does_not(self):
        s=self.service;url='https://www.bilibili.com/video/BV1PyxQ6sEbH/?p=6'
        s.on_source_changed(url);s.page.mode.setCurrentIndex(s.page.mode.findData('dom'))
        s.on_source_changed(url+'&spm_id_from=test');self.assertEqual(s.mode,'dom')
        s.page.enabled.setChecked(False);s.on_source_changed(url.replace('p=6','p=7'))
        self.assertEqual(s.mode,'auto');self.assertTrue(s.enabled)

    def test_media_cid_change_rearms_auto_even_without_url_change(self):
        s=self.service;self.browser.web=SimpleNamespace(Source='https://www.bilibili.com/video/BV1PyxQ6sEbH/?p=6')
        s._follow_media_key=('doc','33');s.page.mode.setCurrentIndex(s.page.mode.findData('dom'))
        meta={'id':'video','document':'doc','media':'v','src':'blob:v','player_cid':'44','duration':100,'ready':4,
              'epoch':0,'time':1,'text':'','seeking':False,'ended':False,'paused':True}
        s._page_task=Task(meta);s._page_generation=s.generation
        s.read_page(time.monotonic());self.assertEqual(s.mode,'auto')



if __name__=='__main__': unittest.main()
