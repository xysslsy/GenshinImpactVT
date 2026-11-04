"""Bilibili playback, user-configurable hotkeys and subtitle direction overlay."""
import json
from urllib.parse import urlsplit
from ctypes import wintypes

from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QColorDialog, QComboBox, QLabel, QPushButton, QScrollArea, QSlider, QSpinBox

from .browser import user32
from .compass import Compass
from .mouse_buttons import SideButtons
from .raw_mouse import RawMouse
from .episode_keys import EpisodeKeys, SystemEpisodeKeys
from .subtitles import SubtitleController
from .bilibili_subtitles import official_episode_url

def on_bilibili(self):
    host = (urlsplit(self.address.text()).hostname or '').lower()
    return host == 'bilibili.com' or host.endswith('.bilibili.com')

def install(cls):
    old_init, old_close, old_native = cls.__init__, cls.closeEvent, cls.nativeEvent

    def initialize(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        self.immersive = False
        self.compass = Compass(); color = QColor(self.settings.value('compass/color', '#4080ff'))
        if color.isValid(): self.compass.color = color
        page = self.stack.widget(3); box = page.layout()
        episode_toggle = QCheckBox('启用 7 上一集 / 8 下一集'); self.episode_toggle = episode_toggle
        episode_toggle.setChecked(self.settings.value('episode_keys/enabled', True, type=bool)); box.insertWidget(box.count()-1, episode_toggle)
        notice = QLabel('系统全局方式会占用 7、8，其他程序可能无法输入这两个键；关闭或切回普通监听即可恢复。'); notice.setWordWrap(True); box.insertWidget(box.count()-1, notice)
        self.episode_keys = EpisodeKeys(self); self.episode_keys.pressed.connect(self.media_action, Qt.ConnectionType.QueuedConnection)
        self.system_episode_keys = SystemEpisodeKeys(int(self.winId()))
        self.episode_mode = QComboBox(); self.episode_mode.addItem('普通监听（不占用按键）', 'hook'); self.episode_mode.addItem('系统全局热键（占用 7、8）', 'system')
        selected = self.episode_mode.findData(self.settings.value('episode_keys/mode', 'hook'))
        self.episode_mode.setCurrentIndex(max(0, selected)); box.insertWidget(box.count()-1, self.episode_mode)
        self.episode_status = QLabel(''); self.episode_status.setWordWrap(True); box.insertWidget(box.count()-1, self.episode_status)
        self.episode_mode.currentIndexChanged.connect(self.change_episode_mode)
        episode_toggle.toggled.connect(self.set_episode_keys)
        if episode_toggle.isChecked() and not self.current_episode_keys().start():
            episode_toggle.setChecked(False); self.episode_status.setText('7 / 8 启用失败，可能已被占用，请切换监听方式。')
        elif episode_toggle.isChecked(): self.episode_status.setText('7 / 8 已启用。')
        toggle = QCheckBox('启用字幕方向浮窗（拖动文字调整位置）'); self.compass_toggle = toggle; toggle.setChecked(self.settings.value('compass/enabled', False, type=bool)); toggle.toggled.connect(self.set_compass); box.insertWidget(box.count()-1, toggle)
        color_button = QPushButton('选择方向高亮颜色'); color_button.clicked.connect(self.choose_compass_color); box.insertWidget(box.count()-1, color_button)
        ambient=QCheckBox('方向氛围光（东北等斜向只亮对应区域）')
        ambient.setChecked(self.settings.value('compass/glow_enabled',True,type=bool))
        self.compass.set_glow_enabled(ambient.isChecked());box.insertWidget(box.count()-1,ambient)
        ambient.toggled.connect(lambda value:(self.compass.set_glow_enabled(value),self.settings.setValue('compass/glow_enabled',value)))
        glow_note=QLabel('圆形柔光短暂亮起后淡出，背景透明；可拖动整个方向浮窗对准小地图。')
        glow_note.setWordWrap(True);box.insertWidget(box.count()-1,glow_note)
        box.insertWidget(box.count()-1,QLabel('氛围光强度'))
        self.glow_strength=QSlider(Qt.Orientation.Horizontal);self.glow_strength.setRange(15,100)
        self.glow_strength.setValue(self.settings.value('compass/glow_strength',75,type=int))
        self.compass.set_strength(self.glow_strength.value());box.insertWidget(box.count()-1,self.glow_strength)
        self.glow_strength.valueChanged.connect(lambda value:(self.compass.set_strength(value),self.settings.setValue('compass/glow_strength',value)))
        self.glow_size=QSpinBox();self.glow_size.setRange(140,420);self.glow_size.setSuffix(' px · 方向浮窗大小')
        self.glow_size.setValue(self.settings.value('compass/glow_size',240,type=int))
        self.compass.set_extent(self.glow_size.value());box.insertWidget(box.count()-1,self.glow_size)
        self.glow_size.valueChanged.connect(lambda value:(self.compass.set_extent(value),self.settings.setValue('compass/glow_size',value)))
        mouse = QCheckBox('鼠标侧键：上键播放/暂停，下键快退 5 秒'); self.mouse_toggle = mouse; mouse.setChecked(self.settings.value('mouse/enabled', True, type=bool)); box.insertWidget(box.count()-1, mouse)
        mouse_note = QLabel('同时保留鼠标原有功能；某些游戏或鼠标驱动可能接管侧键。'); mouse_note.setWordWrap(True); box.insertWidget(box.count()-1, mouse_note)
        self.side_buttons = SideButtons(self); self.side_buttons.pressed.connect(self.side_button, Qt.ConnectionType.QueuedConnection)
        self.raw_mouse = RawMouse(int(self.winId()), self); self.raw_mouse.pressed.connect(self.side_button, Qt.ConnectionType.QueuedConnection)
        self.mouse_count = 0
        self.mouse_status = QLabel('侧键状态：尚未检测到按键（计数 0）'); self.mouse_status.setWordWrap(True); box.insertWidget(box.count()-1, self.mouse_status)
        self.side_buttons.observed.connect(self.mouse_observed, Qt.ConnectionType.QueuedConnection)
        self.raw_mouse.observed.connect(self.mouse_observed, Qt.ConnectionType.QueuedConnection)
        self.mouse_mode = QComboBox(); self.mouse_mode.addItem('后台原始输入（适用于部分游戏）', 'raw'); self.mouse_mode.addItem('普通侧键监听', 'hook')
        selected = self.mouse_mode.findData(self.settings.value('mouse/mode', 'raw'))
        self.mouse_mode.setCurrentIndex(max(0, selected)); box.insertWidget(box.count()-1, self.mouse_mode)
        injected = QCheckBox('普通监听：接受鼠标驱动产生的模拟侧键'); injected.setChecked(self.settings.value('mouse/allow_injected', False, type=bool)); box.insertWidget(box.count()-1, injected)
        self.side_buttons.allow_injected = injected.isChecked()
        injected.toggled.connect(self.set_injected_enabled)
        mouse.toggled.connect(self.set_mouse_enabled)
        self.mouse_mode.currentIndexChanged.connect(self.change_mouse_mode)
        if mouse.isChecked() and not self.current_mouse().start():
            mouse.setChecked(False); self.status.setText('鼠标侧键监听启动失败，请检查设置。')
        scroll = QScrollArea(); scroll.setWidgetResizable(True); self.stack.removeWidget(page); scroll.setWidget(page); self.stack.insertWidget(3, scroll)
        browser_page = self.stack.widget(0); bottom = browser_page.layout().itemAt(2).layout()
        compact = QPushButton('精简窗口'); compact.clicked.connect(self.toggle_immersive); bottom.addWidget(compact)
        show_compass = QPushButton('显示方向浮窗'); show_compass.clicked.connect(self.show_compass); bottom.addWidget(show_compass)
        if toggle.isChecked():
            pos = self.settings.value('compass/position')
            if pos is not None: self.compass.move(pos)
            self.compass.show()
        self.subtitles = SubtitleController(self.browser,self.compass,self.settings,self)
        self.subtitles.caption_changed.connect(self.subtitle_strip.set_caption)
        self.subtitles.enabled_changed.connect(self.subtitle_strip.set_recognition_enabled)
        self.subtitle_strip.set_recognition_enabled(self.subtitles.enabled)
        footer=self.subtitles.page.show_footer
        footer.setChecked(self.settings.value('subtitles/show_footer',True,type=bool))
        self.subtitle_strip.setVisible(footer.isChecked())
        footer.toggled.connect(lambda visible:(self.subtitle_strip.setVisible(visible),self.settings.setValue('subtitles/show_footer',visible)))
        subtitle_scroll = QScrollArea(); subtitle_scroll.setWidgetResizable(True); subtitle_scroll.setWidget(self.subtitles.page)
        self.subtitles.page_index = self.stack.addWidget(subtitle_scroll)
        subtitle_nav = QPushButton('字幕识别'); subtitle_nav.setObjectName('nav'); subtitle_nav.setCheckable(True)
        subtitle_nav.clicked.connect(lambda: self.select(self.subtitles.page_index))
        self.navbuttons.append(subtitle_nav)
        self.centralWidget().layout().itemAt(0).widget().layout().insertWidget(5,subtitle_nav)
        self.subtitles.page.show_compass.clicked.connect(self.show_compass)
        self.subtitles.enabled_changed.connect(lambda enabled: self.compass_toggle.setChecked(True) if enabled else None)
        self._fullscreen_core = None
        def browser_ready():
            self._fullscreen_core = self.browser.web.CoreWebView2
            self._fullscreen_handler = lambda sender, event: self.sync_fullscreen()
            self._fullscreen_core.ContainsFullScreenElementChanged += self._fullscreen_handler
        self.browser.ready.connect(browser_ready)

    def sync_fullscreen(self):
        active = bool(self._fullscreen_core.ContainsFullScreenElement)
        if active != self.immersive: self.toggle_immersive()

    def current_episode_keys(self):
        return self.system_episode_keys if self.episode_mode.currentData() == 'system' else self.episode_keys

    def change_episode_mode(self):
        self.episode_keys.stop(); self.system_episode_keys.stop()
        if self.episode_toggle.isChecked() and not self.current_episode_keys().start():
            self.episode_status.setText('7 / 8 启用失败，可能已被占用，请切回普通监听。')
        else:
            self.settings.setValue('episode_keys/mode', self.episode_mode.currentData())
            self.episode_status.setText('7 / 8 已启用。' if self.episode_toggle.isChecked() else '7 / 8 已关闭。')

    def set_episode_keys(self, enabled):
        if enabled and not self.current_episode_keys().start():
            self.episode_toggle.blockSignals(True); self.episode_toggle.setChecked(False); self.episode_toggle.blockSignals(False)
            self.episode_status.setText('7 / 8 启用失败，可能已被占用。'); return
        if not enabled: self.episode_keys.stop(); self.system_episode_keys.stop()
        self.episode_status.setText('7 / 8 已启用。' if enabled else '7 / 8 已关闭。')
        self.settings.setValue('episode_keys/enabled', enabled)

    def toggle_immersive(self):
        self.immersive = not self.immersive; self.select(0)
        if self.immersive: self.floating.show()
        root_layout = self.centralWidget().layout(); root_layout.itemAt(0).widget().setVisible(not self.immersive)
        layout = self.stack.widget(0).layout()
        for index in (0, 2):
            row = layout.itemAt(index).layout()
            for i in range(row.count()):
                widget = row.itemAt(i).widget()
                if widget: widget.setVisible(not self.immersive)

    def set_compass(self, enabled):
        self.settings.setValue('compass/enabled', enabled); self.compass.setVisible(enabled)

    def show_compass(self):
        self.compass.move(self.mapToGlobal(QPoint(24, 70)))
        self.compass_toggle.setChecked(True); self.compass.show(); self.compass.raise_()

    def side_button(self, which):
        self.media_action('pause' if which == 2 else 'back')

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
        if action == 'immersive': self.toggle_immersive(); return
        if action == 'visible':
            if self.isVisible() and not self.isMinimized(): self.floating.show(); self.hide()
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
                self.media_action(action); return True, 0
        return old_native(self, event_type, message)

    def close(self, event):
        self.subtitles.close()
        self.episode_keys.stop()
        self.system_episode_keys.stop()
        self.side_buttons.stop()
        self.raw_mouse.stop()
        if self._fullscreen_core is not None:
            self._fullscreen_core.ContainsFullScreenElementChanged -= self._fullscreen_handler
        self.settings.setValue('compass/position', self.compass.pos()); self.compass.close()
        old_close(self, event)

    cls.__init__ = initialize; cls.closeEvent = close; cls.nativeEvent = native
    cls.toggle_immersive = toggle_immersive; cls.set_compass = set_compass; cls.choose_compass_color = choose_color
    cls.show_compass = show_compass; cls.side_button = side_button; cls.set_mouse_enabled = set_mouse_enabled
    cls.mouse_observed = mouse_observed; cls.set_injected_enabled = set_injected_enabled
    cls.current_mouse = current_mouse; cls.change_mouse_mode = change_mouse_mode
    cls.sync_fullscreen = sync_fullscreen
    cls.set_episode_keys = set_episode_keys
    cls.current_episode_keys = current_episode_keys; cls.change_episode_mode = change_episode_mode
    cls.media_action = media_action
