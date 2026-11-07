import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QAbstractAnimation
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from genshinimpactvt.compass import Compass,ambient_position,rim_highlight


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
        for active,quadrant in (({'北'},(0,-1)),({'南'},(0,1)),({'东'},(1,0)),({'西'},(-1,0)),
                                ({'东','北'},(1,-1)),({'西','北'},(-1,-1)),({'东','南'},(1,1)),({'西','南'},(-1,1))):
            x,y,r=ambient_position(active,240,240)
            self.assertEqual(((x>120)-(x<120),(y>120)-(y<120)),quadrant)
            self.assertGreater(r,0)
        for active in (set(),{'东','西'},{'南','北'},{'东','西','北'}):
            self.assertIsNone(ambient_position(active,240,240))

    def test_diagonal_is_one_soft_transparent_blue_light(self):
        self.overlay.set_text('向东北方向走');self.settle();image=render(self.overlay)
        x,y,r=ambient_position(self.overlay.active,240,240)
        center=image.pixelColor(round(x),round(y))
        self.assertGreater(center.alpha(),100);self.assertGreater(center.blue(),center.red())
        self.assertLess(image.pixelColor(round(x+r*.8),round(y)).alpha(),center.alpha())
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
        x,y,_=ambient_position(self.overlay.active,240,240)
        self.overlay.set_strength(30);low=render(self.overlay).pixelColor(round(x),round(y))
        self.overlay.set_strength(90);high=render(self.overlay).pixelColor(round(x),round(y))
        self.assertGreater(high.alpha(),low.alpha());self.assertGreater(high.red(),high.blue())
        self.overlay.set_glow_enabled(False)
        self.assertEqual(render(self.overlay).pixelColor(round(x),round(y)).alpha(),0)
        self.assertEqual(self.overlay.active,{'东','北'})

    def test_hold_is_idle_and_fade_finishes_cleanly(self):
        self.overlay.set_text('向西南走');self.settle()
        self.assertEqual(self.overlay.animation.state(),QAbstractAnimation.State.Stopped)
        self.assertTrue(self.overlay.expiry.isSingleShot())
        self.overlay._fade_out();self.settle()
        self.assertFalse(self.overlay.active);self.assertFalse(self.overlay.expiry.isActive())

    def test_longer_hold_survives_gaps_and_updates_direction(self):
        self.overlay.set_text('向东北走'); self.settle()
        self.assertEqual(self.overlay.expiry.interval(),5000)
        self.overlay.set_text(''); self.overlay.set_text('打开宝箱')
        self.assertEqual(self.overlay.active,{'东','北'})
        self.overlay.set_hold_seconds(10)
        self.assertEqual(self.overlay.expiry.interval(),10000)
        self.overlay.set_text('向西走');self.assertEqual(self.overlay.active,{'西'})
        self.overlay.set_hold_seconds(100);self.assertEqual(self.overlay.hold_seconds,30)

    def test_rim_sector_has_width_without_a_center_ball(self):
        image=rim_highlight({'北'},240,240,QColor('#4080ff'),1.)
        self.assertGreater(image.pixelColor(120,22).alpha(),100)
        for x,y in ((75,30),(165,30)):
            self.assertGreater(image.pixelColor(x,y).alpha(),20)
        for x,y in ((120,120),(20,120),(220,120),(120,218),(120,60)):
            self.assertEqual(image.pixelColor(x,y).alpha(),0)

    def test_all_eight_rim_sectors_point_the_right_way(self):
        for active in ({'北'},{'南'},{'东'},{'西'},{'东','北'},{'东','南'},{'西','北'},{'西','南'}):
            image=rim_highlight(active,240,240,QColor('#4080ff'),1.)
            x,y,_=ambient_position(active,240,240)
            self.assertGreater(image.pixelColor(round(x),round(y)).alpha(),100,str(active))
            self.assertEqual(image.pixelColor(round(240-x),round(240-y)).alpha(),0,str(active))


if __name__=='__main__':unittest.main()
