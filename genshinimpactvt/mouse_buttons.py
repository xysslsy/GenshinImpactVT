"""Observe side-button presses without consuming mouse input."""
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
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

class MouseData(ctypes.Structure):
    _fields_ = [('pt', wintypes.POINT), ('mouseData', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]

class SideButtons(QObject):
    pressed = Signal(int)
    observed = Signal(int, bool)

    def __init__(self, parent=None, *, allow_injected=False):
        super().__init__(parent); self.handle = None; self.allow_injected = allow_injected
        self.callback = HOOKPROC(self._hook)

    def start(self):
        if self.handle: return True
        self.handle = user32.SetWindowsHookExW(14, self.callback, None, 0)
        return bool(self.handle)

    def stop(self):
        if self.handle:
            user32.UnhookWindowsHookEx(self.handle); self.handle = None

    def _hook(self, code, message, pointer):
        if code >= 0 and message == 0x020B:
            event = ctypes.cast(pointer, ctypes.POINTER(MouseData)).contents
            self.process(event)
        return user32.CallNextHookEx(self.handle, code, message, pointer)

    def process(self, event):
        button = (event.mouseData >> 16) & 0xffff
        if button not in (1, 2): return
        self.observed.emit(button, bool(event.flags & 1))
        if self.allow_injected or not (event.flags & 1):
            self.pressed.emit(button)
