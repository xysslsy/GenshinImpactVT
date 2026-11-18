import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

from genshinimpactvt.desktop_subtitle import DesktopSubtitle


class DesktopSubtitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.player = QWidget()
        self.overlay = DesktopSubtitle(self.player)

    def tearDown(self):
        self.overlay.close()
        self.player.close()

    def test_can_show_current_caption_without_showing_player(self):
        self.overlay.set_recognition_enabled(True)
        self.overlay.set_caption('向北走', 'platform')
        self.assertFalse(self.overlay.isVisible())
        self.overlay.set_enabled(True)
        self.assertTrue(self.overlay.isVisible())
        self.assertFalse(self.player.isVisible())
        self.assertTrue(self.overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(self.overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.overlay.set_enabled(False)
        self.assertFalse(self.overlay.isVisible())
        self.overlay.set_enabled(True)
        self.assertEqual(self.overlay.caption, '向北走')

    def test_fits_the_player_screen_and_clears_with_recognition(self):
        self.overlay.set_enabled(True)
        self.overlay.set_recognition_enabled(True)
        caption = '第一行字幕\n' + '向东北继续走，沿路前进。' * 18
        self.overlay.set_caption(caption, 'dom')
        area = self.player.screen().availableGeometry()
        frame = self.overlay.geometry()
        self.assertTrue(area.contains(frame))
        self.assertLessEqual(abs(frame.center().x() - area.center().x()), 1)
        self.assertEqual(area.bottom() - frame.bottom(), max(12, min(32, area.height() // 30)))
        self.assertEqual(self.overlay.caption, caption)
        self.overlay.clear()
        self.assertFalse(self.overlay.isVisible())
        self.overlay.set_caption('向东走', 'dom')
        self.overlay.set_recognition_enabled(False)
        self.assertFalse(self.overlay.isVisible())
        self.assertEqual(self.overlay.caption, '')

    def test_caption_leaves_the_background_transparent(self):
        self.overlay.set_enabled(True)
        self.overlay.set_recognition_enabled(True)
        self.overlay.set_caption('向北走', 'dom')
        image = QImage(self.overlay.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        self.overlay.render(image)
        self.assertEqual(image.pixelColor(5, image.height() // 2).alpha(), 0)
        self.assertEqual(image.pixelColor(image.width() // 2, 4).alpha(), 0)
        self.assertTrue(any(image.pixelColor(x, y).alpha() >= 240
                            for x in range(19, image.width() - 19)
                            for y in range(9, image.height() - 9)))

    def test_font_size_resizes_an_existing_caption_and_preserves_its_bottom_anchor(self):
        self.overlay.set_enabled(True)
        self.overlay.set_recognition_enabled(True)
        self.overlay.set_caption('向东北走', 'dom')
        original = self.overlay.geometry()
        self.overlay.set_font_size(44)
        larger = self.overlay.geometry()
        self.assertGreater(larger.width(), original.width())
        self.assertGreater(larger.height(), original.height())
        self.assertEqual(larger.bottom(), original.bottom())
        self.assertEqual(self.overlay.caption, '向东北走')
        self.overlay.set_font_size(100)
        self.assertEqual(self.overlay.caption_font.pixelSize(), DesktopSubtitle.MAX_FONT_SIZE)


if __name__ == '__main__':
    unittest.main()
