import ctypes
from ctypes import wintypes
import json
import os
import sys
from pathlib import Path
import multiprocessing

# PyInstaller's spawned OCR worker must branch before loading Qt or .NET.
if __name__ == '__main__':
    multiprocessing.freeze_support()

# Default package tests use a separate profile. The explicit Bilibili test uses
# the normal browser session, with separate application settings/database.
SMOKE_DIR = None
BILI_TEST = '--self-test-bili' in sys.argv
if '--self-test' in sys.argv:
    index = sys.argv.index('--self-test')
    if index + 1 >= len(sys.argv): raise ValueError('--self-test requires a directory')
    SMOKE_DIR = Path(sys.argv[index + 1]).resolve()
    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    if not BILI_TEST: os.environ['LOCALAPPDATA'] = str(SMOKE_DIR)
from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem, QStackedWidget,
    QCheckBox)
from genshinimpactvt.browser import BrowserHost, DATA, user32
from genshinimpactvt.storage import Store
from genshinimpactvt.urls import normalize_url
from genshinimpactvt.subtitle_overlay import SubtitleOverlay
from genshinimpactvt.version import APP_NAME,APP_TITLE,__version__,DISPLAY_VERSION

user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
STYLE = '''
QWidget { color:#282825; background:#ffffff; font-family:"Microsoft YaHei UI"; font-size:14px; }
QWidget#side { background:#f7f7f5; border-right:1px solid #e9e9e5; }
QLabel#brand { font-size:14px; font-weight:700; padding:12px 6px 14px; background:transparent; }
QLabel#heading { font-size:23px; font-weight:700; padding:12px 0; }
QLabel#muted { color:#777773; font-size:12px; }
QPushButton { background:#f6f6f4; border:1px solid #e8e8e5; border-radius:7px; padding:8px 12px; }
QPushButton:hover { background:#ecece9; } QPushButton:pressed { background:#e1e1dd; }
QPushButton#nav { text-align:left; background:transparent; border:0; padding:10px 12px; }
QPushButton#nav:hover { background:#eaeae7; } QPushButton#nav:checked { background:#e5e5e1; font-weight:600; }
QLineEdit,QKeySequenceEdit { border:1px solid #dededb; border-radius:7px; padding:8px; background:white; }
QLineEdit:focus,QKeySequenceEdit:focus { border:1px solid #888882; }
QListWidget { border:1px solid #ecece9; border-radius:8px; padding:6px; outline:none; }
QListWidget::item { padding:11px; border-radius:5px; } QListWidget::item:selected { background:#ecece9; color:#222; }
'''

def button(label, action, nav=False):
    b = QPushButton(label); b.clicked.connect(action)
    if nav: b.setObjectName('nav'); b.setCheckable(True)
    return b

class Floating(QWidget):
    def __init__(self, main):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.main = main; self.setWindowTitle(APP_TITLE+' · 控制')
        layout = QHBoxLayout(self); layout.setContentsMargins(8,8,8,8)
        layout.addWidget(button('←', main.browser.back)); layout.addWidget(button('→', main.browser.forward))
        layout.addWidget(button('刷新', main.browser.reload))
        self.pin = QCheckBox('置顶'); self.pin.toggled.connect(main.set_topmost); layout.addWidget(self.pin)
        layout.addWidget(button('显示主窗口', main.restore_main))
        layout.addWidget(button('显示 / 隐藏工具栏', main.toggle_immersive))

class Main(QMainWindow):
    def __init__(self, data_dir=DATA):
        super().__init__(); self.data_dir = Path(data_dir); self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(self.data_dir / 'settings.ini'), QSettings.Format.IniFormat)
        self.store = Store(self.data_dir / 'library.sqlite3'); self.current_url = ''
        self.setWindowTitle(APP_TITLE); self.resize(960, 620); self.setMinimumSize(480, 300)
        self.browser = BrowserHost(); self.browser.ready.connect(lambda: self.status.setText('浏览器已就绪'))
        self.browser.failed.connect(self.error); self.browser.navigated.connect(self.navigated)
        self.browser.source_changed.connect(self.address_changed); self.browser.loading.connect(lambda: self.status.setText('正在加载…'))
        root = QWidget(); self.setCentralWidget(root); outer = QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        side = QWidget(); side.setObjectName('side'); side.setFixedWidth(190); nav = QVBoxLayout(side); nav.setContentsMargins(14,18,14,18)
        brand = QLabel(APP_NAME+'\n'+DISPLAY_VERSION); brand.setObjectName('brand'); nav.addWidget(brand)
        self.stack = QStackedWidget(); self.navbuttons = []
        for title, page in [('浏览器', self.make_browser()), ('收藏', self.make_list('bookmarks')), ('历史记录', self.make_list('history')), ('设置', self.make_settings())]:
            index = self.stack.addWidget(page); b = button(title, lambda checked=False, n=index: self.select(n), True); self.navbuttons.append(b); nav.addWidget(b)
        nav.addStretch(); caption = QLabel('您的攻略工作台'); caption.setObjectName('muted'); nav.addWidget(caption)
        outer.addWidget(side); outer.addWidget(self.stack, 1); self.select(0)
        self.floating = Floating(self)
        self.pin.setChecked(self.settings.value('window/topmost', True, type=bool))
        geometry = self.settings.value('window/geometry')
        if geometry: self.restoreGeometry(geometry)
        self.show()
        self.set_topmost(self.pin.isChecked())
        start = self.settings.value('browser/last_url', '')
        if start: QTimer.singleShot(0, lambda: self.open_url(start))
        else: QTimer.singleShot(0, self.open_fixture)

    def make_browser(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(20,18,20,12); layout.setSpacing(12)
        bar = QHBoxLayout(); bar.addWidget(button('←', self.browser.back)); bar.addWidget(button('→', self.browser.forward)); bar.addWidget(button('↻', self.browser.reload))
        self.address = QLineEdit(); self.address.setPlaceholderText('输入网址，例如 example.com'); self.address.returnPressed.connect(lambda: self.open_url(self.address.text())); bar.addWidget(self.address, 1)
        bar.addWidget(button('前往', lambda: self.open_url(self.address.text()))); bar.addWidget(button('☆ 收藏', self.add_bookmark)); layout.addLayout(bar)
        layout.addWidget(self.browser, 1)
        bottom = QHBoxLayout(); self.status = QLabel('正在启动浏览器…'); self.status.setObjectName('muted'); bottom.addWidget(self.status, 1)
        self.pin = QCheckBox('窗口置顶'); self.pin.toggled.connect(self.set_topmost); bottom.addWidget(self.pin)
        bottom.addWidget(button('悬浮控制', self.toggle_floating)); layout.addLayout(bottom)
        self.subtitle_overlay = SubtitleOverlay(self.browser, self)
        return page

    def make_list(self, kind):
        page = QWidget(); box = QVBoxLayout(page); box.setContentsMargins(38,30,38,30)
        title = QLabel('收藏' if kind == 'bookmarks' else '历史记录'); title.setObjectName('heading'); box.addWidget(title)
        info = QLabel('双击打开网页 · 选中后可删除'); info.setObjectName('muted'); box.addWidget(info)
        listing = QListWidget(); setattr(self, kind + '_list', listing); listing.itemDoubleClicked.connect(lambda item: self.open_url(item.data(Qt.ItemDataRole.UserRole)[1])); box.addWidget(listing, 1)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(button('删除选中项', lambda: self.delete_selected(kind))); box.addLayout(row)
        return page

    def make_settings(self):
        page = QWidget(); box = QVBoxLayout(page); box.setContentsMargins(38,30,38,30)
        title = QLabel('设置'); title.setObjectName('heading'); box.addWidget(title)
        info = QLabel('视频控制'); info.setObjectName('muted'); box.addWidget(info)
        box.addStretch(); return page

    def select(self, index):
        self.stack.setCurrentIndex(index)
        for i,b in enumerate(self.navbuttons): b.setChecked(i == index)
        if index in (1,2): self.refresh_list('bookmarks' if index == 1 else 'history')

    def refresh_list(self, kind):
        listing = getattr(self, kind + '_list'); listing.clear()
        try:
            for row_id,title,url in self.store.rows(kind):
                item = QListWidgetItem(f'{title}\n{url}' if title != url else url); item.setData(Qt.ItemDataRole.UserRole, (row_id,url)); listing.addItem(item)
        except Exception as exc: self.error(f'读取失败：{exc}')

    def delete_selected(self, kind):
        listing = getattr(self, kind + '_list'); item = listing.currentItem()
        if item:
            try: self.store.delete(kind, item.data(Qt.ItemDataRole.UserRole)[0]); self.refresh_list(kind)
            except Exception as exc: self.error(f'删除失败：{exc}')

    def open_fixture(self):
        self.status.setText('正在加载本地测试页面…'); self.browser.start((Path(__file__).parent / 'fixture.html').resolve().as_uri())

    def open_url(self, value):
        try:
            url = normalize_url(value); self.select(0); self.status.setText('正在加载…')
            if not self.browser.web: self.browser.start(url)
            else: self.browser.navigate(url)
        except Exception as exc: self.error(str(exc))

    def address_changed(self, url): self.address.setText(url)
    def navigated(self, url, success, error):
        self.status.setText('页面加载完成' if success else '页面加载失败：' + error)
        if success and url.startswith(('http://','https://')):
            self.current_url = url
            try: self.store.visit(url, url); self.settings.setValue('browser/last_url', url)
            except Exception as exc: self.error(f'保存历史失败：{exc}')

    def add_bookmark(self):
        try:
            url = normalize_url(self.address.text()); self.store.bookmark(url, url); self.status.setText('已保存到收藏')
        except Exception as exc: self.error(f'收藏失败：{exc}')

    def error(self, message): self.status.setText(str(message))
    def set_topmost(self, enabled):
        self.pin.blockSignals(True); self.pin.setChecked(enabled); self.pin.blockSignals(False)
        if hasattr(self, 'floating'):
            self.floating.pin.blockSignals(True); self.floating.pin.setChecked(enabled); self.floating.pin.blockSignals(False)
        if user32.SetWindowPos(int(self.winId()), -1 if enabled else -2, 0,0,0,0, 0x0001 | 0x0002 | 0x0010):
            self.settings.setValue('window/topmost', enabled)
        else:
            self.status.setText('设置窗口置顶失败，请重试。')
    def toggle_floating(self): self.floating.setVisible(not self.floating.isVisible())
    def restore_main(self): self.showNormal(); self.raise_(); self.activateWindow()

    def nativeEvent(self, event_type, message):
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event):
        self.settings.setValue('window/geometry', self.saveGeometry()); self.settings.sync()
        self.floating.close(); self.browser.close_browser(); self.store.close(); super().closeEvent(event); QApplication.instance().quit()

from genshinimpactvt.enhancements import install
install(Main)

def main():
    ole = ctypes.OleDLL('ole32'); ole.OleInitialize(None)
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GenshinImpactVT.Desktop.1')
    app = QApplication(sys.argv[:1]); app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / 'assets' / 'app.ico')))
    app.setApplicationName(APP_NAME);app.setApplicationVersion(__version__)
    app.setStyleSheet(STYLE); window = Main(SMOKE_DIR/'app') if SMOKE_DIR is not None and BILI_TEST else Main()
    test_result = {'ready': False, 'navigation': False, 'icon': not app.windowIcon().isNull(), 'errors': []}
    if SMOKE_DIR is not None:
        ocr_test = '--self-test-ocr' in sys.argv
        finished = False
        window.browser.ready.connect(lambda: test_result.update(ready=True))
        window.browser.navigated.connect(lambda url, success, error: test_result.update(navigation=success))
        window.browser.failed.connect(lambda error: test_result['errors'].append(error))
        def finish_test():
            nonlocal finished
            if finished: return
            finished = True
            if ocr_test:
                test_result['ocr'] = '东' in window.compass.active
                test_result['ocr_text'] = window.subtitles.page.text.text()
                test_result['ocr_status'] = window.subtitles.page.status.text()
                test_result['ocr_samples'] = window.subtitles.samples
            (SMOKE_DIR / 'result.json').write_text(json.dumps(test_result, ensure_ascii=False, indent=2), encoding='utf-8')
            window.close()
        if BILI_TEST:
            from genshinimpactvt.bilibili_selftest import setup_test
            setup_test(window,test_result,sys.argv[sys.argv.index('--self-test-bili')+1],finish_test)
        if ocr_test:
            def start_ocr_test():
                service = window.subtitles
                service.page.mode.setCurrentIndex(service.page.mode.findData('ocr'))
                service.page.enabled.setChecked(True)
                service.open_demo()
            window.browser.ready.connect(lambda: QTimer.singleShot(600,start_ocr_test))
            ocr_watch = QTimer(window)
            ocr_watch.timeout.connect(lambda: finish_test() if '东' in window.compass.active else None)
            ocr_watch.start(200)
        QTimer.singleShot(30000 if BILI_TEST else 20000 if ocr_test else 10000, finish_test)
    result = app.exec(); ole.OleUninitialize()
    if SMOKE_DIR is not None and (not test_result['ready'] or not test_result['navigation'] or not test_result['icon'] or test_result['errors'] or test_result.get('ocr') is False or test_result.get('native_subtitles') is False): return 1
    return result

if __name__ == '__main__': sys.exit(main())
