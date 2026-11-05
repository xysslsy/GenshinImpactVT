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

RECOVERY_SCRIPT=Path(__file__).with_name('caption_recovery.js').read_text(encoding='utf-8')
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
    changed=Signal()

    def __init__(self,browser,parent=None):
        super().__init__(parent)
        self.browser=browser;self.enabled=False;self.core=None;self.epoch=0
        self.video_key=None;self.timeline=CueTimeline();self.message='请打开 B 站视频，并开启播放器字幕'
        self.label='B站字幕';self._pending=[];self._records={};self._chosen=None
        self._executor=None;self._future=None;self._fetch_key=None;self._closed=False
        self._subscribed=False;self._handler=self.on_resource
        self._page_key=None
        self._recovery_task=None;self._recovery_phase='';self._recovery_token=''
        self._attempts=0;self._retry_at=0.;self._recovery_started=0.
        self._resolved_page=None;self._resolved_key=None
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.setInterval(150)
        browser.ready.connect(self.attach)
        browser.source_changed.connect(self.on_source_changed)
        browser.loading.connect(self.reset)

    def attach(self):
        self.core=self.browser.web.CoreWebView2
        self.update_subscription()
        if self.enabled:self.request_recovery()

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
        self.reset()

    def reset(self,*args):
        self.cancel_recovery()
        self.epoch+=1;self.video_key=None;self.timeline=CueTimeline();self._records.clear();self._chosen=None
        self._attempts=0;self._retry_at=0.;self._resolved_page=None;self._resolved_key=None
        self.message='请在软件内登录 B 站；播放器开启 AI/CC 字幕后可读取'
        # Outstanding tasks are drained, but their epoch no longer matches.
        if self._pending or self._future:self.timer.start()
        self.request_recovery()
        self.changed.emit()

    def on_source_changed(self,url):
        try:
            p=urlsplit(url);query=parse_qs(p.query)
            page=page_identity(url) or (p.hostname,p.path)
        except ValueError:page=None
        if page!=self._page_key:
            self._page_key=page;self.reset()

    def set_video(self,bvid,cid):
        cid=normalize_cid(cid)
        if not bvid or not cid:return
        identity=page_identity(str(getattr(self.browser.web,'Source','') or ''))
        if identity and str(bvid)!=identity[0]:return
        key=self._resolved_key if self._resolved_page==identity and self._resolved_key else (str(bvid),cid)
        if key!=self.video_key:
            self.video_key=key;self.timeline=CueTimeline();self._chosen=None
        record=self._records.get(key[1])
        if record:self.use_player_data(record)
        if not self.timeline.cues:self.request_recovery()

    def on_resource(self,sender,event):
        if not self.enabled or self._closed:return
        if not is_bilibili_page(str(getattr(self.browser.web,'Source','') or '')):return
        try:
            p=urlsplit(str(event.Request.Uri))
            if p.hostname!='api.bilibili.com' or p.path not in PLAYER_PATHS:return
            cid=parse_qs(p.query).get('cid',[''])[0]
            if not cid.isdigit() or int(event.Response.StatusCode)!=200:return
            page=urlsplit(str(getattr(self.browser.web,'Source','') or ''));page_query=parse_qs(page.query)
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
        if self.timeline.cues:return
        data=document.get('data') or {}
        if self.video_key and ((data.get('cid') and normalize_cid(data['cid'])!=self.video_key[1]) or
                               (data.get('bvid') and data['bvid']!=self.video_key[0])):
            self.message='播放器返回的分 P 信息不一致，正在重新读取'
            self.request_recovery();return
        if document.get('code')!=0:
            self.message='B站未提供可读字幕，请检查登录状态或刷新页面';return
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
                if time.monotonic()-started>20:
                    self._pending.remove(entry)
                    self.message='播放器响应超时，正在自动重试字幕'
                    self.request_recovery()
                continue
            self._pending.remove(entry)
            try:
                from System import Array,Byte
                stream=task.Result
                if stream is None:continue
                if epoch!=self.epoch or not self.enabled:
                    stream.Dispose();continue
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
            if self.enabled and key[0]==self.epoch and key[1]==self.video_key and not self.timeline.cues:
                try:
                    cues=future.result()
                    if not cues:raise ValueError("Empty caption timeline")
                    self.timeline=CueTimeline(cues)
                    self.message=f'{self.label} · 已载入 {len(self.timeline.cues)} 条字幕，无本地推理'
                except Exception:
                    self.message='字幕文本加载失败，正在自动重试'
                    self.request_recovery()
                self.changed.emit()
        self.poll_recovery(time.monotonic())
        if not self._pending and self._future is None:
            if self._recovery_task is None and not self._retry_at:self.timer.stop()
            if self._executor is not None:
                self._executor.shutdown(wait=False);self._executor=None

    def cancel_recovery(self):
        token=self._recovery_token
        if token:
            try:self.browser.execute_script("(()=>{let s=window.__givtCaptionRecovery;if(s&&s.token==="+json.dumps(token)+"){s.abort.abort();delete window.__givtCaptionRecovery}})()")
            except Exception:pass
        self._recovery_task=None;self._recovery_token='';self._retry_at=0.

    def request_recovery(self, immediate=False):
        if self._closed or not self.enabled or self.timeline.cues:return
        if not page_identity(str(getattr(self.browser.web,'Source','') or '')):return
        if self._attempts>=4 or self._recovery_task is not None:return
        if not self._retry_at:self._retry_at=time.monotonic()+(.0 if immediate else .4)
        self.timer.start()

    def refresh(self):
        self.reset()
        if self.enabled:
            self._retry_at=time.monotonic();self.timer.start()
            self.message='正在重新读取当前视频字幕，视频不会刷新'

    def retry_recovery(self, message):
        if self.timeline.cues:self._retry_at=0.;return
        if self._attempts<4:
            delay=RETRY_DELAYS[max(0,self._attempts-1)]
            self._retry_at=time.monotonic()+delay
            self.message=message+f'；{int(delay)} 秒后自动重试（{self._attempts}/4）'
        else:
            self._retry_at=0.
            self.message=message+'；自动重试已结束，可点“重试字幕”'
        self.changed.emit()

    def apply_recovery(self, result):
        identity=page_identity(str(getattr(self.browser.web,'Source','') or ''))
        if not identity or not isinstance(result,dict):return
        key=result.get('key') or {}
        cid=normalize_cid(key.get('cid'))
        if key and (key.get('bvid')!=identity[0] or key.get('page')!=identity[1] or (identity[2] and cid!=identity[2])):return
        status=result.get('status')
        if status=='ok' and cid:
            cues=parse_cues(result.get('caption'))
            if not cues:self.retry_recovery('平台返回空字幕');return
            self._resolved_page=identity;self._resolved_key=(identity[0],cid)
            self.video_key=self._resolved_key;self.timeline=CueTimeline(cues)
            self.label='B站 · '+str(result.get('label','字幕'))[:60]
            self.message=f'{self.label} · 已载入 {len(cues)} 条字幕，无本地推理'
            self._retry_at=0.;self.changed.emit();return
        if self.timeline.cues:return
        if status=='login':message='这集字幕需要登录，请在软件内正常登录 B站'
        elif status=='no_tracks':message='平台暂未提供这集可读的 AI/CC 字幕'
        elif status=='platform':
            code=result.get('code')
            if code==-101:message='B站登录已失效，请在软件内重新登录'
            elif code==-412:message='B站暂时限制请求，请稍后重试'
            else:message='平台暂未返回可读字幕（代码 '+str(code)[:12]+'）'
        else:message='字幕请求超时或网络暂不可用'
        self.retry_recovery(message)

    def poll_recovery(self, now):
        if self._closed or not self.enabled:return
        if self.timeline.cues:
            self._retry_at=0.
            if self._recovery_task is not None:self.cancel_recovery()
            return
        if self._recovery_task is not None:
            if now-self._recovery_started>22:
                self.cancel_recovery();self.retry_recovery('字幕请求超时');return
            if not self._recovery_task.IsCompleted:return
            task=self._recovery_task;self._recovery_task=None
            try:
                value=json.loads(str(task.Result))
                if self._recovery_phase=='read' and isinstance(value,dict) and value.get('done'):
                    self.cancel_recovery()
                    self.apply_recovery(value.get('result'));return
                token=json.dumps(self._recovery_token)
                self._recovery_task=self.browser.execute_script('(()=>{let s=window.__givtCaptionRecovery;return s&&s.token==='+token+'?{done:s.done,result:s.result}:null})()')
                self._recovery_phase='read'
            except Exception:self.cancel_recovery();self.retry_recovery('字幕读取暂不可用')
            return
        if not self._retry_at or now<self._retry_at:return
        self._retry_at=0.
        if not page_identity(str(getattr(self.browser.web,'Source','') or '')):return
        if self.core is None:return  # attach() schedules again when the engine is ready.
        self._attempts+=1;self._recovery_started=now
        self._recovery_token=f'{self.epoch}-{self._attempts}-{now}'
        try:
            self._recovery_task=self.browser.execute_script(RECOVERY_SCRIPT.replace('TOKEN',json.dumps(self._recovery_token)))
            self._recovery_phase='begin'
            self.message=f'正在读取当前视频字幕（{self._attempts}/4）…'
        except Exception:self.retry_recovery('浏览器尚未准备好读取字幕')

    def text_at(self,seconds):
        return self.timeline.at(seconds) if self.enabled else ''

    def close(self):
        self.cancel_recovery()
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
