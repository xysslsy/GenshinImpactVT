"""Non-blocking WebView2 snapshot -> isolated OCR -> direction overlay."""
import json
import multiprocessing as mp
import queue
import time
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urlencode

from PySide6.QtCore import QObject, QTimer, QBuffer, QByteArray, QIODevice, QRect, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog

from .ocr_engine import worker
from .subtitle_text import DEFAULT_REGION, StableText, valid_region
from .subtitle_ui import SubtitlePage, RegionDialog
from .bilibili_subtitles import BilibiliSubtitleFeed, is_bilibili_page, official_player_url


# Query only active cues and *visible* rendered subtitles, never the transcript panel.
PAGE_SCRIPT = r'''(()=>{
 const timingOnly=false;
 const visible=e=>{let r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)!==0};
 const all=timingOnly?[]:Array.from(document.querySelectorAll('video')).filter(visible);
 const v=timingOnly?(document.querySelector('.bpx-player-video-wrap video')||document.querySelector('video')):all.sort((a,b)=>b.clientWidth*b.clientHeight-a.clientWidth*a.clientHeight)[0];
 if(!v)return null;
 if(!v.__givtId){v.__givtId=String(Date.now())+Math.random();v.__givtEpoch=0;v.addEventListener('seeking',()=>v.__givtEpoch++);v.addEventListener('emptied',()=>v.__givtEpoch++);}
 let cues=[];if(!timingOnly){for(const t of v.textTracks){if(t===window.__genshinimpactvtCaptionTrack)continue;if(t.mode!=='disabled'&&t.activeCues)for(const c of t.activeCues)cues.push(c.text||'');}
 if(!cues.length)cues=Array.from(document.querySelectorAll('.bpx-player-subtitle-item-text,.bilibili-player-video-subtitle span,.bili-subtitle-x-subtitle-panel-major-group,.bili-subtitle-x-subtitle-panel-minor-group')).filter(visible).map(e=>e.textContent||'');}
 const state=window.__INITIAL_STATE__||{};
 const params=new URL(location.href).searchParams;
 const r=timingOnly?{width:0,height:0,x:0,y:0}:v.getBoundingClientRect();let w=r.width,h=r.height,x=r.x,y=r.y;
 if(!timingOnly&&v.videoWidth&&v.videoHeight&&getComputedStyle(v).objectFit==='contain'){
  let k=Math.min(w/v.videoWidth,h/v.videoHeight),nw=v.videoWidth*k,nh=v.videoHeight*k;x+=(w-nw)/2;y+=(h-nh)/2;w=nw;h=nh;
 }
 return {id:location.href+'|'+v.__givtId+'|'+v.currentSrc,epoch:v.__givtEpoch,time:v.currentTime,paused:v.paused,
 seeking:v.seeking,ended:v.ended,ready:v.readyState,text:cues.join(' ').slice(0,500),
 bili:{bvid:state.bvid||state.videoData?.bvid||params.get('bvid'),cid:state.cid||state.videoData?.cid||params.get('cid')},
 rect:[x,y,w,h],viewport:[innerWidth,innerHeight]};
})()'''
TIMING_SCRIPT = PAGE_SCRIPT.replace('const timingOnly=false;','const timingOnly=true;')


def image_bytes(image):
    data = QByteArray(); buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly); image.save(buffer, 'PNG'); buffer.close()
    return bytes(data)


def video_image(image, metadata):
    """Map CSS viewport coordinates to actual capture pixels, including high DPI."""
    x,y,w,h = metadata['rect']; vw,vh = metadata['viewport']
    if vw <= 0 or vh <= 0 or w <= 0 or h <= 0:
        raise ValueError('视频尺寸无效')
    sx,sy = image.width()/vw,image.height()/vh
    rect = QRect(round(x*sx),round(y*sy),round(w*sx),round(h*sy))
    # Partially offscreen video cannot be treated as the full video for ROI mapping.
    # CSS layout may have fractional pixels while innerWidth/Height are integers.
    # Allow at most two capture pixels of rounding, not genuinely cropped videos.
    if not image.rect().adjusted(-2,-2,2,2).contains(rect) or rect.width()<32 or rect.height()<24:
        raise ValueError('请将视频完整显示在浏览器内，再识别字幕')
    return image.copy(rect.intersected(image.rect()))


def crop_region(image, region):
    x,y,w,h = valid_region(region)
    rect = QRect(round(x*image.width()),round(y*image.height()),
                 max(1,round(w*image.width())),max(1,round(h*image.height())))
    return image.copy(rect.intersected(image.rect()))


class SubtitleController(QObject):
    enabled_changed = Signal(bool)
    caption_changed = Signal(str,str)

    def __init__(self, browser, compass, settings, parent):
        super().__init__(parent)
        self.browser,self.compass,self.settings = browser,compass,settings
        self.enabled = settings.value('subtitles/enabled', settings.value('compass/enabled', False, type=bool), type=bool)
        self.mode = settings.value('subtitles/mode', 'auto')
        if self.mode not in ('auto','dom','ocr'): self.mode = 'auto'
        self.ocr_available = not (Path(__file__).resolve().parents[1]/'assets'/'lightweight.flag').exists()
        if self.mode == 'ocr' and not self.ocr_available: self.mode = 'auto'
        self.interval = settings.value('subtitles/interval', 500, type=int)
        if self.interval not in (350,500,1000): self.interval = 500
        try: self.region = valid_region(json.loads(settings.value('subtitles/region', 'null')))
        except (TypeError,ValueError): self.region = DEFAULT_REGION
        self.page = SubtitlePage(self.enabled,self.mode,self.interval,self.ocr_available)
        self.native_feed = BilibiliSubtitleFeed(browser,self)
        self.native_feed.set_enabled(self.enabled and self.mode == 'auto')
        self.page.enabled.toggled.connect(self.set_enabled)
        self.page.mode.currentIndexChanged.connect(self.change_mode)
        self.page.interval.currentIndexChanged.connect(self.change_interval)
        self.page.pick.clicked.connect(self.pick_region)
        self.page.reset.clicked.connect(self.reset_region)
        self.page.demo.clicked.connect(self.open_demo)
        self.page.refresh.clicked.connect(self.refresh_subtitles)
        self.page.player.clicked.connect(self.open_official_player)
        self.page.full_page.clicked.connect(self.return_full_page)
        self.gate = StableText(); self.generation = 0; self._source = ''
        self._caption_state=('','')
        self._metadata = None; self._identity = None; self._epoch = None
        self._page_task = None; self._capture = None; self._capture_for_picker = False
        self._page_generation = 0
        self._page_started = self._capture_started = 0.
        self._last_frame = 0.; self._last_time = None; self._last_wall = 0.
        self._closed = False; self._picker = None; self._pick_requested = False
        self._process = None; self._requests = self._replies = None
        self._worker_ready = False; self._worker_busy = False; self._worker_failed = False
        self._worker_started = 0.; self._job = None; self._token = 0
        self.samples = 0; self.last_latency_ms = None
        browser.source_changed.connect(self.reset_timeline)
        browser.loading.connect(self.reset_timeline)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.setInterval(300)
        if self.enabled:self.timer.start()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled); self.settings.setValue('subtitles/enabled', self.enabled)
        self.reset_timeline(); self._worker_failed = False
        self.native_feed.set_enabled(self.enabled and self.mode == 'auto')
        if enabled:self.timer.start()
        if not enabled:
            self.stop_worker(); self.page.status.setText('字幕识别已关闭')
        self.enabled_changed.emit(self.enabled)

    def change_mode(self):
        self.mode = self.page.mode.currentData(); self.settings.setValue('subtitles/mode', self.mode)
        self.reset_timeline(); self._worker_failed = False
        self.native_feed.set_enabled(self.enabled and self.mode == 'auto')
        if self.mode != 'ocr': self.stop_worker()

    def change_interval(self):
        self.interval = self.page.interval.currentData(); self.settings.setValue('subtitles/interval', self.interval)

    def reset_region(self):
        self.region = DEFAULT_REGION; self.save_region(); self.page.preview.setText('已恢复视频下方默认区域')

    def save_region(self):
        self.settings.setValue('subtitles/region', json.dumps(self.region)); self.reset_timeline()

    def reset_timeline(self, *args):
        self.generation += 1; self.gate.reset(); self.compass.clear(); self.page.text.setText('—')
        self.publish_caption('','')
        self._source = ''; self._last_time = None; self._metadata = None

    def publish_caption(self,text,source):
        value=str(text or '').strip()[:500]
        state=(value,source if value else '')
        if state!=self._caption_state:
            self._caption_state=state;self.caption_changed.emit(*state)

    def pick_region(self):
        self.parent().select(0)
        self.reset_timeline()
        self._pick_requested = True; self.page.status.setText('正在获取视频快照…')
        self.timer.start()

    def refresh_subtitles(self):
        self.native_feed.reset()
        self.reset_timeline(); self.browser.reload()

    def open_official_player(self):
        key=self.native_feed.video_key
        if not key:
            self.page.status.setText('请先打开 B站视频并等待视频信息加载');return
        page=parse_qs(urlsplit(self.parent().address.text()).query).get('p',['1'])[0]
        self.parent().open_url(official_player_url(key[0],page,key[1]))

    def return_full_page(self):
        url=urlsplit(self.parent().address.text());query=parse_qs(url.query)
        key=self.native_feed.video_key
        bvid=key[0] if key else query.get('bvid',[''])[0]
        if not bvid:
            self.page.status.setText('请先打开 B站视频');return
        page=query.get('p',['1'])[0]
        self.parent().open_url('https://www.bilibili.com/video/'+bvid+'/?'+urlencode({'p':page}))

    def open_demo(self):
        self.parent().select(0)
        self.browser.navigate((Path(__file__).resolve().parents[1]/'assets'/'subtitle-test.html').as_uri())

    def start_worker(self):
        if not self.ocr_available or self.mode != 'ocr' or self._process is not None or self._worker_failed: return
        ctx = mp.get_context('spawn')
        self._requests = ctx.Queue(maxsize=1); self._replies = ctx.Queue(maxsize=2)
        self._process = ctx.Process(target=worker,args=(self._requests,self._replies),daemon=True)
        try:
            self._process.start()
        except Exception as exc:
            # An unstarted Process cannot be joined or queried with is_alive().
            self._process = None
            self.worker_error('无法启动识别进程：'+str(exc)[:150])
            return
        self._worker_started = time.monotonic()
        self.page.status.setText('正在加载本地 OCR 模型…')

    def stop_worker(self):
        if self._process is not None:
            if self._process.is_alive(): self._process.terminate()
            self._process.join(timeout=1)
            if not self._process.is_alive(): self._process.close()
        for channel in (self._requests,self._replies):
            if channel is not None: channel.cancel_join_thread(); channel.close()
        self._process = self._requests = self._replies = None
        self._worker_ready = self._worker_busy = False; self._job = None

    def worker_error(self, text):
        self.stop_worker(); self._worker_failed = True
        self.page.status.setText('OCR 不可用：'+text+'。网页字幕仍可使用；修复后关闭再开启识别。')

    def read_replies(self, now):
        if self._replies is None: return
        for _ in range(3):
            try: reply = self._replies.get_nowait()
            except queue.Empty: break
            if reply[0] == 'ready':
                self._worker_ready = True
            elif reply[0] == 'error':
                self.worker_error(reply[1]); return
            elif reply[0] == 'result':
                self._worker_busy = False
                _,token,generation,text,inference = reply
                job,self._job = self._job,None
                if not job or token != job[0] or generation != self.generation or now-job[1] > 2.5:
                    continue
                if not self.enabled or not self._metadata or self._metadata['seeking']: continue
                if self.mode == 'auto' and self._metadata['text'].strip(): continue
                self.samples += 1; self.last_latency_ms = round((now-job[1])*1000)
                self.deliver(text,'ocr')
                self.page.status.setText(f'画面 OCR · 端到端 {self.last_latency_ms} ms · 推理 {inference} ms')
        if self._process and not self._process.is_alive(): self.worker_error('识别进程已退出')
        elif not self._worker_ready and now-self._worker_started > 45: self.worker_error('模型加载超时')
        elif self._job and now-self._job[1] > 10: self.worker_error('单次识别超时')

    def deliver(self, text, source):
        if source != self._source:
            self._source = source; self.gate.reset()
        accepted = self.gate.observe(text,source)
        self.page.text.setText(text or '未识别到字幕')
        self.publish_caption(text,source)
        if accepted is not None: self.compass.set_text(accepted)
        elif not text: self.compass.clear()

    def read_page(self, now):
        if self._page_task is not None:
            if not self._page_task.IsCompleted:
                if now-self._page_started > 8: self.page.status.setText('网页响应超时，请刷新页面')
                return
            task,self._page_task = self._page_task,None
            try:
                if self._page_generation != self.generation:
                    return
                metadata = json.loads(str(task.Result))
                if metadata is None:
                    if self._metadata is not None: self.reset_timeline()
                    self._metadata = None
                    if self.enabled or self._pick_requested: self.page.status.setText('请先打开视频，并让视频完整显示在窗口内')
                    self._pick_requested = False
                else:
                    identity,epoch = metadata['id'],metadata['epoch']
                    jumped = (self._last_time is not None and (metadata['time'] < self._last_time-.5 or
                              abs(metadata['time']-self._last_time) > max(2.,(now-self._last_wall)*4+1)))
                    if identity != self._identity or epoch != self._epoch or jumped:
                        self.reset_timeline()
                    self._identity,self._epoch = identity,epoch
                    self._last_time,self._last_wall = metadata['time'],now
                    self._metadata = metadata
                    bili = metadata.get('bili') or {}
                    self.native_feed.set_video(bili.get('bvid'),bili.get('cid'))
                    if metadata['seeking'] or metadata['ended']:
                        self.compass.clear(); self.gate.reset();self.publish_caption('','');self.page.text.setText('—')
                    elif self.enabled and self.mode != 'ocr' and metadata['text'].strip():
                        self.deliver(metadata['text'],'dom'); self.page.status.setText('正在读取网页字幕')
                    elif self.enabled and self.mode == 'dom':
                        self.deliver('','dom'); self.page.status.setText('当前没有可读取的网页字幕，可切换自动或 OCR')
                    elif self.enabled and self.mode == 'auto':
                        self.deliver(self.native_feed.text_at(metadata['time']),'platform')
                        if is_bilibili_page(str(self.browser.web.Source)):
                            self.page.status.setText(self.native_feed.message)
                        else:self.page.status.setText('当前无网页字幕；B站 AI/CC 字幕需在 B站视频页面使用')
            except Exception as exc:
                self.reset_timeline(); self.page.status.setText('读取视频信息失败：'+str(exc)[:150])
        if self._page_task is None:
            try:
                script = TIMING_SCRIPT if self.mode == 'auto' and self.native_feed.timeline.cues and not self._pick_requested else PAGE_SCRIPT
                self._page_task = self.browser.execute_script(script); self._page_started = now
                self._page_generation = self.generation
            except Exception: pass

    def poll_capture(self, now):
        if self._capture is None: return
        task,stream,generation,metadata,picker = self._capture
        if not task.IsCompleted:
            if now-self._capture_started > 8: self.page.status.setText('视频截图超时，请刷新页面后重试')
            return
        self._capture = None
        try:
            task.GetAwaiter().GetResult()
            image = QImage.fromData(bytes(stream.ToArray()), 'PNG')
            if image.isNull(): raise ValueError('浏览器返回了空截图')
            image = video_image(image,metadata)
            if generation != self.generation: return
            if picker:
                self._picker = RegionDialog(image,self.region,self.parent())
                self._picker.finished.connect(self.region_picked); self._picker.open()
                return
            cropped = crop_region(image,self.region); self.page.set_preview(cropped)
            if not self.enabled or self.mode == 'dom' or not self._worker_ready or self._worker_busy: return
            # Modest enlargement helps small glyphs; cap width to bound inference work.
            if cropped.width() < 960: cropped = cropped.scaledToWidth(min(1600,cropped.width()*2))
            self._token += 1
            self._requests.put_nowait((self._token,generation,image_bytes(cropped)))
            self._job = (self._token,self._capture_started); self._worker_busy = True
        except queue.Full: pass
        except Exception as exc: self.page.status.setText('字幕截图失败：'+str(exc)[:200])
        finally: stream.Dispose()

    def region_picked(self, result):
        dialog,self._picker = self._picker,None
        if result == QDialog.DialogCode.Accepted:
            self.region = valid_region(dialog.canvas.region); self.save_region()
            self.page.set_preview(crop_region(dialog.canvas.image,self.region))
        dialog.deleteLater()
        if not self._closed: self.parent().select(self.page_index)

    def tick(self):
        if self._closed or self._picker is not None: return
        now = time.monotonic()
        if self._capture is not None: self.poll_capture(now)
        if self._picker is not None: return
        if not (self.enabled or self._pick_requested):
            if self._capture is None:self.timer.stop()
            return
        self.read_page(now); self.read_replies(now)
        meta = self._metadata
        if not meta or meta['seeking'] or meta['ended'] or meta['ready'] < 2: return
        if self.mode != 'ocr':self.timer.setInterval(700 if meta['paused'] else 300)
        else:self.timer.setInterval(300)
        if self._capture is not None: return
        picker = self._pick_requested
        if not picker:
            if self.mode != 'ocr': return
            if self.parent().isMinimized() or not self.parent().isVisible():
                self.compass.clear(); self.page.status.setText('主窗口隐藏或最小化，画面识别已暂停'); return
            self.start_worker()
            if not self._worker_ready or self._worker_busy or self._worker_failed: return
            if now-self._last_frame < self.interval/1000: return
        try:
            task,stream = self.browser.capture_preview()
            self._capture = (task,stream,self.generation,dict(meta),picker)
            self._capture_started = self._last_frame = now; self._pick_requested = False
        except Exception as exc:
            self._pick_requested = False; self.page.status.setText('无法获取视频画面：'+str(exc)[:150])

    def close(self):
        self._closed = True; self.timer.stop(); self.stop_worker(); self.native_feed.close()
        if self._picker is not None: self._picker.reject()
        if self._capture is not None:
            self._capture[1].Dispose(); self._capture = None
