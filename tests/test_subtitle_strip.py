import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QSettings
from PySide6.QtWidgets import QApplication,QWidget
from genshinimpactvt.subtitle_strip import SubtitleStrip
from genshinimpactvt.subtitles import SubtitleController
from genshinimpactvt.compass import Compass
from test_subtitle_controller import Browser


class SubtitleStripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_plain_text_and_disabled_state(self):
        strip=SubtitleStrip();strip.set_recognition_enabled(True)
        text='<b>往东北走</b>'
        strip.set_caption(text,'platform')
        self.assertEqual(strip.text.text(),text)
        self.assertEqual(strip.text.textFormat(),Qt.TextFormat.PlainText)
        self.assertEqual(strip.source.text(),'B站 AI/CC')
        strip.set_recognition_enabled(False)
        self.assertFalse(strip.current);self.assertFalse(strip.source.text())
        strip.close()

    def test_controller_deduplicates_and_clears_on_navigation(self):
        with tempfile.TemporaryDirectory() as temp:
            parent=QWidget();compass=Compass();strip=SubtitleStrip()
            settings=QSettings(str(Path(temp)/'s.ini'),QSettings.Format.IniFormat)
            controller=SubtitleController(Browser(),compass,settings,parent);controller.timer.stop()
            events=[];controller.caption_changed.connect(lambda text,source:events.append((text,source)))
            controller.caption_changed.connect(strip.set_caption)
            controller.deliver('往东北走，沿路前进','platform')
            controller.deliver('往东北走，沿路前进','platform')
            self.assertEqual(strip.current,'往东北走，沿路前进');self.assertEqual(len(events),1)
            controller.reset_timeline()
            self.assertEqual(events[-1],('',''));self.assertFalse(strip.current)
            controller.close();compass.close();strip.close();parent.close()


if __name__=='__main__':unittest.main()
