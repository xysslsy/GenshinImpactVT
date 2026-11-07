"""Compositor opacity without recreating the native WebView2 host HWND."""
from PySide6.QtCore import QObject,Signal


class WindowOpacity(QObject):
    changed=Signal(int)

    def __init__(self,main):
        super().__init__(main);self.main=main
        try:percent=int(main.settings.value('window/opacity_percent',100))
        except (TypeError,ValueError):percent=100
        self.percent=100;self.set_percent(percent)

    def set_percent(self,percent):
        percent=max(20,min(100,int(percent)))
        self.main.setWindowOpacity(percent/100)
        self.percent=percent
        self.main.settings.setValue('window/opacity_percent',percent)
        self.changed.emit(percent)

    def step(self,amount):self.set_percent(self.percent+amount)
