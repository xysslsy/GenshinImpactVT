"""Background Windows Raw Input listener limited to mouse side buttons."""
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QObject, Signal

user32 = ctypes.WinDLL('user32', use_last_error=True)

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [('usage_page', wintypes.USHORT), ('usage', wintypes.USHORT),
                ('flags', wintypes.DWORD), ('target', wintypes.HWND)]

class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('size', wintypes.DWORD),
                ('device', wintypes.HANDLE), ('wparam', wintypes.WPARAM)]

class RAWMOUSE(ctypes.Structure):
    _fields_ = [('flags', wintypes.USHORT), ('buttons', wintypes.ULONG),
                ('raw_buttons', wintypes.ULONG), ('x', wintypes.LONG),
                ('y', wintypes.LONG), ('extra', wintypes.ULONG)]

class RAWINPUT(ctypes.Structure):
    _fields_ = [('header', RAWINPUTHEADER), ('mouse', RAWMOUSE)]

user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                   ctypes.POINTER(wintypes.UINT), wintypes.UINT]
user32.GetRawInputData.restype = wintypes.UINT

def side_buttons(flags):
    return [button for mask, button in ((0x0040, 1), (0x0100, 2)) if flags & mask]

class RawMouse(QObject):
    pressed = Signal(int)
    observed = Signal(int, bool)

    def __init__(self, hwnd, parent=None):
        super().__init__(parent); self.hwnd = hwnd; self.active = False

    def start(self):
        if self.active: return True
        device = RAWINPUTDEVICE(1, 2, 0x100, self.hwnd)  # RIDEV_INPUTSINK
        self.active = bool(user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)))
        return self.active

    def stop(self):
        if self.active:
            device = RAWINPUTDEVICE(1, 2, 1, None)  # RIDEV_REMOVE
            user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device))
            self.active = False

    def handle_input(self, handle):
        if not self.active: return
        size = wintypes.UINT(ctypes.sizeof(RAWINPUT)); data = RAWINPUT()
        count = user32.GetRawInputData(handle, 0x10000003, ctypes.byref(data), ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        if count == 0xffffffff or count < ctypes.sizeof(RAWINPUTHEADER) + ctypes.sizeof(RAWMOUSE) or data.header.type != 0: return
        for button in side_buttons(data.mouse.buttons & 0xffff):
            self.observed.emit(button, False); self.pressed.emit(button)
