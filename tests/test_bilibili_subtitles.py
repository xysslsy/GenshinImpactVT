import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QApplication
from genshinimpactvt.bilibili_subtitles import (CueTimeline,parse_cues,choose_track,
    allowed_caption_url,normalize_cid,player_record,BilibiliSubtitleFeed)
from genshinimpactvt.bilibili_subtitles import official_player_url,official_episode_url


class Browser(QObject):
    ready=Signal();source_changed=Signal(str);loading=Signal()
    web=SimpleNamespace(Source='https://www.bilibili.com/video/BV1CMHQzsEJV/?p=3')


class BiliSubtitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_timestamps_overlap_pause_and_seek(self):
        timeline=CueTimeline(parse_cues({'body':[
            {'from':5,'to':8,'content':'向北走'}, {'from':1,'to':3,'content':'向东走'},
            {'from':1,'to':2,'content':'这是测试'}, {'from':9,'to':7,'content':'无效'},
            {'from':float('nan'),'to':12,'content':'无效'}]}))
        self.assertEqual(timeline.at(0),'')
        self.assertIn('向东走',timeline.at(1.5))
        self.assertEqual(timeline.at(3),'')
        self.assertEqual(timeline.at(6),'向北走')
        self.assertIn('向东走',timeline.at(1.5))

    def test_only_provider_cdn_caption_urls(self):
        for url in ('https://aisubtitle.hdslb.com/bfs/ai_subtitle/test.json',
                    '//i0.hdslb.com/bfs/subtitle/test.json'):
            self.assertTrue(allowed_caption_url(url))
        for url in ('file:///tmp/caption','http://aisubtitle.hdslb.com/bfs/ai_subtitle/x',
                    'https://hdslb.com.evil.test/bfs/subtitle/x','https://127.0.0.1/bfs/subtitle/x',
                    'https://u:p@hdslb.com/bfs/subtitle/x','https://hdslb.com:444/bfs/subtitle/x',
                    'https://hdslb.com/not-a-caption'):
            self.assertFalse(allowed_caption_url(url))

    def test_chinese_track_and_no_account_metadata_retained(self):
        tracks=[{'lan':'ai-en','subtitle_url':'https://aisubtitle.hdslb.com/bfs/ai_subtitle/en.json'},
                {'lan':'ai-zh','subtitle_url':'https://aisubtitle.hdslb.com/bfs/ai_subtitle/zh.json'}]
        self.assertEqual(choose_track(tracks)['lan'],'ai-zh')
        record=player_record({'code':0,'data':{'login_mid':123,'subtitle':{'subtitles':tracks},'other':'private'}})
        self.assertNotIn('login_mid',json.dumps(record));self.assertNotIn('private',json.dumps(record))

    def test_login_requirement_is_not_reported_as_no_captions(self):
        feed=BilibiliSubtitleFeed(Browser())
        feed.use_player_data({'code':0,'data':{'need_login_subtitle':True}})
        self.assertIn('登录',feed.message);self.assertIsNone(feed._future);feed.close()

    def test_large_cid_serialized_as_float(self):
        self.assertEqual(normalize_cid(32294243227.0),'32294243227')
        self.assertEqual(normalize_cid('32294243227'),'32294243227')
        for bad in (True,1.5,float('inf'),None,'1.0'):self.assertEqual(normalize_cid(bad),'')

    def test_tracking_url_does_not_clear_subtitles(self):
        browser=Browser();feed=BilibiliSubtitleFeed(browser)
        feed.on_source_changed(browser.web.Source)
        feed.timeline=CueTimeline([(0,5,'向东走')]);epoch=feed.epoch
        feed.on_source_changed(browser.web.Source+'&spm_id_from=test')
        self.assertEqual(feed.epoch,epoch);self.assertEqual(feed.timeline.at(1),'向东走')
        feed.on_source_changed('https://www.bilibili.com/video/BV1CMHQzsEJV/?p=4')
        self.assertGreater(feed.epoch,epoch);self.assertFalse(feed.timeline.cues);feed.close()

    def test_auto_mode_never_starts_ocr(self):
        from unittest.mock import patch
        import tempfile
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QWidget
        from genshinimpactvt.compass import Compass
        from genshinimpactvt.subtitles import SubtitleController
        with tempfile.TemporaryDirectory() as temp:
            parent=QWidget();compass=Compass();settings=QSettings(str(Path(temp)/'s.ini'),QSettings.Format.IniFormat)
            service=SubtitleController(Browser(),compass,settings,parent)
            service.enabled=True;service._metadata={'time':0,'seeking':False,'ended':False,'ready':4,'text':'','paused':False}
            service.read_page=lambda now:None
            with patch.object(service,'start_worker') as start:
                service.tick();start.assert_not_called()
            service.close();compass.close();parent.close()

    def test_official_player_episode_does_not_keep_cid(self):
        from urllib.parse import parse_qs,urlsplit
        url=official_player_url('BV1CMHQzsEJV',3,'32294243227')
        target=official_episode_url(url,1);query=parse_qs(urlsplit(target).query)
        self.assertEqual(query['p'],['4']);self.assertNotIn('cid',query)
        with self.assertRaises(ValueError):official_episode_url(official_player_url('BV1CMHQzsEJV',1),-1)
        self.assertIsNone(official_episode_url('https://www.bilibili.com/video/BV1CMHQzsEJV/',1))

    def test_embed_cid_change_invalidates_timeline(self):
        feed=BilibiliSubtitleFeed(Browser())
        feed.on_source_changed(official_player_url('BV1CMHQzsEJV',3,'32294243227'))
        feed.timeline=CueTimeline([(0,5,'向东走')]);epoch=feed.epoch
        feed.on_source_changed(official_player_url('BV1CMHQzsEJV',3,'32294243228'))
        self.assertGreater(feed.epoch,epoch);self.assertFalse(feed.timeline.cues);feed.close()


if __name__=='__main__':unittest.main()
