"""Source application + real WebView2/Windows input; isolated synthetic video only."""
import ctypes
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
DATA=ROOT/'.test-controls-v13';DATA.mkdir(exist_ok=True)
os.environ['LOCALAPPDATA']=str(DATA)
from PySide6.QtCore import QSettings,QTimer,Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication
from main import Main,STYLE
from genshinimpactvt.shortcuts import SystemKeys,Shortcuts
import genshinimpactvt.enhancements as enhancements


def main():
    settings=QSettings(str(DATA/'app/settings.ini'),QSettings.Format.IniFormat);settings.clear()
    settings.setValue('browser/last_url','');settings.setValue('mouse/enabled',False)
    settings.setValue('episode_keys/enabled',True);settings.setValue('subtitles/enabled',False)
    settings.setValue('window/compact',True);settings.sync()
    ole=ctypes.OleDLL('ole32');ole.OleInitialize(None)
    app=QApplication([]);app.setStyleSheet(STYLE);win=Main(DATA/'app')
    checks={};errors=[];win.browser.failed.connect(errors.append)
    enhancements.on_bilibili=lambda window:True  # Only a local, self-owned video fixture.
    user32=ctypes.WinDLL('user32');user32.GetForegroundWindow.restype=ctypes.c_void_p
    user32.SetForegroundWindow.argtypes=[ctypes.c_void_p]
    user32.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]

    def check(name,value):
        checks[name]=bool(value);print(name,bool(value),flush=True)

    def delay(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:yield

    def js(script):
        task=win.browser.execute_script(script);deadline=time.monotonic()+8
        while not task.IsCompleted:
            if time.monotonic()>deadline:raise TimeoutError('WebView2 Task')
            yield
        return json.loads(str(task.Result))

    def press(vk):
        win.raise_();win.activateWindow();user32.SetForegroundWindow(int(win.winId()))
        yield from delay(.2)
        if user32.GetForegroundWindow()!=int(win.winId()):raise RuntimeError('Test window could not acquire foreground; no input sent')
        user32.keybd_event(vk,0,0,0);user32.keybd_event(vk,0,2,0)
        yield from delay(.3)

    def steps():
        deadline=time.monotonic()+18
        while not win.browser.web or not win.browser.web.CoreWebView2:
            if time.monotonic()>deadline:raise TimeoutError('Browser startup')
            yield
        yield from delay(3)
        check('compact_start_without_control_bar',win.immersive and not win.floating.isVisible())
        check('tray_available',win.window_controls.tray.isVisible())
        check('native_recovery_menu',win.window_controls.system_menu_available)
        win.window_controls.toggle_action.trigger();yield from delay(.1)
        check('tray_summons',win.floating.isVisible())
        win.floating.close();check('close_only_hides',not win.floating.isVisible() and win.isVisible())
        win.episode_keys.allow_injected=True
        yield from press(0x78)
        check('F9_hook_summons',win.floating.isVisible())
        check('summon_preserves_focus',user32.GetForegroundWindow()==int(win.winId()))
        yield from press(0x78);check('F9_hook_hides',not win.floating.isVisible())
        user32.PostMessageW(int(win.winId()),0x112,win.window_controls.RESTORE,0)
        yield from delay(.2)
        check('native_menu_restores_normal',not win.immersive and win.navbuttons[3].isVisible() and win.width()>=900)
        # Exercise an actual keyboard edit session, rather than just replacing an in-memory map.
        win.select(3);panel=win.shortcuts.page;panel.begin()
        panel.editors['forward'].setKeySequence(QKeySequence('J'))
        panel.editors['back'].setKeySequence(QKeySequence('K'))
        panel.editors['pause'].setKeySequence(QKeySequence('P'))
        panel.editors['controls'].setKeySequence(QKeySequence('F7'))
        panel.mouse_editors[2].setCurrentIndex(panel.mouse_editors[2].findData('forward'))
        panel.apply()
        check('all_bindings_save',not panel.editing and win.shortcuts.values['forward']=='J' and win.shortcuts.mouse[2]=='forward')
        panel.begin();panel.editors['next'].setKeySequence(QKeySequence('J'));panel.apply()
        check('duplicate_rejected',panel.editing and win.shortcuts.suspended and win.shortcuts.values['next']=='8')
        panel.cancel();check('cancel_resumes',not win.shortcuts.suspended and bool(win.episode_keys.handle))
        win.settings.sync();other=Shortcuts(win)
        check('restart_restores_bindings',other.values['controls']=='F7' and other.values['forward']=='J' and other.mouse[2]=='forward')
        other.stop();other.page.close();other.deleteLater()
        win.select(0)
        yield from js("const v=document.querySelector('video');v.pause();v.loop=false;v.currentTime=.1;true")
        yield from press(0x4a)
        state=yield from js("({time:document.querySelector('video').currentTime,duration:document.querySelector('video').duration})")
        check('custom_J_fast_forward',abs(state['time']-min(state['duration'],5.1))<.25)
        yield from press(0x4b)
        check('custom_K_rewind',(yield from js("document.querySelector('video').currentTime"))<.3)
        yield from press(0x50)
        check('custom_P_plays',not (yield from js("document.querySelector('video').paused")))
        yield from delay(.4);yield from press(0x50)
        check('custom_P_pauses',(yield from js("document.querySelector('video').paused")))
        win.side_button(2);yield from delay(.3)
        state=yield from js("({time:document.querySelector('video').currentTime,duration:document.querySelector('video').duration})")
        check('remapped_side_action',abs(state['time']-state['duration'])<.25)
        win.episode_mode.setCurrentIndex(win.episode_mode.findData('system'))
        check('custom_system_registered',win.system_episode_keys.active and not win.episode_keys.handle)
        yield from press(0x76)
        check('F7_system_summons',win.floating.isVisible())
        yield from press(0x76);check('F7_system_hides',not win.floating.isVisible())
        win.episode_mode.setCurrentIndex(win.episode_mode.findData('hook'))
        win.show_compass();win.glow_duration.setValue(6);win.subtitles.deliver('向东北走','platform')
        win.subtitles.deliver('','platform');win.subtitles.deliver('打开宝箱','platform')
        yield from delay(3)
        check('direction_survives_old_timeout_and_gaps',win.compass.active=={'东','北'} and win.compass._phase=='hold')
        check('duration_persists',win.settings.value('compass/hold_seconds',type=int)==6)
        yield from delay(3.7)
        check('direction_expires_and_stops',not win.compass.active and not win.compass.expiry.isActive())
        win.shortcuts.page.begin();win.select(3)
        win.grab().save(str(DATA/'settings-preview.png'));win.shortcuts.page.cancel()
        check('no_browser_errors',not errors)

    iterator=steps();started=time.monotonic()
    def tick():
        try:
            if time.monotonic()-started>55:raise TimeoutError('Test timeout')
            next(iterator);return
        except StopIteration:pass
        except Exception as exc:errors.append(f'{type(exc).__name__}: {exc}');print(errors[-1],flush=True)
        timer.stop();win.close()
    timer=QTimer();timer.timeout.connect(tick);timer.start(40)
    app.exec();ole.OleUninitialize()
    probe=SystemKeys(None);probe.bindings=win.shortcuts.bindings
    released=probe.start();probe.stop();check('all_system_keys_released',released and not win.episode_keys.handle)
    result={'checks':checks,'errors':errors}
    (DATA/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return 0 if len(checks)>=26 and all(checks.values()) and not errors else 1


if __name__=='__main__':sys.exit(main())
