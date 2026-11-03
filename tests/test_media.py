import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from genshinimpactvt.compass import directions
from genshinimpactvt.raw_mouse import side_buttons

class MediaTests(unittest.TestCase):
    def test_directions(self):
        self.assertEqual(directions('往东再向北'), {'东', '北'})
        self.assertEqual(directions('找东西'), set())
        self.assertEqual(directions('不是南'), set())

    def test_raw_mouse_flags(self):
        self.assertEqual(side_buttons(0x40), [1])
        self.assertEqual(side_buttons(0x100), [2])
        self.assertEqual(side_buttons(0x140), [1, 2])
        self.assertEqual(side_buttons(0x280), [])

if __name__ == '__main__': unittest.main()
