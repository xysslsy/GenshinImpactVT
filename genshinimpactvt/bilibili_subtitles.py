"""Read caption data offered to the normal Bilibili player; no ASR or signing."""
import bisect
import concurrent.futures
import json
import math
import time
from urllib.parse import parse_qs, urlsplit, urlencode
from pathlib import Path
import re

from PySide6.QtCore import QObject, QTimer, Signal
from .subtitle_text import direction_steps

MAX_BYTES = 4 * 1024 * 1024
PLAYER_PATHS = ('/x/player/wbi/v2', '/x/player/v2')


def normalize_cid(value):
    if isinstance(value,bool):return ''
    if isinstance(value,(int,float)):
        return str(int(value)) if math.isfinite(value) and 0<value<=2**53 and int(value)==value else ''
    return value if isinstance(value,str) and value.isdigit() else ''


def official_player_url(bvid,page=1,cid='',autoplay=False):
    import re
    if not isinstance(bvid,str) or not re.fullmatch(r'BV[0-9A-Za-z]{10}',bvid):
        raise ValueError('请先打开 B站视频')
    try:page=max(1,int(page))
    except (TypeError,ValueError):page=1
    query={'bvid':bvid,'p':page,'autoplay':int(autoplay),'danmaku':0}
    if normalize_cid(cid):query['cid']=normalize_cid(cid)
    return 'https://player.bilibili.com/player.html?'+urlencode(query)


def official_episode_url(url,delta):
    parsed=urlsplit(url)
    if parsed.hostname!='player.bilibili.com' or parsed.path!='/player.html':return None
    query=parse_qs(parsed.query)
    try:page=int(query.get('p',['1'])[0])+delta
    except ValueError:page=1
    if page<1:raise ValueError('已经是第一集')
    # cid overrides p in the official API: deliberately omit it for a new episode.
    return official_player_url(query.get('bvid',[''])[0],page,autoplay=True)


def is_bilibili_page(url):
    try:
        p = urlsplit(url)
        return p.scheme == 'https' and (p.hostname == 'bilibili.com' or (p.hostname or '').endswith('.bilibili.com'))
    except ValueError:
        return False


def page_identity(url):
    """A logical video/part, ignoring tracking parameters and stale page globals."""
    if not is_bilibili_page(url): return None
    try:
        parsed=urlsplit(url);query=parse_qs(parsed.query)
        match=re.search(r'/video/(BV[0-9A-Za-z]{10})(?:/|$)',parsed.path)
        bvid=match.group(1) if match else query.get('bvid',[''])[0] if parsed.hostname=='player.bilibili.com' else ''
        if not re.fullmatch(r'BV[0-9A-Za-z]{10}',bvid): return None
        page=int(query.get('p',['1'])[0])
        if not 1<=page<=100000: return None
        return (bvid,page,normalize_cid(query.get('cid',[''])[0]) if parsed.hostname=='player.bilibili.com' else '')
    except (ValueError,TypeError): return None

MEDIA_CONTEXT=Path(__file__).with_name('media_context.js').read_text(encoding='utf-8')
RECOVERY_SCRIPT=Path(__file__).with_name('caption_recovery.js').read_text(encoding='utf-8').replace('MEDIA_CONTEXT',MEDIA_CONTEXT)
RETRY_DELAYS=(2.,5.,12.)


def allowed_caption_url(url):
    """Only provider-supplied HTTPS subtitle URLs on Bilibili's CDN."""
    try:
        p = urlsplit(url if not url.startswith('//') else 'https:'+url)
        host = p.hostname or ''
        return (p.scheme == 'https' and p.username is None and p.password is None
                and p.port in (None,443) and (host == 'hdslb.com' or host.endswith('.hdslb.com'))
                and p.path.startswith(('/bfs/subtitle/','/bfs/ai_subtitle/')))
    except (ValueError,AttributeError):
        return False


def parse_cues(document):
    body = document.get('body') if isinstance(document,dict) else None
    if not isinstance(body,list) or len(body)>30000:
        raise ValueError('字幕格式不受支持')
    cues = []
    for row in body:
        if not isinstance(row,dict): continue
        try:
            start,end = float(row['from']),float(row['to']);text = row['content']
            if not (math.isfinite(start) and math.isfinite(end) and 0<=start<end): continue
            if not isinstance(text,str): continue
            text=text.strip()[:500]
            if text:cues.append((start,end,text))
        except (KeyError,TypeError,ValueError): continue
    cues.sort(key=lambda item:item[:2])
    return cues


class CueTimeline:
    def __init__(self,cues=()):
        self.cues=list(cues);self.starts=[cue[0] for cue in cues]

    def at(self,seconds):
        i=bisect.bisect_right(self.starts,seconds)-1
        # Include overlapping lines with the same start; bound lookup work.
        found=[]
        for n in range(max(0,i-8),i+1):
            start,end,text=self.cues[n]
            if start<=seconds<end:found.append(text)
        return ' '.join(dict.fromkeys(found))[:500]

    def direction_events(self,seconds,since=None):
        end=bisect.bisect_right(self.starts,seconds)
        begin=max(0,bisect.bisect_right(self.starts,since)-1) if since is not None else max(0,end-1)
        events=[]
        for index in range(begin,end):
            start,stop,text=self.cues[index]
            steps=direction_steps(text)
            current=[]
            for part,(fraction,phrase) in enumerate(steps):
                when=start+(stop-start)*fraction
                if since is not None and since<when<=seconds:events.append((when,(index,part),phrase))
                if start<=seconds<stop and when<=seconds:current.append((when,(index,part),phrase))
            if current and current[-1] not in events:events.append(current[-1])
        return sorted(events,key=lambda value:value[0])


def choose_track(tracks):
    valid=[]
    for row in tracks if isinstance(tracks,list) else []:
        if isinstance(row,dict) and allowed_caption_url(row.get('subtitle_url','')):
            valid.append(row)
    def priority(track):
        language=str(track.get('lan',''))
        return (0 if language in ('zh-CN','zh-Hans','zh') else
                1 if language.startswith('ai-zh') else 2 if 'zh' in language else 3)
    return min(valid,key=priority) if valid else None


def player_record(document):
    """Retain only caption fields, not the player's account or other metadata."""
    data=document.get('data') if isinstance(document,dict) else None
    if not isinstance(data,dict):data={}
    subtitle=data.get('subtitle')
    if not isinstance(subtitle,dict):subtitle={}
    tracks=subtitle.get('subtitles',[])
    if not isinstance(tracks,list):tracks=[]
    return {'code':document.get('code'),'data':{'cid':normalize_cid(data.get('cid')),
        'bvid':data.get('bvid') if isinstance(data.get('bvid'),str) and re.fullmatch(r'BV[0-9A-Za-z]{10}',data['bvid']) else '',
        'need_login_subtitle':bool(data.get('need_login_subtitle')),
        'subtitle':{'subtitles':[{k:row.get(k) for k in ('lan','lan_doc','subtitle_url','ai_type')}
                                for row in tracks[:30] if isinstance(row,dict)]}}}


def fetch_caption(url):
    # No cookies, credentials, audio, user files, or model downloads.
    import urllib.request
    class SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            if not allowed_caption_url(newurl): raise ValueError('字幕地址重定向到不支持的站点')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    if url.startswith('//'):url='https:'+url
    if not allowed_caption_url(url):raise ValueError('字幕地址不受支持')
    request=urllib.request.Request(url,headers={'Referer':'https://www.bilibili.com/',
                                               'User-Agent':'Mozilla/5.0 GenshinImpactVT/0.2'})
    with urllib.request.build_opener(SafeRedirect()).open(request,timeout=10) as response:
        data=response.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('字幕文件超过大小限制')
    return parse_cues(json.loads(data.decode('utf-8-sig')))


class BilibiliSubtitleFeed(QObject):
    """One loader, one generation and one verified playback context. No response racing."""
    changed=Signal()

    def __init__(self,browser,parent=None):
        super().__init__(parent);self.browser=browser;self.enabled=False;self.core=None
        self.epoch=0;self.video_key=None;self.timeline=CueTimeline();self.label='B站字幕'
        self.message='请打开 B站视频';self._closed=False;self._page_key=None
        self._context=None;self._loaded_context=None;self._loaded_page=None
        self._recovery_task=None;self._recovery_token='';self._recovery_phase=''
        self._job=None;self._attempts=0;self._retry_at=0.;self._recovery_started=0.
        self._waiting_context=None;self._subscribed=False;self._records={}
        self.timer=QTimer(self);self.timer.setInterval(80);self.timer.timeout.connect(self.poll)
        browser.ready.connect(self.attach);browser.source_changed.connect(self.on_source_changed)
        browser.loading.connect(self.reset)

    def source(self):return str(getattr(self.browser.web,'Source','') or '')
    def attach(self):
        self.core=self.browser.web.CoreWebView2
        self.request_recovery()
    def update_subscription(self):pass  # v2 never accepts unsolicited player responses.
    def on_resource(self,*args):pass

    def set_enabled(self,enabled):
        enabled=bool(enabled)
        if self.enabled!=enabled:self.enabled=enabled;self.reset()

    def cancel_recovery(self):
        token=self._recovery_token
        if token:
            try:self.browser.execute_script('(()=>{let s=window.__givtCaptionRecovery;if(s&&s.token==='+json.dumps(token)+'){s.abort.abort();delete window.__givtCaptionRecovery}})()')
            except Exception:pass
        self._recovery_task=None;self._recovery_token='';self._job=None;self._retry_at=0.

    def reset(self,*args):
        self.cancel_recovery();self.epoch+=1;self.timer.stop()
        self.video_key=None;self.timeline=CueTimeline();self._loaded_context=None;self._loaded_page=None
        self._context=None;self._attempts=0;self._waiting_context=None
        self.message='正在核对当前视频，请等待播放器就绪';self.changed.emit()

    def on_source_changed(self,url):
        key=page_identity(url)
        if key!=self._page_key:self._page_key=key;self.reset()

    @staticmethod
    def signature(meta):
        if not isinstance(meta,dict):return None
        if not meta.get('document') or not meta.get('media') or not meta.get('src'):return None
        return (str(meta['document']),str(meta['media']),str(meta['src']),str(meta.get('player_cid') or ''))

    def set_context(self,metadata):
        key=page_identity(self.source());signature=self.signature(metadata)
        if not key or signature is None:return
        if self._context and self.signature(self._context)!=signature:
            self.reset()
        self._context={k:metadata.get(k) for k in ('document','media','src','player_cid','duration','ready')}
        self.request_recovery()

    def set_video(self,bvid,cid):
        # Page globals are hints, never an authority capable of replacing a verified timeline.
        return

    def use_player_data(self,document):
        if self.timeline.cues:return
        data=document.get('data') or {}
        if data.get('need_login_subtitle'):self.message='请在软件内登录 B站后重试字幕'
        else:self.message='正在独立核对当前播放器与字幕归属'
        self.request_recovery()

    def request_recovery(self,immediate=False):
        if self._closed or not self.enabled or self.timeline.cues or self._recovery_task is not None:return
        if not page_identity(self.source()) or not self._context or not self.core:return
        if (self._context.get('ready') or 0)<2 or self._attempts>=5:return
        if self._waiting_context==self.signature(self._context):return
        if not self._retry_at:self._retry_at=time.monotonic()+(0 if immediate else .1)
        self.timer.start()

    def refresh(self):
        context=self._context;self.reset();self._context=context
        self.message='正在重新核对字幕，不刷新视频'
        self.request_recovery(immediate=True)

    def retry_recovery(self,message):
        if self.timeline.cues:return
        if self._attempts<5:
            delay=(1.,2.,4.,8.)[max(0,self._attempts-1)]
            self._retry_at=time.monotonic()+delay
            self.message=message+f'；{int(delay)} 秒后重试（{self._attempts}/5）'
            self.timer.start()
        else:self._retry_at=0.;self.message=message+'；请点“重试字幕”再次核对'
        self.changed.emit()

    def apply_recovery(self,result,job=None):
        job=job or self._job
        if not job or job!=(self._recovery_token,self.epoch,self.signature(self._context),page_identity(self.source())):return False
        if not isinstance(result,dict) or result.get('token')!=job[0]:return False
        proof=result.get('context') or {}
        if self.signature(proof)!=job[2]:return False
        key=result.get('key') or {};identity=job[3];cid=normalize_cid(key.get('cid'))
        if not identity or key.get('bvid')!=identity[0] or key.get('page')!=identity[1] or not cid:return False
        if identity[2] and identity[2]!=cid:return False
        if self._context.get('player_cid') and str(self._context['player_cid'])!=cid:return False
        if result.get('status')=='ok':
            if not result.get('track_id') or not result.get('verified'):return False
            cues=parse_cues(result.get('caption'))
            if not cues:raise ValueError('平台返回空字幕')
            duration=float(self._context.get('duration') or 0)
            if duration and max(c[1] for c in cues)>duration+5:raise ValueError('字幕时间超过当前视频长度，拒绝载入')
            self.timeline=CueTimeline(cues);self.video_key=(identity[0],cid)
            self._loaded_context=job[2];self._loaded_page=identity
            self.label=str(result.get('label','中文'))[:60]
            self.message=f'已核对 {identity[0]} · P{identity[1]} · {self.label} · {len(cues)} 条字幕'
            self._retry_at=0.;self.changed.emit();return True
        return False

    def poll(self):
        if self._closed or not self.enabled:self.timer.stop();return
        now=time.monotonic()
        if self._recovery_task is not None:
            if now-self._recovery_started>25:
                self.cancel_recovery();self.retry_recovery('读取超时');return
            if not self._recovery_task.IsCompleted:return
            task=self._recovery_task;self._recovery_task=None
            try:
                value=json.loads(str(task.Result))
                if self._recovery_phase=='read' and isinstance(value,dict) and value.get('done'):
                    job=self._job;result=value.get('result') or {}
                    accepted=self.apply_recovery(result,job)
                    status=result.get('status');message=result.get('message','字幕归属核对失败，未显示本次结果')
                    self.cancel_recovery()
                    if not accepted:
                        if status=='waiting':
                            self._attempts=max(0,self._attempts-1);self._waiting_context=self.signature(self._context)
                            self.message='等待播放器切到当前视频，暂不显示字幕'
                        else:self.retry_recovery(message)
                    if not self._retry_at:self.timer.stop()
                    return
                token=json.dumps(self._recovery_token)
                self._recovery_task=self.browser.execute_script('(()=>{let s=window.__givtCaptionRecovery;return s&&s.token==='+token+'?{done:s.done,result:s.result}:null})()')
                self._recovery_phase='read'
            except Exception as exc:
                self.cancel_recovery();self.retry_recovery('字幕读取失败：'+str(exc)[:80])
            return
        if not self._retry_at or now<self._retry_at:
            if not self._retry_at:self.timer.stop()
            return
        self._retry_at=0.
        if not self._context or not page_identity(self.source()):self.timer.stop();return
        self._attempts+=1;self._recovery_started=now
        self._recovery_token=f'{self.epoch}-{self._attempts}-{now}'
        self._job=(self._recovery_token,self.epoch,self.signature(self._context),page_identity(self.source()))
        try:
            self._recovery_task=self.browser.execute_script(RECOVERY_SCRIPT.replace('TOKEN',json.dumps(self._recovery_token)).replace('EXPECTED',json.dumps(self._job[3])))
            self._recovery_phase='begin';self.message=f'正在核对当前视频字幕（{self._attempts}/5）'
        except Exception:self.cancel_recovery();self.retry_recovery('浏览器暂不可读')

    def poll_recovery(self,now):self.poll()
    def text_at(self,seconds):
        if not self.enabled or self._loaded_context!=self.signature(self._context) or self._loaded_page!=page_identity(self.source()):return ''
        return self.timeline.at(seconds)
    def direction_events(self,seconds,since=None):
        if not self.enabled or self._loaded_context!=self.signature(self._context) or self._loaded_page!=page_identity(self.source()):return []
        return self.timeline.direction_events(seconds,since)
    def close(self):
        self.cancel_recovery();self.enabled=False;self._closed=True;self.timer.stop();self.core=None
