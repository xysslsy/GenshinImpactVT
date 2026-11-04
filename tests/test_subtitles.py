import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from genshinimpactvt.subtitle_text import DEFAULT_REGION, StableText, directions, valid_region


class SubtitleTests(unittest.TestCase):
    def test_directions_and_false_positives(self):
        for text,expected in [('向东前进',{'东'}),('往东北方向走',{'东','北'}),
                              ('向西南走',{'西','南'}),('捡起这个东西',set()),
                              ('不要往东走',set()),('不是南，是北边',{'北'}),
                              ('先往东然后向北',{'东'}),('北京的东北虎',set()),
                              ('往 南 边 走',{'南'})]:
            with self.subTest(text=text): self.assertEqual(directions(text),expected)

    def test_stability_empty_recurrence_and_timeline_reset(self):
        gate=StableText()
        self.assertIsNone(gate.observe('向东走','ocr',0))
        self.assertEqual(gate.observe('向东走','ocr',.5),'向东走')
        self.assertIsNone(gate.observe('向东走','ocr',1))
        gate.observe('','ocr',1.5)
        self.assertIsNone(gate.observe('向东走','ocr',2))
        self.assertEqual(gate.observe('向东走','ocr',2.5),'向东走')
        gate.reset()
        self.assertEqual(gate.observe('向东走','dom',3),'向东走')

    def test_single_frame_and_late_repeats_rejected(self):
        gate=StableText()
        self.assertIsNone(gate.observe('向北','ocr',0))
        self.assertIsNone(gate.observe('向南','ocr',.5))
        self.assertIsNone(gate.observe('向南','ocr',4))

    def test_region_config_validation(self):
        for bad in (None,[],['oops'],[.9,0,.5,.5],[0,0,0,0],[float('nan'),0,.5,.5]):
            self.assertEqual(valid_region(bad),DEFAULT_REGION)
        self.assertEqual(valid_region([.1,.7,.8,.2]),(.1,.7,.8,.2))


if __name__=='__main__': unittest.main()
