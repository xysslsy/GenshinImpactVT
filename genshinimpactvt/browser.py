"""Own proof-of-concept host for the official WebView2 WinForms control."""
from pathlib import Path
import ctypes
import os
import winreg

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget
from .urls import normalize_url

ROOT = Path(__file__).resolve().parent.parent
SDK = ROOT / ".deps" / "webview2"
# Preserve the original data directory so existing bookmarks and settings stay available.
DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MaBaoNext"
RUNTIME_KEY = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

def evergreen_version():
    for hive, flags in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
                        (winreg.HKEY_CURRENT_USER, 0)):
        try:
            with winreg.OpenKey(hive, RUNTIME_KEY, 0, winreg.KEY_READ | flags) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return version
        except OSError:
            continue
    return None

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetParent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.SetParent.restype = ctypes.c_void_p
user32.GetParent.argtypes = [ctypes.c_void_p]
user32.GetParent.restype = ctypes.c_void_p
user32.MoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, ctypes.c_bool]
user32.MoveWindow.restype = ctypes.c_bool

class BrowserHost(QWidget):
    ready = Signal()
    navigated = Signal(str, bool, str)
    source_changed = Signal(str)
    loading = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.panel = self.web = None
        self._subscriptions = []
        self._dll_cookie = None
        self._disposed = False
        self._loading = False
        self._core = None
        self._new_window_handler = self._on_new_window

    def start(self, initial_url):
        version = evergreen_version()
        if not version:
            self.failed.emit("未检测到 WebView2 Evergreen Runtime，请安装后重新启动。")
            return
        missing = [p.name for p in (SDK / "Microsoft.Web.WebView2.Core.dll",
                   SDK / "Microsoft.Web.WebView2.WinForms.dll", SDK / "WebView2Loader.dll") if not p.is_file()]
        if missing:
            self.failed.emit("WebView2 SDK 文件缺失：" + ", ".join(missing) + "。请运行 setup_webview2.py。")
            return
        try:
            self._dll_cookie = os.add_dll_directory(str(SDK))
            import pythonnet
            pythonnet.load("netfx")
            import clr
            clr.AddReference("System.Windows.Forms")
            clr.AddReference("System.Drawing")
            clr.AddReference(str(SDK / "Microsoft.Web.WebView2.Core.dll"))
            clr.AddReference(str(SDK / "Microsoft.Web.WebView2.WinForms.dll"))
            from System import Uri
            from System.Windows.Forms import DockStyle, Panel
            from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties

            DATA.mkdir(parents=True,exist_ok=True)
            self._uri = Uri
            self.panel = Panel()
            self.panel.CreateControl()
            self._handle = int(self.panel.Handle.ToInt64())
            ctypes.set_last_error(0)
            previous = user32.SetParent(self._handle, int(self.winId()))
            error = ctypes.get_last_error()
            if not previous and error:
                raise ctypes.WinError(error)
            self.panel.Visible = True
            self.web = WebView2()
            self.web.Dock = DockStyle.Fill
            self.panel.Controls.Add(self.web)
            properties = CoreWebView2CreationProperties()
            properties.UserDataFolder = str(DATA / "browser-profile")
            self.web.CreationProperties = properties
            self._subscriptions = [self._on_initialized, self._on_navigation,
                                   self._on_source_changed]
            self.web.CoreWebView2InitializationCompleted += self._subscriptions[0]
            self.web.NavigationCompleted += self._subscriptions[1]
            self.web.SourceChanged += self._subscriptions[2]
            self._resize_native()
            self._loading = True
            self.web.Source = Uri(initial_url)
        except Exception as exc:
            self.failed.emit(f"浏览器初始化失败：{type(exc).__name__}: {exc}")

    def _on_initialized(self, sender, event):
        if not event.IsSuccess:
            self.failed.emit(f"WebView2 创建失败：{event.InitializationException}")
            return
        self._core = self.web.CoreWebView2
        self._core.NewWindowRequested += self._new_window_handler
        self.ready.emit()

    def _on_new_window(self, sender, event):
        # Suppress the default popup first, including for unsupported schemes.
        event.Handled = True
        try:
            url = normalize_url(str(event.Uri))
        except ValueError:
            self.failed.emit('此链接不是 HTTP(S) 网页，无法在当前页面打开。')
            return
        # Navigate after returning from the COM callback, avoiding reentrancy.
        QTimer.singleShot(0, lambda: self.navigate(url) if not self._disposed else None)

    def _on_navigation(self, sender, event):
        self._loading = False
        url = str(self.web.Source) if self.web and self.web.Source else ""
        self.navigated.emit(url, bool(event.IsSuccess), str(event.WebErrorStatus))

    def _on_source_changed(self, sender, event):
        if self.web and self.web.Source:
            self.source_changed.emit(str(self.web.Source))

    def navigate(self, url):
        self.loading.emit()
        if self.web:
            self.web.Source = self._uri(url)

    def back(self):
        if self.web and self.web.CoreWebView2 and self.web.CanGoBack:
            self.web.GoBack()

    def forward(self):
        if self.web and self.web.CoreWebView2 and self.web.CanGoForward:
            self.web.GoForward()

    def reload(self):
        if self.web and self.web.CoreWebView2:
            self.web.Reload()

    def execute_script(self, script):
        if not self.web or not self.web.CoreWebView2:
            raise RuntimeError("WebView2 尚未就绪")
        return self.web.CoreWebView2.ExecuteScriptAsync(script)

    def capture_preview(self):
        """Start on the Qt/.NET UI thread; caller polls the returned Task."""
        if not self.web or not self.web.CoreWebView2:
            raise RuntimeError('WebView2 尚未就绪')
        from System.IO import MemoryStream
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
        stream = MemoryStream()
        try:
            task = self.web.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream)
            return task, stream
        except Exception:
            stream.Dispose()
            raise

    def _resize_native(self):
        if self.panel and not self._disposed:
            ratio = self.devicePixelRatioF()
            ok = user32.MoveWindow(self._handle, 0, 0,
                                   max(1, round(self.width() * ratio)),
                                   max(1, round(self.height() * ratio)), True)
            if not ok:
                self.failed.emit(f"浏览器窗口调整失败：{ctypes.get_last_error()}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_native()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if self.web:
            self.web.Focus()

    def close_browser(self):
        if self._disposed:
            return
        self._disposed = True
        if self.web:
            if self._core is not None:
                self._core.NewWindowRequested -= self._new_window_handler
                self._core = None
            try:
                self.web.CoreWebView2InitializationCompleted -= self._subscriptions[0]
                self.web.NavigationCompleted -= self._subscriptions[1]
                self.web.SourceChanged -= self._subscriptions[2]
            except (AttributeError, IndexError):
                pass
            self.web.Dispose()
            self.web = None
        if self.panel:
            self.panel.Dispose()
            self.panel = None
