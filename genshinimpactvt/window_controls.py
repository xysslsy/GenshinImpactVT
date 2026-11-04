"""Recoverable floating controls: tray and native window-menu entry points."""
import ctypes
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QApplication


class WindowControls(QObject):
    RESTORE = 0x1e00
    TOGGLE = 0x1e10

    def __init__(self, main):
        super().__init__(main); self.main = main
        self.menu = QMenu(main)
        self.toggle_action = self.menu.addAction('显示 / 隐藏悬浮控制条', self.toggle)
        self.menu.addAction('显示主窗口', main.restore_main)
        self.restore_action = self.menu.addAction('恢复正常界面', main.restore_normal)
        self.menu.addSeparator(); self.menu.addAction('退出软件', main.close)
        icon = QApplication.windowIcon()
        if icon.isNull(): icon = QIcon(str(Path(__file__).resolve().parents[1]/'assets/app.ico'))
        self.tray = QSystemTrayIcon(icon,self); self.tray.setToolTip('GenshinImpactVT · 点击显示或隐藏控制条')
        self.tray.setContextMenu(self.menu); self.tray.activated.connect(self.activated)
        if QSystemTrayIcon.isSystemTrayAvailable(): self.tray.show()
        user32 = ctypes.WinDLL('user32',use_last_error=True)
        user32.GetSystemMenu.argtypes = [wintypes.HWND,wintypes.BOOL]; user32.GetSystemMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU,wintypes.UINT,ctypes.c_size_t,wintypes.LPCWSTR]
        user32.AppendMenuW.restype = wintypes.BOOL
        menu = user32.GetSystemMenu(int(main.winId()),False)
        self.system_menu_available = bool(menu and user32.AppendMenuW(menu,0,self.RESTORE,'恢复正常界面')
            and user32.AppendMenuW(menu,0,self.TOGGLE,'显示 / 隐藏悬浮控制条'))

    def activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger: self.toggle()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick: self.main.restore_normal()

    def toggle(self):
        bar = self.main.floating
        if bar.isVisible(): bar.hide(); return
        bar.adjustSize()
        pos = self.main.settings.value('controls/position', self.main.pos())
        screen = QApplication.screenAt(pos) or self.main.screen()
        rect = screen.availableGeometry()
        bar.move(max(rect.left(),min(pos.x(),rect.right()-bar.width())),
                 max(rect.top(),min(pos.y(),rect.bottom()-bar.height())))
        bar.show()  # WA_ShowWithoutActivating keeps the foreground game's keyboard focus.

    def handle_native(self, message):
        if message.message != 0x112: return False
        action = int(message.wParam)&0xfff0
        if action not in (self.RESTORE,self.TOGGLE): return False
        QTimer.singleShot(0,self.main.restore_normal if action == self.RESTORE else self.toggle)
        return True

    def close(self): self.tray.hide(); self.menu.close()
