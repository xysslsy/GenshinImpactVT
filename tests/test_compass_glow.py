import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QAbstractAnimation,QPoint
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from genshinimpactvt.compass import Compass,active_label_color,direction_angle,direction_highlight


def polar_pixel(image, angle, radius):
    radians = math.radians(angle)
    x = image.width() / 2 + radius * math.cos(radians)
    y = image.height() / 2 - radius * math.sin(radians)
    return image.pixelColor(round(x), round(y))


def render(widget):
    image=QImage(widget.width(),widget.height(),QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent);widget.render(image)
    return image


class GlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.overlay=Compass();self.overlay.show();self.app.processEvents()

    def tearDown(self):self.overlay.close();self.app.processEvents()

    def settle(self):
        self.overlay.animation.setCurrentTime(self.overlay.animation.duration());self.app.processEvents()

    def test_all_eight_directions_and_ambiguity(self):
        for active, angle in (({'北'}, 90), ({'南'}, -90), ({'东'}, 0), ({'西'}, 180),
                              ({'东','北'}, 45), ({'西','北'}, 135), ({'东','南'}, -45), ({'西','南'}, -135)):
            self.assertEqual(direction_angle(active), angle)
        for active in (set(),{'东','西'},{'南','北'},{'东','西','北'}):
            self.assertIsNone(direction_angle(active))

    def test_diagonal_has_glowing_rim_and_two_arrows_with_clear_center(self):
        self.overlay.set_text('向东北方向走');self.settle();image=render(self.overlay)
        rim = polar_pixel(image, 45, 83.25)
        halo = polar_pixel(image, 45, 92)
        self.assertGreater(rim.alpha(),100)
        self.assertGreater(rim.blue(),rim.red())
        self.assertGreater(halo.alpha(),0)
        self.assertLess(halo.alpha(),rim.alpha())
        self.assertGreater(polar_pixel(image, 45, 27).alpha(),100)
        self.assertGreater(polar_pixel(image, 45, 37.5).alpha(),100)
        self.assertEqual(image.pixelColor(60,180).alpha(),0)
        self.assertEqual(image.pixelColor(120,120).alpha(),0)
        self.assertEqual(image.pixelColor(0,0).alpha(),0)

    def test_clear_cancels_fade_and_all_timers_immediately(self):
        self.overlay.set_text('向北走');self.settle();self.overlay._fade_out()
        self.assertEqual(self.overlay.animation.state(),QAbstractAnimation.State.Running)
        self.overlay.clear()
        self.assertFalse(self.overlay.active);self.assertFalse(self.overlay.expiry.isActive())
        self.assertEqual(self.overlay.animation.state(),QAbstractAnimation.State.Stopped)
        self.assertEqual(self.overlay._opacity,0)

    def test_strength_color_and_legacy_switch(self):
        self.overlay.set_text('向东北走');self.settle();self.overlay.color=QColor('#ff8844')
        self.overlay.set_strength(30);low=polar_pixel(render(self.overlay),45,83.25)
        self.overlay.set_strength(90);high=polar_pixel(render(self.overlay),45,83.25)
        self.assertGreater(high.alpha(),low.alpha());self.assertGreater(high.red(),high.blue())
        self.overlay.set_glow_enabled(False)
        self.assertEqual(polar_pixel(render(self.overlay),45,83.25).alpha(),0)
        self.assertEqual(self.overlay.active,{'东','北'})

    def test_hold_is_idle_and_fade_finishes_cleanly(self):
        self.overlay.set_text('向西南走');self.settle()
        self.assertEqual(self.overlay.animation.state(),QAbstractAnimation.State.Stopped)
        self.assertTrue(self.overlay.expiry.isSingleShot())
        self.overlay._fade_out();self.settle()
        self.assertFalse(self.overlay.active);self.assertFalse(self.overlay.expiry.isActive())

    def test_active_label_uses_a_lighter_version_of_the_current_cue_color(self):
        self.overlay.set_text('向北走')
        self.settle()
        tints = []
        for value in ('#d4472a', '#3169d5'):
            self.overlay.color = QColor(value)
            tint = active_label_color(self.overlay.color)
            self.assertGreater(tint.lightness(), self.overlay.color.lightness())
            self.assertNotEqual(tint.rgb(), QColor('white').rgb())
            image = render(self.overlay)
            label_pixels = {image.pixelColor(x, y).rgb() for x in range(100, 140) for y in range(4, 36)
                            if image.pixelColor(x, y).alpha() == 255}
            self.assertIn(tint.rgb(), label_pixels)
            tints.append(tint)
        self.assertGreater(tints[0].red(), tints[0].blue())
        self.assertGreater(tints[1].blue(), tints[1].red())

    def test_longer_hold_survives_gaps_and_updates_direction(self):
        self.overlay.set_text('向东北走'); self.settle()
        self.assertEqual(self.overlay.expiry.interval(),5000)
        self.overlay.set_text(''); self.overlay.set_text('打开宝箱')
        self.assertEqual(self.overlay.active,{'东','北'})
        self.overlay.set_hold_seconds(10)
        self.assertEqual(self.overlay.expiry.interval(),10000)
        self.overlay.set_text('向西走');self.assertEqual(self.overlay.active,{'西'})
        self.overlay.set_hold_seconds(100);self.assertEqual(self.overlay.hold_seconds,30)

    def test_three_rim_segments_have_gaps_between_the_line_cores(self):
        image = direction_highlight({'北'},240,240,QColor('#8de7ff'))
        for angle in (56,90,124):
            self.assertGreater(polar_pixel(image,angle,83.25).alpha(),150)
        for angle in (69,111):
            self.assertLess(polar_pixel(image,angle,83.25).alpha(),125)
        for x,y in ((120,120),(20,120),(220,120),(120,218),(120,60)):
            self.assertEqual(image.pixelColor(x,y).alpha(),0)

    def test_all_eight_sectors_and_arrows_point_the_right_way(self):
        for active in ({'北'},{'南'},{'东'},{'西'},{'东','北'},{'东','南'},{'西','北'},{'西','南'}):
            image = direction_highlight(active,240,240,QColor('#8de7ff'),2.)
            angle = direction_angle(active)
            self.assertGreater(polar_pixel(image,angle,166.5).alpha(),150,str(active))
            self.assertGreater(polar_pixel(image,angle,75).alpha(),150,str(active))
            self.assertEqual(polar_pixel(image,angle+180,166.5).alpha(),0,str(active))

    def test_initial_position_restores_valid_saved_point_and_keeps_resize_on_screen(self):
        screen = self.app.primaryScreen()
        area = screen.availableGeometry()
        self.overlay.place_at_startup(None,screen)
        self.assertEqual(self.overlay.pos(),area.topLeft()+QPoint(12,12))
        saved = area.topLeft()+QPoint(40,30)
        self.overlay.place_at_startup(saved,screen)
        self.assertEqual(self.overlay.pos(),saved)
        self.overlay.set_extent(300)
        self.assertTrue(area.contains(self.overlay.frameGeometry()))


if __name__=='__main__':unittest.main()
