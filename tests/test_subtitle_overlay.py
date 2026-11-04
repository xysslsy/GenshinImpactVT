import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget
from genshinimpactvt.subtitle_overlay import SubtitleOverlay
from genshinimpactvt.subtitles import SubtitleController
from genshinimpactvt.compass import Compass
from test_subtitle_controller import Browser


class SubtitleOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_disabled_hidden_and_escaped_caption(self):
        browser = Browser()
        scripts = []
        browser.execute_script = scripts.append
        overlay = SubtitleOverlay(browser)
        overlay.set_caption('disabled', 'platform')
        self.assertFalse(overlay.current)
        overlay.set_recognition_enabled(True)
        text = '<img src=x onerror=alert(1)>\n"往东北走"'
        overlay.set_caption(text, 'platform')
        self.assertEqual(overlay.current, text)
        self.assertIn('const text = ' + json.dumps(text, ensure_ascii=True), scripts[-1])
        overlay.set_visible(False)
        self.assertIn('const text = "";', scripts[-1])
        self.assertEqual(overlay.current, text)
        overlay.set_visible(True)
        self.assertIn(json.dumps(text, ensure_ascii=True), scripts[-1])
        overlay.set_recognition_enabled(False)
        self.assertFalse(overlay.current)
        self.assertFalse(overlay.source)

    def test_loading_clears_and_unready_browser_is_safe(self):
        browser = Browser()
        overlay = SubtitleOverlay(browser)
        overlay.set_recognition_enabled(True)
        overlay.set_caption('向东走', 'dom')
        self.assertTrue(overlay.last_error)
        browser.loading.emit()
        self.assertFalse(overlay.current)

    def test_controller_deduplicates_and_clears_on_navigation(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = QWidget()
            compass = Compass()
            browser = Browser()
            overlay = SubtitleOverlay(browser)
            overlay.set_recognition_enabled(True)
            settings = QSettings(str(Path(temp)/'s.ini'), QSettings.Format.IniFormat)
            controller = SubtitleController(browser, compass, settings, parent)
            controller.timer.stop()
            events = []
            controller.caption_changed.connect(lambda *args: events.append(args))
            controller.caption_changed.connect(overlay.set_caption)
            controller.deliver('往东北走，沿路前进', 'platform')
            controller.deliver('往东北走，沿路前进', 'platform')
            self.assertEqual(overlay.current, '往东北走，沿路前进')
            self.assertEqual(len(events), 1)
            controller.reset_timeline()
            self.assertEqual(events[-1], ('', ''))
            self.assertFalse(overlay.current)
            controller.close()
            compass.close()
            parent.close()


if __name__ == '__main__':
    unittest.main()
