"""Read caption data offered to the normal Bilibili player; no ASR or signing."""
import bisect
import concurrent.futures
import json
import math
import time
from urllib.parse import parse_qs, urlsplit, urlencode

from PySide6.QtCore import QObject, QTimer, Signal

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
    return {'code':document.get('code'),'data':{'need_login_subtitle':bool(data.get('need_login_subtitle')),
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
    changed=Signal()

    def __init__(self,browser,parent=None):
        super().__init__(parent)
        self.browser=browser;self.enabled=False;self.core=None;self.epoch=0
        self.video_key=None;self.timeline=CueTimeline();self.message='请打开 B 站视频，并开启播放器字幕'
        self.label='B站字幕';self._pending=[];self._records={};self._chosen=None
        self._executor=None;self._future=None;self._fetch_key=None;self._closed=False
        self._subscribed=False;self._handler=self.on_resource
        self._page_key=None
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.setInterval(150)
        browser.ready.connect(self.attach)
        browser.source_changed.connect(self.on_source_changed)
        browser.loading.connect(self.reset)

    def attach(self):
        self.core=self.browser.web.CoreWebView2
        self.update_subscription()

    def update_subscription(self):
        if self.core is None:return
        if self.enabled and not self._subscribed:
            self.core.WebResourceResponseReceived += self._handler;self._subscribed=True
        elif not self.enabled and self._subscribed:
            self.core.WebResourceResponseReceived -= self._handler;self._subscribed=False

    def set_enabled(self,enabled):
        enabled=bool(enabled)
        if self.enabled==enabled:return
        self.enabled=enabled
        self.update_subscription()
        if not enabled:self.reset()

    def reset(self,*args):
        self.epoch+=1;self.video_key=None;self.timeline=CueTimeline();self._records.clear();self._chosen=None
        self.message='请在软件内登录 B 站；播放器开启 AI/CC 字幕后可读取'
        # Outstanding tasks are drained, but their epoch no longer matches.
        if self._pending or self._future:self.timer.start()
        self.changed.emit()

    def on_source_changed(self,url):
        try:
            p=urlsplit(url);query=parse_qs(p.query)
            page=(p.hostname,p.path,query.get('p',['1'])[0],query.get('cid',[''])[0])
        except ValueError:page=None
        if page!=self._page_key:
            self._page_key=page;self.reset()

    def set_video(self,bvid,cid):
        cid=normalize_cid(cid)
        if not bvid or not cid:return
        key=(str(bvid),cid)
        if key!=self.video_key:
            self.video_key=key;self.timeline=CueTimeline();self._chosen=None
        record=self._records.get(cid)
        if record:self.use_player_data(record)

    def on_resource(self,sender,event):
        if not self.enabled or self._closed:return
        if not is_bilibili_page(str(self.browser.web.Source)):return
        try:
            p=urlsplit(str(event.Request.Uri))
            if p.hostname!='api.bilibili.com' or p.path not in PLAYER_PATHS:return
            cid=parse_qs(p.query).get('cid',[''])[0]
            if not cid.isdigit() or int(event.Response.StatusCode)!=200:return
            page=urlsplit(str(self.browser.web.Source));page_query=parse_qs(page.query)
            if page.hostname=='player.bilibili.com' and page.path=='/player.html':
                expected=page_query.get('cid',[''])[0]
                if expected and expected!=cid:return
                bvid=page_query.get('bvid',[''])[0]
                if bvid:self.set_video(bvid,cid)
            if len(self._pending)>=2:return
            task=event.Response.GetContentAsync()
            self._pending.append((self.epoch,cid,task,time.monotonic()))
            self.timer.start()
        except Exception:
            self.message='B站字幕信息读取失败，请刷新页面后重试'

    def use_player_data(self,document):
        if document.get('code')!=0:
            self.message='B站未提供可读字幕，请检查登录状态或刷新页面';return
        data=document.get('data') or {}
        if data.get('need_login_subtitle'):
            self.message='这集字幕需要登录：请在软件内登录 B站，再点“刷新字幕”'
            return
        track=choose_track((data.get('subtitle') or {}).get('subtitles',[]))
        if not track:
            self.message='这集暂未提供可读 AI/CC 字幕；可先在 B站播放器检查字幕选项'
            return
        url=track['subtitle_url'];key=(self.epoch,self.video_key,url)
        if key==self._chosen:return
        if self._future is not None:return
        self._chosen=key;self._fetch_key=key
        self.label='B站 · '+str(track.get('lan_doc') or track.get('lan') or '字幕')[:60]
        self.message='正在读取 B站提供的字幕文本…'
        if self._executor is None:self._executor=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='bili-caption')
        self._future=self._executor.submit(fetch_caption,url);self.timer.start()

    def poll(self):
        for entry in list(self._pending):
            epoch,cid,task,started=entry
            if not task.IsCompleted:
                if time.monotonic()-started>20:self.message='B站字幕响应较慢，请稍后刷新'
                continue
            self._pending.remove(entry)
            try:
                from System import Array,Byte
                stream=task.Result
                if stream is None:continue
                try:
                    chunk=Array.CreateInstance(Byte,65536);parts=[];total=0
                    while True:
                        count=stream.Read(chunk,0,len(chunk))
                        if not count:break
                        total+=count
                        if total>MAX_BYTES:raise ValueError('播放器响应过大')
                        parts.append(bytes(chunk)[:count])
                finally:stream.Dispose()
                if epoch!=self.epoch or not self.enabled:continue
                document=json.loads(b''.join(parts).decode('utf-8-sig'))
                if not isinstance(document,dict):continue
                document=player_record(document);self._records[cid]=document
                if len(self._records)>2:self._records.pop(next(iter(self._records)))
                if self.video_key and cid==self.video_key[1]:self.use_player_data(document)
                self.changed.emit()
            except Exception:
                if epoch==self.epoch:self.message='字幕信息读取失败，请刷新字幕重试'
        if self._future is not None and self._future.done():
            future,key=self._future,self._fetch_key;self._future=None;self._fetch_key=None
            if self.enabled and key[0]==self.epoch and key[1]==self.video_key:
                try:
                    self.timeline=CueTimeline(future.result())
                    self.message=f'{self.label} · 已载入 {len(self.timeline.cues)} 条字幕，无本地推理'
                except Exception:
                    self.message='字幕文本加载失败，请点“刷新字幕”重试'
                self.changed.emit()
        if not self._pending and self._future is None:
            self.timer.stop()
            if self._executor is not None:
                self._executor.shutdown(wait=False);self._executor=None

    def text_at(self,seconds):
        return self.timeline.at(seconds) if self.enabled else ''

    def close(self):
        self._closed=True;self.enabled=False;self.epoch+=1;self.timer.stop()
        if self.core is not None:
            try:
                if self._subscribed:self.core.WebResourceResponseReceived -= self._handler
            except Exception:pass
            self.core=None
        if self._executor is not None:self._executor.shutdown(wait=False,cancel_futures=True)
        for _,_,task,_ in self._pending:
            if task.IsCompleted:
                try:
                    if task.Result is not None:task.Result.Dispose()
                except Exception:pass
        self._pending.clear()
