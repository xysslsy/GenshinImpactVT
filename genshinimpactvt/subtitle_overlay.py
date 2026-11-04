"""Event-driven captions inside WebView2; no extra Qt window or video polling."""
import json

from PySide6.QtCore import QObject


# Runs in the current document. Keep rendering in the browser compositor rather
# than trying to paint a transparent Qt child over the native WinForms HWND.
OVERLAY_SCRIPT = r"""
(() => {
  const text = __CAPTION_JSON__;
  const key = '__genshinimpactvtCaptionOverlay';
  let state = window[key];
  if (!state) {
    const host = document.createElement('div');
    host.id = 'genshinimpactvt-caption-overlay';
    host.setAttribute('aria-hidden', 'true');
    const root = host.attachShadow({mode: 'open'});
    const style = document.createElement('style');
    style.textContent = `
      :host {all:initial;pointer-events:none!important;background:transparent!important;}
      .caption {position:absolute;left:5%;right:5%;bottom:9%;margin:0;
        text-align:center;color:white;background:transparent;white-space:pre-line;
        overflow-wrap:anywhere;font-family:"Microsoft YaHei UI",sans-serif;
        font-weight:600;line-height:1.4;text-shadow:0 1px 3px #000,1px 0 2px #000,
        -1px 0 2px #000,0 -1px 2px #000;pointer-events:none;user-select:none;
        max-height:40%;overflow:hidden;}
    `;
    const label = document.createElement('div');
    label.className = 'caption';
    root.append(style, label);
    const cueStyle = document.createElement('style');
    cueStyle.textContent = 'video::cue(.givt-overlay){background:transparent;color:white;text-shadow:0 1px 3px black;}';
    document.documentElement.appendChild(cueStyle);
    state = {host, label, text:'', video:null, frame:0, track:null, tracks:new WeakMap()};
    window[key] = state;
    state.hideTrack = () => {
      if (state.track) {
        // Disabled tracks may expose cues as null; clear while hidden first.
        state.track.mode = 'hidden';
        for (const cue of Array.from(state.track.cues || [])) state.track.removeCue(cue);
        state.track.mode = 'disabled';
      }
    };
    state.place = () => {
      state.frame = 0;
      if (!state.text) {host.remove();state.hideTrack();return;}
      const videos = Array.from(document.querySelectorAll('video')).filter(v => {
        const r = v.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(v).visibility !== 'hidden';
      });
      const v = videos.sort((a,b) => b.clientWidth*b.clientHeight-a.clientWidth*a.clientHeight)[0];
      if (state.video !== v) {
        state.hideTrack();state.track = state.tracks.get(v) || null;state.resize.disconnect();
        if (state.video) state.video.removeEventListener('loadedmetadata', state.schedule);
        state.video = v;
        if (v) {state.resize.observe(v);v.addEventListener('loadedmetadata', state.schedule);}
      }
      if (!v) {host.remove();return;}
      const fs = document.fullscreenElement;
      // A video element itself cannot display DOM children. Use a dedicated cue
      // track only for that native fullscreen case, excluded by our reader.
      if (fs === v) {
        host.remove();
        if (!state.track) {
          state.track = v.addTextTrack('subtitles', 'GenshinImpactVT overlay', 'zh');
          state.tracks.set(v,state.track);
        }
        window.__genshinimpactvtCaptionTrack = state.track;
        state.track.mode = 'hidden';
        const safeText = '<c.givt-overlay>'+state.text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</c>';
        if (!state.track.cues.length || state.track.cues[0].text !== safeText) {
          state.hideTrack();
          const cue = new VTTCue(0, 1e10, safeText);cue.line = -3;
          state.track.addCue(cue);
        }
        state.track.mode = 'showing';return;
      }
      state.hideTrack();
      const parent = fs || document.documentElement;
      if (host.parentNode !== parent) parent.appendChild(host);
      const r = v.getBoundingClientRect();
      const left = Math.max(0,r.left), top = Math.max(0,r.top);
      const width = Math.max(0,Math.min(innerWidth,r.right)-left);
      const height = Math.max(0,Math.min(innerHeight,r.bottom)-top);
      host.style.cssText = `all:initial;display:block;position:fixed;left:${left}px;top:${top}px;
        width:${width}px;height:${height}px;z-index:2147483647;pointer-events:none;
        background:transparent;border:0;margin:0;padding:0;overflow:hidden;`;
      state.label.style.fontSize = Math.max(14,Math.min(28,r.width/32))+'px';
    };
    state.schedule = () => {
      if (state.text && !state.frame) state.frame = requestAnimationFrame(state.place);
    };
    state.resize = new ResizeObserver(state.schedule);
    addEventListener('resize',state.schedule);
    addEventListener('scroll',state.schedule,true);
    document.addEventListener('fullscreenchange',state.schedule);
    // All listeners/observers are document-scoped and disappear on navigation.
  }
  state.text = text;state.label.textContent = text;
  if (!text) {
    if (state.frame) cancelAnimationFrame(state.frame);
    state.frame = 0;state.resize.disconnect();
    if (state.video) state.video.removeEventListener('loadedmetadata',state.schedule);
    state.video = null;
    state.host.remove();state.hideTrack();
  } else state.place();
  return true;
})()
"""


class SubtitleOverlay(QObject):
    def __init__(self, browser, parent=None):
        super().__init__(parent)
        self.browser = browser
        self.enabled = False
        self.visible = True
        self.current = ''
        self.source = ''
        self.last_error = ''
        browser.loading.connect(self.clear)

    def clear(self):
        self.set_caption('', '')

    def set_recognition_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            self.clear()

    def set_visible(self, visible):
        self.visible = bool(visible)
        self.render()

    def set_caption(self, text, source):
        self.current = str(text or '').strip()[:500] if self.enabled else ''
        self.source = str(source or '') if self.current else ''
        self.render()

    def render(self):
        text = self.current if self.enabled and self.visible else ''
        script = OVERLAY_SCRIPT.replace('__CAPTION_JSON__', json.dumps(text, ensure_ascii=True))
        try:
            self.browser.execute_script(script)
            self.last_error = ''
        except RuntimeError as exc:
            # No live document during initialization, navigation or shutdown.
            self.last_error = str(exc)
