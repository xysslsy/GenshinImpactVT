"""Observe 7/8 without consuming them or collecting other keyboard input."""
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QObject, Signal

user32 = ctypes.WinDLL('user32', use_last_error=True)
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HANDLE
user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]; user32.GetAsyncKeyState.restype = ctypes.c_short

class KeyData(ctypes.Structure):
    _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]

class EpisodeKeys(QObject):
    pressed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent); self.handle = None; self.down = set(); self.allow_injected = False
        self.callback = HOOKPROC(self._hook)

    def start(self):
        if not self.handle: self.handle = user32.SetWindowsHookExW(13, self.callback, None, 0)
        return bool(self.handle)

    def stop(self):
        if self.handle: user32.UnhookWindowsHookEx(self.handle); self.handle = None
        self.down.clear()

    def _hook(self, code, message, pointer):
        if code >= 0 and message in (0x100, 0x101, 0x104, 0x105):
            event = ctypes.cast(pointer, ctypes.POINTER(KeyData)).contents
            if event.vkCode in (0x37, 0x38):
                if message in (0x101, 0x105): self.down.discard(event.vkCode)
                elif event.vkCode not in self.down:
                    self.down.add(event.vkCode)
                    modified = any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5b, 0x5c))
                    if not modified and (self.allow_injected or not (event.flags & 0x10)):
                        self.pressed.emit('previous' if event.vkCode == 0x37 else 'next')
        return user32.CallNextHookEx(self.handle, code, message, pointer)

class SystemEpisodeKeys:
    """Optional Windows global hotkeys; registered keys are unavailable to normal typing."""
    IDS = {8407: ('previous', 0x37), 8408: ('next', 0x38)}

    def __init__(self, hwnd):
        self.hwnd = hwnd; self.active = False; self.error = 0
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL

    def start(self):
        if self.active: return True
        registered = []
        for ident, (_, vk) in self.IDS.items():
            if not user32.RegisterHotKey(self.hwnd, ident, 0x4000, vk):
                self.error = ctypes.get_last_error()
                for old in registered: user32.UnregisterHotKey(self.hwnd, old)
                return False
            registered.append(ident)
        self.active = True; self.error = 0; return True

    def stop(self):
        if self.active:
            for ident in self.IDS: user32.UnregisterHotKey(self.hwnd, ident)
            self.active = False

    def action(self, ident):
        return self.IDS[ident][0] if self.active and ident in self.IDS else None
