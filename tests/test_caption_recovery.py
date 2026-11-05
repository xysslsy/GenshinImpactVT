import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QApplication
from genshinimpactvt.bilibili_subtitles import BilibiliSubtitleFeed,CueTimeline,page_identity

URL='https://www.bilibili.com/video/BV1CMHQzsEJV/?p=3'


class Browser(QObject):
    ready=Signal();source_changed=Signal(str);loading=Signal()
    def __init__(self):
        super().__init__();self.web=SimpleNamespace(Source=URL);self.scripts=[];self.results=[]
    def execute_script(self,script):
        self.scripts.append(script)
        value=self.results.pop(0) if self.results else True
        return SimpleNamespace(IsCompleted=True,Result=json.dumps(value))


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.browser=Browser();self.feed=BilibiliSubtitleFeed(self.browser);self.feed.core=SimpleNamespace()
        self.feed.enabled=True
    def tearDown(self):self.feed.close()
    def success(self,cid='33',page=3):
        return {'status':'ok','key':{'bvid':'BV1CMHQzsEJV','cid':cid,'page':page},'label':'中文',
                'caption':{'body':[{'from':1,'to':4,'content':'向东北走'}]}}
    def test_identity_ignores_tracking_and_distinguishes_parts(self):
        self.assertEqual(page_identity(URL),page_identity(URL+'&spm_id_from=whatever'))
        self.assertNotEqual(page_identity(URL),page_identity(URL.replace('p=3','p=4')))
        for bad in ('https://evil.test/video/BV1CMHQzsEJV/','https://www.bilibili.com/','https://www.bilibili.com/video/BV1CMHQzsEJV/?p=0'):
            self.assertIsNone(page_identity(bad))
    def test_late_enable_bootstraps_without_player_response(self):
        feed=self.feed
        with patch('genshinimpactvt.bilibili_subtitles.time.monotonic',return_value=10.):
            feed.request_recovery(immediate=True);feed.poll_recovery(10.)
            self.browser.results.append({'done':True,'result':self.success()})
            feed.poll_recovery(10.1);feed.poll_recovery(10.2)
        self.assertEqual(feed.text_at(2),'向东北走');self.assertEqual(feed.video_key,('BV1CMHQzsEJV','33'))
        self.assertTrue(any('fetch(' in script for script in self.browser.scripts))
        feed.poll();self.assertFalse(feed.timer.isActive())
    def test_retry_budget_and_new_video_reset(self):
        feed=self.feed
        with patch('genshinimpactvt.bilibili_subtitles.time.monotonic',return_value=10.):
            for attempt in range(1,5):
                feed._attempts=attempt;feed.apply_recovery({'status':'error','reason':'timeout'})
                self.assertEqual(bool(feed._retry_at),attempt<4)
            feed.request_recovery();self.assertFalse(feed._retry_at)
            self.browser.web.Source=URL.replace('p=3','p=4');feed.on_source_changed(self.browser.web.Source)
            self.assertEqual(feed._attempts,0);self.assertTrue(feed._retry_at)
    def test_old_part_result_never_replaces_current_video(self):
        feed=self.feed;self.browser.web.Source=URL.replace('p=3','p=4')
        feed.apply_recovery(self.success(page=3));self.assertFalse(feed.timeline.cues)
        feed.apply_recovery(self.success(cid='44',page=4));self.assertEqual(feed.video_key[1],'44')
        # Stale __INITIAL_STATE__.cid must not undo the resolved current part.
        feed.set_video('BV1CMHQzsEJV','33');self.assertEqual(feed.video_key[1],'44')
    def test_refresh_rearms_and_does_not_reload_page(self):
        feed=self.feed;feed._attempts=4;feed.timeline=CueTimeline([(0,3,'向东走')])
        with patch('genshinimpactvt.bilibili_subtitles.time.monotonic',return_value=10.):feed.refresh()
        self.assertEqual(feed._attempts,0);self.assertEqual(feed._retry_at,10.)
        self.assertFalse(feed.timeline.cues);self.assertIn('不会刷新',feed.message)
        self.assertFalse(any('reload' in script for script in self.browser.scripts))
    def test_expired_response_does_not_block_queue_forever(self):
        self.feed._pending=[(0,'33',SimpleNamespace(IsCompleted=False),0.)]
        with patch('genshinimpactvt.bilibili_subtitles.time.monotonic',return_value=30.):self.feed.poll()
        self.assertFalse(self.feed._pending)
    def test_ready_timeline_is_not_overwritten_by_late_failure(self):
        self.feed.apply_recovery(self.success())
        self.feed.use_player_data({'code':-101})
        self.feed.apply_recovery({'status':'error'})
        self.assertIn('已载入',self.feed.message);self.assertEqual(self.feed.text_at(2),'向东北走')
    def test_mismatched_player_response_does_not_fetch_wrong_part(self):
        self.feed.video_key=('BV1CMHQzsEJV','33')
        self.feed.use_player_data({'code':0,'data':{'cid':'44','subtitle':{'subtitles':[
            {'lan':'ai-zh','subtitle_url':'https://aisubtitle.hdslb.com/bfs/ai_subtitle/x.json'}]}}})
        self.assertIsNone(self.feed._future);self.assertTrue(self.feed._retry_at)
        self.assertIn('不一致',self.feed.message)
    def test_empty_download_is_retried_instead_of_reported_ready(self):
        from concurrent.futures import Future
        feed=self.feed;feed.video_key=('BV1CMHQzsEJV','33')
        feed._fetch_key=(feed.epoch,feed.video_key,'unused')
        feed._future=Future();feed._future.set_result([])
        feed.poll()
        self.assertFalse(feed.timeline.cues);self.assertNotIn('已载入 0',feed.message)
        self.assertTrue(feed._retry_at or feed._recovery_task)
    def test_disabled_and_non_video_pages_do_not_send_requests(self):
        self.feed.enabled=False;self.feed.request_recovery();self.feed.poll_recovery(100.)
        self.assertFalse(self.browser.scripts)
        self.feed.enabled=True;self.browser.web.Source='https://example.com/'
        self.feed.request_recovery();self.feed.poll_recovery(100.)
        self.assertFalse(self.browser.scripts)

    def test_saved_enabled_setting_is_safe_before_browser_initialization(self):
        self.feed.enabled=False;self.feed.core=None;self.browser.web=None
        self.feed.set_enabled(True)
        self.assertTrue(self.feed.enabled);self.assertFalse(self.browser.scripts)


if __name__=='__main__':unittest.main()
