import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from genshinimpactvt.bilibili_subtitles import CueTimeline
from genshinimpactvt.subtitle_text import directions

class DirectionTests(unittest.TestCase):
    def test_spoken_directions_and_false_positives(self):
        for phrase,expected in [('正北',{'北'}),('东北角',{'东','北'}),('朝着北偏东走',{'东','北'}),('西面这边',{'西'}),('捡东西南瓜',set()),('不要往东北走',set())]:
            self.assertEqual(directions(phrase),expected,phrase)
    def test_short_cue_crossed_between_samples_is_not_lost(self):
        t=CueTimeline([(1.01,1.04,'往东北走')])
        self.assertEqual(t.at(1.1),'')
        self.assertEqual(t.direction_events(1.1,1.)[0][2],'往东北走')
    def test_adjacent_identical_phrases_have_distinct_ids(self):
        t=CueTimeline([(1,2,'向北'),(2,3,'向北')])
        self.assertNotEqual(t.direction_events(1.5)[0][1],t.direction_events(2.5,1.5)[-1][1])
    def test_sequential_directions_advance_within_cue(self):
        t=CueTimeline([(0,6,'先往东然后向北')])
        self.assertEqual(directions(t.direction_events(.2)[-1][2]),{'东'})
        self.assertEqual(directions(t.direction_events(5,.2)[-1][2]),{'北'})

if __name__=='__main__':unittest.main()
