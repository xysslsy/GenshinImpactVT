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

    def test_region_and_mode_survive_restart(self):
        service=self.service;service.region=(.1,.6,.8,.3);service.save_region()
        service.page.mode.setCurrentIndex(service.page.mode.findData('ocr'))
        service.page.enabled.setChecked(True);self.settings.sync()
        other=SubtitleController(self.browser,self.compass,self.settings,self.parent);other.timer.stop()
        self.assertEqual(other.region,(.1,.6,.8,.3));self.assertEqual(other.mode,'ocr');self.assertTrue(other.enabled)
        other.close()


if __name__=='__main__': unittest.main()
