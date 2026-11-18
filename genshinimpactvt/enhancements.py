"""Bilibili playback, user-configurable hotkeys and subtitle direction overlay."""
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
from ctypes import wintypes

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QColorDialog, QComboBox, QLabel, QPushButton, QSlider, QSpinBox

from .browser import user32
from .compass import Compass
from .desktop_subtitle import DesktopSubtitle
from .mouse_buttons import SideButtons
from .raw_mouse import RawMouse
from .settings_ui import SettingsCard, SettingsDisclosure, SettingsSection, setting_note, slider_field, slider_spin_field
from .shortcuts import Shortcuts
from .window_controls import WindowControls
from .window_opacity import WindowOpacity
from .subtitles import SubtitleController
from .bilibili_subtitles import official_episode_url
from .uninstaller import HELPER, MARKER


def make_window_settings(window):
    section = SettingsSection()
    window_card = SettingsCard('窗口')
    window.window_opacity = WindowOpacity(window)
    window.opacity_label = QLabel(f'{window.window_opacity.percent}%')
    window.opacity_slider = QSlider(Qt.Orientation.Horizontal)
    window.opacity_slider.setRange(20, 100)
    window.opacity_slider.setValue(window.window_opacity.percent)
    window.opacity_slider.valueChanged.connect(window.window_opacity.set_percent)

    def update_opacity(percent):
        window.opacity_slider.blockSignals(True)
        window.opacity_slider.setValue(percent)
        window.opacity_slider.blockSignals(False)
        window.opacity_label.setText(f'{percent}%')

    window.window_opacity.changed.connect(update_opacity)
    window_card.form.addRow('不透明度', slider_field(window.opacity_slider, window.opacity_label))

    compass = window.compass = Compass()
    color = QColor(window.settings.value('compass/color', compass.color.name()))
    if color.isValid():
        compass.color = color
    float_card = SettingsCard('方向浮窗')
    window.compass_toggle = QCheckBox('显示方向浮窗')
    window.compass_toggle.setChecked(window.settings.value('compass/enabled', True, type=bool))
    window.compass_toggle.toggled.connect(window.set_compass)
    float_card.form.addRow(window.compass_toggle)
    float_card.form.addRow(setting_note('默认在屏幕左上角，拖动方位文字可移动。'))

    color_button = QPushButton('选择颜色')
    color_button.clicked.connect(window.choose_compass_color)
    float_card.form.addRow('高亮颜色', color_button)

    window.glow_strength = QSlider(Qt.Orientation.Horizontal)
    window.glow_strength.setRange(15, 100)
    window.glow_strength.setValue(window.settings.value('compass/glow_strength', 75, type=int))
    compass.set_strength(window.glow_strength.value())
    strength_value = QLabel(f'{window.glow_strength.value()}%')

    def update_strength(percent):
        compass.set_strength(percent)
        strength_value.setText(f'{percent}%')
        window.settings.setValue('compass/glow_strength', percent)

    window.glow_strength.valueChanged.connect(update_strength)
    float_card.form.addRow('高亮强度', slider_field(window.glow_strength, strength_value))

    window.glow_size = QSpinBox()
    window.glow_size.setRange(140, 420)
    window.glow_size.setSuffix(' px')
    window.glow_size.setValue(window.settings.value('compass/glow_size', 240, type=int))
    compass.set_extent(window.glow_size.value())
    window.glow_size.valueChanged.connect(compass.set_extent)
    window.glow_size.valueChanged.connect(lambda size: window.settings.setValue('compass/glow_size', size))
    float_card.form.addRow('浮窗大小', slider_spin_field(window.glow_size, '浮窗大小'))

    window.glow_duration = QSpinBox()
    window.glow_duration.setRange(1, 30)
    window.glow_duration.setSuffix(' 秒')
    window.glow_duration.setValue(window.settings.value('compass/hold_seconds', 5, type=int))
    compass.set_hold_seconds(window.glow_duration.value())
    window.glow_duration.valueChanged.connect(compass.set_hold_seconds)
    window.glow_duration.valueChanged.connect(lambda seconds: window.settings.setValue('compass/hold_seconds', seconds))
    float_card.form.addRow('提示时长', window.glow_duration)

    advanced = SettingsCard('')
    glow = QCheckBox('显示柔光刻线和方向箭头')
    glow.setChecked(window.settings.value('compass/glow_enabled', True, type=bool))
    compass.set_glow_enabled(glow.isChecked())
    glow.toggled.connect(compass.set_glow_enabled)
    glow.toggled.connect(lambda enabled: window.settings.setValue('compass/glow_enabled', enabled))
    advanced.form.addRow(glow)
    window.uninstall_button = QPushButton('卸载此版本…')
    window.uninstall_button.clicked.connect(window.request_uninstall)
    install_root = Path(sys.executable).parent
    window.uninstall_button.setEnabled(bool(getattr(sys, 'frozen', False)) and
                                       (install_root / MARKER).is_file() and (install_root / HELPER).is_file())
    window.uninstall_button.setToolTip('卸载便携版；默认保留个人资料。开发源码不提供卸载。')
    advanced.form.addRow('软件管理', window.uninstall_button)
    section.add(window_card)
    section.add(float_card)
    section.add(SettingsDisclosure('高级设置 · 普通用户可忽略', advanced))
    return section


def make_shortcut_settings(window):
    section = SettingsSection()
    switches = SettingsCard('键盘与鼠标')
    window.episode_toggle = QCheckBox('启用键盘快捷键')
    window.episode_toggle.setChecked(window.settings.value('episode_keys/enabled', True, type=bool))
    window.mouse_toggle = QCheckBox('启用鼠标侧键')
    window.mouse_toggle.setChecked(window.settings.value('mouse/enabled', True, type=bool))
    switches.form.addRow(window.episode_toggle)
    switches.form.addRow(window.mouse_toggle)

    advanced = SettingsCard('')
    window.episode_mode = QComboBox()
    window.episode_mode.addItem('普通监听', 'hook')
    window.episode_mode.addItem('系统全局热键', 'system')
    window.episode_mode.setToolTip('普通监听保留原按键，系统全局热键会占用所设按键。')
    selected = window.episode_mode.findData(window.settings.value('episode_keys/mode', 'hook'))
    window.episode_mode.setCurrentIndex(max(0, selected))
    window.episode_status = setting_note('')
    advanced.form.addRow('键盘监听方式', window.episode_mode)
    advanced.form.addRow(window.episode_status)

    window.mouse_mode = QComboBox()
    window.mouse_mode.addItem('后台原始输入', 'raw')
    window.mouse_mode.addItem('普通侧键监听', 'hook')
    selected = window.mouse_mode.findData(window.settings.value('mouse/mode', 'raw'))
    window.mouse_mode.setCurrentIndex(max(0, selected))
    window.mouse_count = 0
    window.mouse_status = setting_note('侧键状态：尚未检测到按键（计数 0）')
    injected = QCheckBox('普通监听时接受鼠标模拟侧键')
    injected.setChecked(window.settings.value('mouse/allow_injected', False, type=bool))
    advanced.form.addRow('鼠标监听方式', window.mouse_mode)
    advanced.form.addRow(injected)
    advanced.form.addRow(window.mouse_status)

    window.shortcuts = Shortcuts(window)
    window.episode_keys = window.shortcuts.hook
    window.system_episode_keys = window.shortcuts.system
    window.episode_mode.currentIndexChanged.connect(window.change_episode_mode)
    window.episode_toggle.toggled.connect(window.set_episode_keys)
    window.shortcuts.start()
    window.side_buttons = SideButtons(window)
    window.raw_mouse = RawMouse(int(window.winId()), window)
    for listener in (window.side_buttons, window.raw_mouse):
        listener.pressed.connect(window.side_button, Qt.ConnectionType.QueuedConnection)
        listener.observed.connect(window.mouse_observed, Qt.ConnectionType.QueuedConnection)
    window.side_buttons.allow_injected = injected.isChecked()
    injected.toggled.connect(window.set_injected_enabled)
    window.mouse_toggle.toggled.connect(window.set_mouse_enabled)
    window.mouse_mode.currentIndexChanged.connect(window.change_mouse_mode)
    if window.mouse_toggle.isChecked() and not window.current_mouse().start():
        window.mouse_toggle.setChecked(False)
        window.status.setText('鼠标侧键监听启动失败，请检查设置。')

    section.add(switches)
    section.add(window.shortcuts.page)
    section.add(SettingsDisclosure('高级设置 · 普通用户可忽略', advanced))
    return section

def on_bilibili(self):
    host = (urlsplit(self.address.text()).hostname or '').lower()
    return host == 'bilibili.com' or host.endswith('.bilibili.com')

def install(cls):
    old_init, old_close, old_native = cls.__init__, cls.closeEvent, cls.nativeEvent

    def initialize(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        self.immersive = False
        self.settings_view.add_section('window', '窗口与浮窗', make_window_settings(self))

        self.subtitles = SubtitleController(self.browser, self.compass, self.settings, self)
        self.subtitles.caption_changed.connect(self.subtitle_overlay.set_caption)
        self.subtitles.enabled_changed.connect(self.subtitle_overlay.set_recognition_enabled)
        self.subtitle_overlay.set_recognition_enabled(self.subtitles.enabled)
        self.desktop_subtitle = DesktopSubtitle(self)
        self.subtitles.caption_changed.connect(self.desktop_subtitle.set_caption)
        self.subtitles.enabled_changed.connect(self.desktop_subtitle.set_recognition_enabled)
        self.desktop_subtitle.set_recognition_enabled(self.subtitles.enabled)
        footer = self.subtitles.page.show_footer
        footer.setChecked(self.settings.value('subtitles/show_footer', True, type=bool))
        self.subtitle_overlay.set_visible(footer.isChecked())
        desktop = self.subtitles.page.show_desktop
        desktop.setChecked(self.settings.value('subtitles/show_desktop', False, type=bool))
        self.desktop_subtitle.set_enabled(desktop.isChecked())
        desktop_size = self.subtitles.page.desktop_font_size
        desktop_size.setValue(self.settings.value('subtitles/desktop_font_size', DesktopSubtitle.DEFAULT_FONT_SIZE, type=int))
        desktop_size_field = self.subtitles.page.desktop_size_field
        desktop_size_field.setEnabled(desktop.isChecked())
        self.desktop_subtitle.set_font_size(desktop_size.value())

        def show_video_subtitles(visible):
            self.subtitle_overlay.set_visible(visible)
            self.settings.setValue('subtitles/show_footer', visible)

        footer.toggled.connect(show_video_subtitles)
        desktop.toggled.connect(self.desktop_subtitle.set_enabled)
        desktop.toggled.connect(lambda visible: self.settings.setValue('subtitles/show_desktop', visible))
        desktop.toggled.connect(desktop_size_field.setEnabled)
        desktop_size.valueChanged.connect(self.desktop_subtitle.set_font_size)
        desktop_size.valueChanged.connect(lambda size: self.settings.setValue('subtitles/desktop_font_size', size))
        self.subtitles.enabled_changed.connect(lambda enabled: self.compass_toggle.setChecked(True) if enabled else None)
        self.settings_view.add_section('subtitles', '字幕设置', self.subtitles.page)
        self.settings_view.add_section('shortcuts', '快捷键', make_shortcut_settings(self))

        bottom = self.stack.widget(0).layout().itemAt(2).layout()
        compact = QPushButton('小窗观看')
        compact.clicked.connect(self.enter_mini_player)
        bottom.addWidget(compact)
        show_compass = QPushButton('显示方向浮窗')
        show_compass.clicked.connect(self.show_compass)
        bottom.addWidget(show_compass)
        self._fullscreen_core = None
        self._fullscreen_restore_immersive = None
        def browser_ready():
            self._fullscreen_core = self.browser.web.CoreWebView2
            self._fullscreen_handler = lambda sender, event: self.sync_fullscreen()
            self._fullscreen_core.ContainsFullScreenElementChanged += self._fullscreen_handler
        self.browser.ready.connect(browser_ready)
        self.window_controls = WindowControls(self)
        if self.settings.value('window/compact', False, type=bool):
            self.toggle_immersive()
        self.show_at_startup()
        self.desktop_subtitle.follow_player_screen()
        self.compass.place_at_startup(self.settings.value('compass/position'), self.screen())
        self.compass.setVisible(self.compass_toggle.isChecked())

    def sync_fullscreen(self):
        active = bool(self._fullscreen_core.ContainsFullScreenElement)
        if active:
            if self._fullscreen_restore_immersive is None: self._fullscreen_restore_immersive = self.immersive
            if not self.immersive: self.toggle_immersive()
        elif self._fullscreen_restore_immersive is not None:
            if not self._fullscreen_restore_immersive and self.immersive: self.toggle_immersive()
            self._fullscreen_restore_immersive = None

    def current_episode_keys(self):
        return self.system_episode_keys if self.episode_mode.currentData() == 'system' else self.episode_keys

    def change_episode_mode(self):
        self.settings.setValue('episode_keys/mode',self.episode_mode.currentData())
        self.shortcuts.start()

    def set_episode_keys(self, enabled):
        self.settings.setValue('episode_keys/enabled',enabled)
        self.shortcuts.start()
        if not enabled: self.episode_status.setText('键盘快捷键已关闭，可用托盘唤出控制条。')

    def toggle_immersive(self):
        self.immersive = not self.immersive; self.select(0)
        # Keep compact mode free of controls, with recovery through the tray or window menu.
        if self.immersive and not self.window_controls.system_menu_available and not self.window_controls.tray.isVisible(): self.floating.show()
        root_layout = self.centralWidget().layout(); root_layout.itemAt(0).widget().setVisible(not self.immersive)
        layout = self.stack.widget(0).layout()
        layout.setContentsMargins(0, 0, 0, 0) if self.immersive else layout.setContentsMargins(20, 18, 20, 12)
        layout.setSpacing(0 if self.immersive else 12)
        self.setMinimumSize(320, 180) if self.immersive else self.setMinimumSize(480, 300)
        for index in (0, 2):
            row = layout.itemAt(index).layout()
            for i in range(row.count()):
                widget = row.itemAt(i).widget()
                if widget: widget.setVisible(not self.immersive)

    def enter_mini_player(self):
        if not self.immersive: self.toggle_immersive()
        self.showNormal(); self.resize(480, 300)
        available = self.screen().availableGeometry()
        self.move(available.left()+16, available.bottom()-self.frameGeometry().height()-16)

    def set_compass(self, enabled):
        self.settings.setValue('compass/enabled', enabled); self.compass.setVisible(enabled)

    def show_compass(self):
        self.compass_toggle.setChecked(True); self.compass.show(); self.compass.raise_()

    def side_button(self, which):
        action = self.shortcuts.mouse.get(which)
        if action: self.shortcuts.dispatch(action)

    def mouse_observed(self, which, injected):
        self.mouse_count += 1
        label = '上键 / XBUTTON2' if which == 2 else '下键 / XBUTTON1'
        suffix = '（模拟输入，已忽略；可在设置中允许）' if injected and not self.side_buttons.allow_injected else ''
        self.mouse_status.setText(f'侧键状态：检测到 {label}，计数 {self.mouse_count}' + suffix)

    def set_injected_enabled(self, enabled):
        self.side_buttons.allow_injected = enabled; self.settings.setValue('mouse/allow_injected', enabled)

    def current_mouse(self):
        return self.raw_mouse if self.mouse_mode.currentData() == 'raw' else self.side_buttons

    def change_mouse_mode(self):
        self.side_buttons.stop(); self.raw_mouse.stop()
        if self.mouse_toggle.isChecked() and not self.current_mouse().start():
            self.mouse_status.setText('侧键监听启动失败，请切换方式或关闭后重试。')
        else:
            self.settings.setValue('mouse/mode', self.mouse_mode.currentData())
            self.mouse_status.setText('侧键状态：请按鼠标侧键测试。')

    def set_mouse_enabled(self, enabled):
        if enabled and not self.current_mouse().start():
            self.status.setText('鼠标侧键监听启动失败，请重新尝试。'); return
        if not enabled: self.side_buttons.stop(); self.raw_mouse.stop()
        self.settings.setValue('mouse/enabled', enabled)

    def choose_color(self):
        color = QColorDialog.getColor(self.compass.color, self, '方向高亮颜色')
        if color.isValid():
            self.compass.color = color; self.compass.update(); self.settings.setValue('compass/color', color.name())

    def media_action(self, action):
        if action=='opacity_down':self.window_opacity.step(-10);return
        if action=='opacity_up':self.window_opacity.step(10);return
        if action=='opacity_reset':self.window_opacity.set_percent(100);return
        if action == 'controls': self.toggle_floating(); return
        if action == 'restore': self.restore_normal(); return
        if action == 'compass':
            self.compass_toggle.setChecked(not self.compass_toggle.isChecked()); return
        if action == 'immersive': self.toggle_immersive(); return
        if action == 'visible':
            if self.isVisible() and not self.isMinimized(): self.hide()
            else: self.restore_main()
            return
        if action == 'maximize':
            if self.isMaximized(): self.showNormal()
            else: self.showMaximized()
            return
        if not on_bilibili(self): self.status.setText('视频快捷键仅支持哔哩哔哩页面'); return
        if action in ('previous','next'):
            try:
                target=official_episode_url(self.address.text(),-1 if action=='previous' else 1)
                if target:
                    self.open_url(target);return
            except ValueError as exc:
                self.status.setText(str(exc));return
        script = '''(()=>{const action=ACTION;const v=document.querySelector('video');
          if(action==='previous'||action==='next'){const items=Array.from(document.querySelectorAll('.video-pod__item'));const idx=items.findIndex(x=>x.classList.contains('active'));const target=items[idx+(action==='previous'?-1:1)];
          if(idx>=0&&target){target.click();return 'ok'}const selectors=action==='next'?['.bpx-player-ctrl-next','a[title="下一集"]']:['.bpx-player-ctrl-prev','a[title="上一集"]'];
          for(const s of selectors){let el=document.querySelector(s);if(el&&!el.matches('[disabled],.disabled')){el.click();return 'ok'}}return '没有可用的上一集或下一集';}
          if(!v)return '未找到视频';if(action==='pause'){v.paused?v.play():v.pause();return 'ok'}
          if(action==='back'||action==='forward'){v.currentTime=Math.max(0,Math.min(v.duration||Infinity,v.currentTime+(action==='back'?-5:5)));return 'ok'}return '不支持';})()'''.replace('ACTION', json.dumps(action))
        try:
            task = self.browser.execute_script(script)
            def done(count=0):
                if task.IsCompleted:
                    try:
                        result = json.loads(str(task.Result))
                        if isinstance(result, str) and result != 'ok': self.status.setText(result)
                    except Exception as exc: self.error(str(exc))
                elif count < 30: QTimer.singleShot(100, lambda: done(count+1))
            QTimer.singleShot(50, done)
        except Exception as exc: self.error(str(exc))

    def native(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x00ff and hasattr(self, 'raw_mouse'):
            self.raw_mouse.handle_input(msg.lParam)
        if msg.message == 0x0312 and hasattr(self, 'system_episode_keys'):
            action = self.system_episode_keys.action(msg.wParam)
            if action:
                self.shortcuts.dispatch(action); return True, 0
        return old_native(self, event_type, message)

    def close(self, event):
        self.settings.setValue('window/compact', self.immersive)
        self.subtitles.close()
        self.desktop_subtitle.clear()
        self.desktop_subtitle.close()
        self.shortcuts.stop()
        self.side_buttons.stop()
        self.raw_mouse.stop()
        if self._fullscreen_core is not None:
            self._fullscreen_core.ContainsFullScreenElementChanged -= self._fullscreen_handler
        self.settings.setValue('compass/position', self.compass.pos()); self.compass.close()
        old_close(self, event)

    cls.__init__ = initialize; cls.closeEvent = close; cls.nativeEvent = native
    cls.toggle_immersive = toggle_immersive; cls.enter_mini_player = enter_mini_player; cls.set_compass = set_compass; cls.choose_compass_color = choose_color
    cls.show_compass = show_compass; cls.side_button = side_button; cls.set_mouse_enabled = set_mouse_enabled
    cls.mouse_observed = mouse_observed; cls.set_injected_enabled = set_injected_enabled
    cls.current_mouse = current_mouse; cls.change_mouse_mode = change_mouse_mode
    cls.sync_fullscreen = sync_fullscreen
    cls.set_episode_keys = set_episode_keys
    cls.current_episode_keys = current_episode_keys; cls.change_episode_mode = change_episode_mode
    cls.media_action = media_action
