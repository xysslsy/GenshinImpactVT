"""Configurable Windows shortcuts; no keystroke recording or input suppression."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QPushButton, QKeySequenceEdit, QComboBox)

from .episode_keys import user32, HOOKPROC, KeyData

ACTIONS = {
    'pause': ('播放 / 暂停', ''), 'back': ('快退 5 秒', '5'),
    'forward': ('快进 5 秒', '6'), 'previous': ('上一集', '7'),
    'next': ('下一集', '8'), 'controls': ('显示 / 隐藏控制条', 'F9'),
    'immersive': ('切换极简模式', '0'), 'visible': ('显示 / 隐藏主窗口', '9'),
    'maximize': ('最大化 / 还原', 'F10'), 'restore': ('恢复正常界面', 'F11'),
    'compass': ('显示 / 隐藏方向浮窗', 'F8'),
}


@dataclass(frozen=True)
class Binding:
    text: str
    modifiers: int
    vk: int


def parse_binding(text):
    if not text.strip(): return None
    sequence = QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)
    if sequence.count() != 1: raise ValueError('每个动作只能设置一个按键或一组组合键')
    combination = sequence[0]
    key = combination.key().value
    modifiers = combination.keyboardModifiers()
    mod = (2 if modifiers & Qt.KeyboardModifier.ControlModifier else 0)
    mod |= 1 if modifiers & Qt.KeyboardModifier.AltModifier else 0
    mod |= 4 if modifiers & Qt.KeyboardModifier.ShiftModifier else 0
    mod |= 8 if modifiers & Qt.KeyboardModifier.MetaModifier else 0
    special = {Qt.Key.Key_Space.value:0x20, Qt.Key.Key_Tab.value:9,
        Qt.Key.Key_Escape.value:0x1b, Qt.Key.Key_Backspace.value:8,
        Qt.Key.Key_Return.value:13, Qt.Key.Key_Insert.value:0x2d,
        Qt.Key.Key_Delete.value:0x2e, Qt.Key.Key_Home.value:0x24,
        Qt.Key.Key_End.value:0x23, Qt.Key.Key_PageUp.value:0x21,
        Qt.Key.Key_PageDown.value:0x22, Qt.Key.Key_Left.value:0x25,
        Qt.Key.Key_Up.value:0x26, Qt.Key.Key_Right.value:0x27, Qt.Key.Key_Down.value:0x28}
    if 0x30 <= key <= 0x39 or 0x41 <= key <= 0x5a: vk = key
    elif Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F24.value: vk = 0x70+key-Qt.Key.Key_F1.value
    elif key in special: vk = special[key]
    else:
        user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
        user32.VkKeyScanW.restype = ctypes.c_short
        mapped = user32.VkKeyScanW(chr(key)) if 0x21 <= key <= 0x7e else -1
        if mapped == -1: raise ValueError('不支持此按键，请使用字母、数字、F 键或常见控制键')
        vk = mapped & 0xff
        shift = (mapped >> 8) & 7
        mod |= (4 if shift & 1 else 0) | (2 if shift & 2 else 0) | (1 if shift & 4 else 0)
    # F12 is reserved by Windows for debuggers; destructive/system sequences are not application shortcuts.
    if vk == 0x7b or (mod & 1 and vk in (9,0x73)) or (mod & 8):
        raise ValueError('该按键由系统保留，请换一个快捷键')
    return Binding(sequence.toString(QKeySequence.SequenceFormat.PortableText), mod, vk)


def validate_bindings(values):
    result = {}; seen = {}
    for action, (label, _) in ACTIONS.items():
        binding = parse_binding(values.get(action, ''))
        if binding:
            identity = (binding.modifiers, binding.vk)
            if identity in seen: raise ValueError(f'“{label}”与“{seen[identity]}”使用了相同按键')
            seen[identity] = label
        result[action] = binding
    return result


class KeyboardHook(QObject):
    pressed = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.handle = None; self.down = set(); self.bindings = {}; self.allow_injected = False
        self.callback = HOOKPROC(self._hook)

    def start(self):
        if not self.handle: self.handle = user32.SetWindowsHookExW(13, self.callback, None, 0)
        return bool(self.handle)

    def stop(self):
        if self.handle: user32.UnhookWindowsHookEx(self.handle); self.handle = None
        self.down.clear()

    def _hook(self, code, message, pointer):
        if code >= 0 and message in (0x100,0x101,0x104,0x105):
            event = ctypes.cast(pointer, ctypes.POINTER(KeyData)).contents
            vk = event.vkCode
            if not any(key == vk for _,key in self.bindings):
                return user32.CallNextHookEx(self.handle, code, message, pointer)
            if message in (0x101,0x105): self.down.discard(vk)
            elif vk not in self.down:
                self.down.add(vk)
                if self.allow_injected or not event.flags & 0x10:
                    mod = sum(bit for key,bit in ((0x11,2),(0x12,1),(0x10,4)) if user32.GetAsyncKeyState(key)&0x8000)
                    if any(user32.GetAsyncKeyState(key)&0x8000 for key in (0x5b,0x5c)): mod |= 8
                    action = self.bindings.get((mod,vk))
                    if action: self.pressed.emit(action)
        return user32.CallNextHookEx(self.handle, code, message, pointer)


class SystemKeys:
    def __init__(self, hwnd):
        self.hwnd = hwnd; self.bindings = {}; self.registered = {}; self.active = False
        user32.RegisterHotKey.argtypes = [wintypes.HWND,ctypes.c_int,wintypes.UINT,wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND,ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        self.error = ''

    def start(self):
        if self.active: return True
        for index,(action,binding) in enumerate(self.bindings.items()):
            if not binding: continue
            ident = 8500+index
            if not user32.RegisterHotKey(self.hwnd,ident,0x4000|binding.modifiers,binding.vk):
                self.error = f'{ACTIONS[action][0]}（{binding.text}）被占用或无法注册'
                self.stop(); return False
            self.registered[ident] = action
        self.active = True; self.error = ''; return True

    def stop(self):
        for ident in self.registered: user32.UnregisterHotKey(self.hwnd,ident)
        self.registered.clear(); self.active = False

    def action(self, ident): return self.registered.get(ident)


class ShortcutSettings(QWidget):
    def __init__(self, manager):
        super().__init__(); self.manager = manager; self.editing = False
        layout = QVBoxLayout(self); layout.setContentsMargins(0,8,0,12)
        title = QLabel('自定义快捷键'); title.setStyleSheet('font-weight:600'); layout.addWidget(title)
        note = QLabel('全局按键在其他程序中也生效。编辑期间暂停快捷键和侧键；留空可禁用某个动作。系统全局模式会占用所设按键。')
        note.setWordWrap(True); layout.addWidget(note)
        form = QFormLayout(); self.editors = {}
        for action,(label,_) in ACTIONS.items():
            editor = QKeySequenceEdit(); editor.setMaximumSequenceLength(1); editor.setClearButtonEnabled(True)
            self.editors[action] = editor; form.addRow(label,editor)
        self.mouse_editors = {}
        for which,label in ((2,'鼠标侧键上键'),(1,'鼠标侧键下键')):
            combo = QComboBox(); combo.addItem('不执行动作','')
            for action,(name,_) in ACTIONS.items(): combo.addItem(name,action)
            self.mouse_editors[which] = combo; form.addRow(label,combo)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.edit_button = QPushButton('编辑快捷键'); self.apply_button = QPushButton('保存并启用')
        self.cancel_button = QPushButton('取消'); self.default_button = QPushButton('恢复默认')
        for widget in (self.edit_button,self.apply_button,self.cancel_button,self.default_button): row.addWidget(widget)
        layout.addLayout(row); self.message = QLabel(''); self.message.setWordWrap(True); layout.addWidget(self.message)
        self.edit_button.clicked.connect(self.begin); self.apply_button.clicked.connect(self.apply)
        self.cancel_button.clicked.connect(self.cancel); self.default_button.clicked.connect(self.defaults)
        self.reload(); self.set_editing(False)

    def reload(self):
        for action,editor in self.editors.items(): editor.setKeySequence(QKeySequence(self.manager.values[action]))
        for which,combo in self.mouse_editors.items(): combo.setCurrentIndex(max(0,combo.findData(self.manager.mouse[which])))

    def set_editing(self, editing):
        self.editing = editing
        for widget in (*self.editors.values(),*self.mouse_editors.values(),self.apply_button,self.cancel_button,self.default_button): widget.setEnabled(editing)
        self.edit_button.setEnabled(not editing)

    def begin(self):
        self.manager.suspended = True; self.manager.stop(); self.set_editing(True)
        self.message.setText('正在编辑，快捷键已暂停。修改后点击“保存并启用”。')

    def defaults(self):
        for action,editor in self.editors.items(): editor.setKeySequence(QKeySequence(ACTIONS[action][1]))
        for which,action in ((2,'pause'),(1,'back')):
            self.mouse_editors[which].setCurrentIndex(self.mouse_editors[which].findData(action))

    def apply(self):
        values = {action:editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText) for action,editor in self.editors.items()}
        mouse = {which:combo.currentData() for which,combo in self.mouse_editors.items()}
        try: self.manager.apply(values,mouse)
        except ValueError as exc: self.message.setText(str(exc)); return
        self.set_editing(False); self.message.setText('快捷键已保存，下次启动继续使用。')

    def cancel(self):
        self.reload(); self.manager.suspended = False; self.manager.start()
        self.set_editing(False); self.message.setText('已恢复原来的快捷键。')


class Shortcuts(QObject):
    def __init__(self, main):
        super().__init__(main); self.main = main; self.settings = main.settings; self.suspended = False
        self.values = {key:self.settings.value('shortcuts/'+key,default) for key,(_,default) in ACTIONS.items()}
        try: self.bindings = validate_bindings(self.values)
        except ValueError:
            self.values = {key:default for key,(_,default) in ACTIONS.items()}; self.bindings = validate_bindings(self.values)
        self.mouse = {which:self.settings.value('shortcuts/mouse'+str(which),default) for which,default in ((2,'pause'),(1,'back'))}
        self.hook = KeyboardHook(self); self.system = SystemKeys(int(main.winId()))
        self.hook.pressed.connect(self.dispatch,Qt.ConnectionType.QueuedConnection)
        self.page = ShortcutSettings(self)

    def dispatch(self, action):
        if not self.suspended: self.main.media_action(action)

    def stop(self): self.hook.stop(); self.system.stop()

    def start(self):
        self.stop()
        if self.suspended or not self.main.episode_toggle.isChecked(): return True
        self.hook.bindings = {(b.modifiers,b.vk):action for action,b in self.bindings.items() if b}
        self.system.bindings = self.bindings
        backend = self.system if self.main.episode_mode.currentData() == 'system' else self.hook
        ok = backend.start()
        self.main.episode_status.setText('自定义快捷键已启用。' if ok else (self.system.error or '键盘监听启动失败，请重试。'))
        return ok

    def apply(self, values, mouse):
        bindings = validate_bindings(values)
        if any(action and action not in ACTIONS for action in mouse.values()): raise ValueError('无效侧键动作')
        old_values,old_bindings,old_mouse = self.values,self.bindings,self.mouse
        self.values = {key:b.text if b else '' for key,b in bindings.items()}; self.bindings = bindings; self.mouse = dict(mouse)
        self.suspended = False
        if not self.start():
            error = self.system.error or '无法启用键盘监听'
            self.values,self.bindings,self.mouse = old_values,old_bindings,old_mouse
            self.suspended = True; self.stop(); raise ValueError(error+'；配置未保存，可修改后重试或取消。')
        for key,value in self.values.items(): self.settings.setValue('shortcuts/'+key,value)
        for which,action in self.mouse.items(): self.settings.setValue('shortcuts/mouse'+str(which),action)
        self.settings.sync()
