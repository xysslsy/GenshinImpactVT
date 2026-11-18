"""A click-through caption at the bottom of the current display."""
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget


class DesktopSubtitle(QWidget):
    MIN_FONT_SIZE = 16
    MAX_FONT_SIZE = 56
    DEFAULT_FONT_SIZE = 26
    horizontal_padding = 19
    vertical_padding = 9
    text_flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)

    def __init__(self, owner):
        # Keep this top-level window independent of the player when it is hidden or minimized.
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput |
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowTitle('GenshinImpactVT 屏幕字幕')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.owner = owner
        self.caption = ''
        self.display_enabled = False
        self.recognition_enabled = False
        self.caption_font = QFont('Microsoft YaHei UI')
        self.caption_font.setPixelSize(self.DEFAULT_FONT_SIZE)
        self.caption_font.setWeight(QFont.Weight.DemiBold)

    def follow_player_screen(self):
        self.owner.windowHandle().screenChanged.connect(self.reposition)
        app = QGuiApplication.instance()
        for screen in app.screens():
            self.watch_screen(screen)
        app.screenAdded.connect(self.watch_screen)
        app.screenRemoved.connect(self.reposition)

    def watch_screen(self, screen):
        screen.availableGeometryChanged.connect(self.reposition)

    def set_enabled(self, enabled):
        self.display_enabled = bool(enabled)
        self.refresh()

    def set_font_size(self, size):
        size = max(self.MIN_FONT_SIZE, min(self.MAX_FONT_SIZE, size))
        if size == self.caption_font.pixelSize():
            return
        self.caption_font.setPixelSize(size)
        if self.isVisible():
            self.reposition()
            self.update()

    def set_recognition_enabled(self, enabled):
        self.recognition_enabled = bool(enabled)
        if not self.recognition_enabled:
            self.clear()

    def set_caption(self, text, _source):
        self.caption = str(text or '').strip()[:500] if self.recognition_enabled else ''
        self.refresh()

    def clear(self):
        self.set_caption('', '')

    def refresh(self):
        if not self.display_enabled or not self.caption:
            self.hide()
            return
        self.reposition()
        self.show()
        self.update()

    def reposition(self, *_):
        if not self.display_enabled or not self.caption:
            return
        screen = self.owner.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        padding_x = 2 * self.horizontal_padding
        padding_y = 2 * self.vertical_padding
        metrics = QFontMetrics(self.caption_font)
        maximum_width = max(1, min(1050, int(area.width() * 0.86) - padding_x))
        line_width = max(metrics.horizontalAdvance(line) for line in self.caption.split('\n'))
        text_width = min(maximum_width, max(1, line_width + 4))
        text_box = metrics.boundingRect(QRect(0, 0, text_width, area.height()), self.text_flags, self.caption)
        bottom_gap = max(12, min(32, area.height() // 30))
        width = text_width + padding_x
        height = min(max(metrics.height(), text_box.height()) + padding_y, area.height() - bottom_gap)
        self.setGeometry(area.x() + (area.width() - width) // 2,
                         area.bottom() + 1 - bottom_gap - height, width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.caption_font)
        text_box = self.rect().adjusted(self.horizontal_padding, self.vertical_padding,
                                       -self.horizontal_padding, -self.vertical_padding)
        painter.setPen(QColor(8, 12, 15, 190))
        for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
            painter.drawText(text_box.translated(dx, dy), self.text_flags, self.caption)
        painter.setPen(QColor('#f6f8fa'))
        painter.drawText(text_box, self.text_flags, self.caption)
