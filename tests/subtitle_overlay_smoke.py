"""Real WebView2 integration: rendering, hit testing, fullscreen and small window.

Uses only a local generated video and an isolated browser/application profile.
"""
import ctypes
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT/'.test-overlay'
DATA.mkdir(exist_ok=True)
os.environ['LOCALAPPDATA'] = str(DATA)

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication
from main import Main, STYLE


def main():
    settings = QSettings(str(DATA/'app'/'settings.ini'), QSettings.Format.IniFormat)
    for key in ('mouse/enabled', 'episode_keys/enabled', 'subtitles/enabled'):
        settings.setValue(key, False)
    settings.setValue('browser/last_url', '')
    settings.setValue('window/compact', False)
    settings.setValue('subtitles/show_footer', True)
    settings.sync()
    ole = ctypes.OleDLL('ole32')
    ole.OleInitialize(None)
    app = QApplication([])
    app.setStyleSheet(STYLE)
    win = Main(DATA/'app')
    win.resize(960, 620)
    checks = {}
    errors = []
    win.browser.failed.connect(errors.append)

    # Await .NET Tasks through Qt timers; never block the GUI on Task.Result.
    def wait(task):
        deadline = time.monotonic()+8
        while not task.IsCompleted:
            if time.monotonic() > deadline:
                raise TimeoutError('WebView2 Task did not complete')
            yield
        return task.Result

    def js(script):
        return json.loads(str((yield from wait(win.browser.execute_script(script)))))

    def delay(seconds):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            yield

    def check(name, value):
        checks[name] = bool(value)
        print(name, bool(value), flush=True)

    def steps():
        deadline = time.monotonic()+18
        while not win.browser.web or not win.browser.web.CoreWebView2:
            if time.monotonic()>deadline:
                raise TimeoutError('WebView2 not ready')
            yield
        yield from delay(4)
        win.subtitles.page.mode.setCurrentIndex(win.subtitles.page.mode.findData('dom'))
        win.subtitles.page.enabled.setChecked(True)
        # Add an actual timed text track to a real locally encoded video.
        yield from js("""(() => {
          const style=document.createElement('style');
          style.textContent='body{margin:0!important;max-width:none!important;overflow:hidden}body>h1,body>p,body>input{display:none!important}video{width:100vw!important;height:100vh!important;object-fit:contain}';
          document.head.append(style);
          const v=document.querySelector('video');v.pause();v.currentTime=.5;
          const t=v.addTextTrack('subtitles','local-test','zh');t.mode='hidden';
          t.addCue(new VTTCue(0,2,'往东北走，沿着道路继续前进'));
          return true;
        })()""")
        yield from delay(1.5)
        state = yield from js("""(() => {
          const h=document.getElementById('genshinimpactvt-caption-overlay');
          const v=document.querySelector('video'),r=v.getBoundingClientRect();
          const b=h&&h.getBoundingClientRect(),label=h&&h.shadowRoot.querySelector('.caption');
          return {text:label&&label.textContent, transparent:h&&getComputedStyle(h).backgroundColor==='rgba(0, 0, 0, 0)',
            aligned:!!b&&b.height>100&&Math.abs(b.left-Math.max(0,r.left))<2&&Math.abs(b.width-r.width)<2,
            clickThrough:h&&getComputedStyle(h).pointerEvents==='none'&&document.elementFromPoint(r.left+r.width/2,r.top+r.height*.8)!==h};
        })()""")
        check('real_track_to_overlay', '往东北走' in (state['text'] or ''))
        for key in ('transparent', 'aligned', 'clickThrough'):
            check(key, state[key])
        # Capture the browser compositor, not Qt.grab (which omits native HWNDs).
        task, stream = win.browser.capture_preview()
        try:
            yield from wait(task)
            (DATA/'browser-overlay.png').write_bytes(bytes(stream.ToArray()))
        finally:
            stream.Dispose()
        win.enter_mini_player()
        yield from delay(.3)
        check('mini_player_size_and_position', win.width()==480 and win.height()==300 and win.immersive and win.pos().x()>=win.screen().availableGeometry().left())
        win.resize(420, 260)
        yield from delay(.5)
        check('compact_small_window', win.width()==420 and win.height()==260 and win.browser.width()==win.centralWidget().width())
        check('no_subtitle_layout_row', win.stack.widget(0).layout().count()==3)
        # Explicitly test a changed video rectangle without changing captions.
        rect = yield from js("""(() => {
          const h=document.getElementById('genshinimpactvt-caption-overlay');
          return {w:h.getBoundingClientRect().width,v:document.querySelector('video').getBoundingClientRect().width};
        })()""")
        check('resize_tracks_video', abs(rect['w']-rect['v'])<2)
        win.subtitles.timer.stop()
        evil = '<img src=x onerror="window.injected=true">往东北走'
        win.subtitle_overlay.set_caption(evil, 'platform')
        state = yield from js("""(() => {
          const h=document.getElementById('genshinimpactvt-caption-overlay');
          return {text:h.shadowRoot.querySelector('.caption').textContent,images:h.shadowRoot.querySelectorAll('img').length};
        })()""")
        check('untrusted_caption_is_plain_text', state['text']==evil and state['images']==0)
        # The test-only CDP call grants a gesture to this local fixture.
        # Production rendering uses ExecuteScriptAsync, not a debugging port.
        core = win.browser.web.CoreWebView2
        yield from wait(core.CallDevToolsProtocolMethodAsync('Runtime.evaluate', json.dumps({
            'expression':"document.querySelector('video').parentElement.requestFullscreen()",
            'userGesture':True, 'awaitPromise':True})))
        yield from delay(.5)
        state = yield from js("""(() => {
          const fs=document.fullscreenElement,h=document.getElementById('genshinimpactvt-caption-overlay');
          return !!fs&&!!h&&fs.contains(h);
        })()""")
        check('container_fullscreen_overlay', state)
        yield from js('document.exitFullscreen();true')
        yield from delay(.3)
        check('fullscreen_restores_compact_mode', win.immersive)
        yield from wait(core.CallDevToolsProtocolMethodAsync('Runtime.evaluate', json.dumps({
            'expression':"document.querySelector('video').requestFullscreen()",
            'userGesture':True, 'awaitPromise':True})))
        yield from delay(.5)
        state = yield from js("""(() => {
          const t=window.__genshinimpactvtCaptionTrack;
          return document.fullscreenElement===document.querySelector('video')&&!!t&&t.mode==='showing'&&t.cues.length===1;
        })()""")
        check('native_video_fullscreen_track', state)
        from genshinimpactvt.subtitles import PAGE_SCRIPT
        metadata = yield from js(PAGE_SCRIPT)
        check('overlay_not_read_back_as_subtitle', evil not in metadata['text'])
        win.subtitles.page.show_footer.setChecked(False)
        state = yield from js("!document.getElementById('genshinimpactvt-caption-overlay')&&window.__genshinimpactvtCaptionTrack.mode==='disabled'")
        check('hide_disables_both_renderers', state)
        win.subtitles.page.show_footer.setChecked(True)
        yield from js('document.exitFullscreen();true')
        yield from delay(.3)
        win.subtitles.page.enabled.setChecked(False)
        check('disable_clears', not win.subtitle_overlay.current)
        state = yield from js("!document.getElementById('genshinimpactvt-caption-overlay')")
        check('disable_removes_overlay', state)
        check('no_browser_errors', not errors)

    iterator = steps()
    started = time.monotonic()

    def tick():
        try:
            if time.monotonic()-started > 50:
                raise TimeoutError('smoke test timeout')
            next(iterator)
            return
        except StopIteration:
            pass
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
        timer.stop()
        win.close()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(50)
    app.exec()
    ole.OleUninitialize()
    result = {'checks':checks, 'errors':errors}
    (DATA/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return 0 if len(checks)==17 and all(checks.values()) and not errors else 1


if __name__ == '__main__':
    sys.exit(main())
