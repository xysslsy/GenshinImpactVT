import json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QApplication
from genshinimpactvt.bilibili_subtitles import BilibiliSubtitleFeed,page_identity
URL='https://www.bilibili.com/video/BV1CMHQzsEJV/?p=3'
class Browser(QObject):
    ready=Signal();source_changed=Signal(str);loading=Signal()
    def __init__(self):
        super().__init__();self.web=SimpleNamespace(Source=URL);self.scripts=[];self.results=[]
    def execute_script(self,script):
        self.scripts.append(script)
        return SimpleNamespace(IsCompleted=True,Result=json.dumps(self.results.pop(0) if self.results else True))
class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.browser=Browser();self.feed=BilibiliSubtitleFeed(self.browser)
        self.feed.enabled=True;self.feed.core=True
        self.context={'document':'doc-1','media':'video-1','src':'blob:one','player_cid':'33','duration':100,'ready':4}
        self.feed.set_context(self.context);self.feed.timer.stop()
    def tearDown(self):self.feed.close()
    def job(self):
        feed=self.feed;feed._recovery_token='job-1'
        feed._job=('job-1',feed.epoch,feed.signature(feed._context),page_identity(URL))
        return feed._job
    def success(self):
        self.job()
        return {'status':'ok','token':'job-1','context':dict(self.context),'verified':True,'track_id':'track-33',
                'key':{'bvid':'BV1CMHQzsEJV','cid':'33','page':3},'label':'中文',
                'caption':{'body':[{'from':1,'to':4,'content':'向东北走'}]}}
    def test_verified_result_accepts_only_exact_playback_context(self):
        self.assertTrue(self.feed.apply_recovery(self.success()))
        self.assertEqual(self.feed.text_at(2),'向东北走');self.assertIn('已核对',self.feed.message)
    def test_same_cid_wrong_document_media_or_request_is_rejected(self):
        for field,value in [('document','other'),('media','other'),('src','blob:other'),('player_cid','44')]:
            result=self.success();result['context'][field]=value
            self.assertFalse(self.feed.apply_recovery(result));self.assertFalse(self.feed.timeline.cues)
        for field,value in [('bvid','BV1xx411c7mD'),('cid','44'),('page',4)]:
            result=self.success();result['key'][field]=value;self.assertFalse(self.feed.apply_recovery(result))
        result=self.success();result['token']='old';self.assertFalse(self.feed.apply_recovery(result))
    def test_missing_provenance_is_never_accepted(self):
        for field in ('token','context','verified','track_id'):
            result=self.success();result.pop(field);self.assertFalse(self.feed.apply_recovery(result))
    def test_manual_refresh_invalidates_same_video_old_result(self):
        result=self.success();job=self.feed._job;self.feed.refresh()
        self.assertFalse(self.feed.apply_recovery(result,job));self.assertFalse(self.feed.timeline.cues)
        self.assertFalse(any('location.reload' in s for s in self.browser.scripts))
    def test_old_page_result_rejected_before_source_signal(self):
        result=self.success();self.browser.web.Source=URL.replace('p=3','p=4')
        self.assertFalse(self.feed.apply_recovery(result))
    def test_media_change_clears_loaded_captions(self):
        self.feed.apply_recovery(self.success());self.feed.set_context(dict(self.context,src='blob:next'))
        self.assertEqual(self.feed.text_at(2),'');self.assertIsNone(self.feed.video_key)
    def test_unsolicited_response_cannot_load_captions(self):
        self.feed.use_player_data({'code':0,'data':{'cid':'33'}})
        self.assertFalse(self.feed.timeline.cues);self.assertFalse(self.feed._subscribed)
    def test_page_global_hint_cannot_replace_verified_identity(self):
        self.feed.apply_recovery(self.success());self.feed.set_video('BV1xx411c7mD','44')
        self.assertEqual(self.feed.video_key,('BV1CMHQzsEJV','33'))
    def test_empty_or_overlong_caption_rejected(self):
        result=self.success();result['caption']['body']=[]
        with self.assertRaises(ValueError):self.feed.apply_recovery(result)
        result=self.success();result['caption']['body'][0]['to']=200
        with self.assertRaises(ValueError):self.feed.apply_recovery(result)
    def test_retry_budget_reset_on_new_page(self):
        for attempt in range(1,4):
            self.feed._attempts=attempt;self.feed.retry_recovery('temporary')
            self.assertEqual(bool(self.feed._retry_at),attempt<3)
        self.browser.web.Source=URL.replace('p=3','p=4');self.feed.on_source_changed(self.browser.web.Source)
        self.assertEqual(self.feed._attempts,0);self.assertFalse(self.feed.timer.isActive())
    def test_enabled_safe_before_browser_ready(self):
        self.feed.enabled=False;self.feed.core=None;self.browser.web=None
        self.feed.set_enabled(True);self.assertTrue(self.feed.enabled)
    def test_close_stops_job_and_timer(self):
        self.job();self.feed.close();self.assertIsNone(self.feed._job);self.assertFalse(self.feed.timer.isActive())
    def test_tracking_ignored(self):
        self.assertEqual(page_identity(URL),page_identity(URL+'&spm_id_from=test'))
    def test_waiting_duration_change_rearms_exhausted_attempts(self):
        self.feed._context['duration']=0
        self.feed._waiting_context=self.feed.waiting_signature()
        self.feed._attempts=3;self.feed._retry_at=0
        self.feed.set_context(dict(self.context,duration=100))
        self.assertEqual(self.feed._attempts,0);self.assertTrue(self.feed._retry_at)
if __name__=='__main__':unittest.main()
