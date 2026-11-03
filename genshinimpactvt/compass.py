"""Transparent direction indicator and conservative subtitle parsing."""
import re
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget


def directions(text):
    # Exclude common non-directional compounds and do not guess at negation.
    text = re.sub(r'东西|东西方|东西南北|不往[东西南北]|不是[东西南北]', '', text or '')
    return {c for c in '东西南北' if c in text}


class Compass(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(180, 180)
        self.color = QColor('#4080ff')
        self.active = set()
        self._drag = None
        self.expiry = QTimer(self); self.expiry.setSingleShot(True)
        self.expiry.timeout.connect(self.clear)

    def set_text(self, text):
        self.active = directions(text); self.update()
        self.expiry.start(2500)

    def clear(self):
        self.active = set(); self.update()

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont('Microsoft YaHei UI', 16, QFont.Weight.Bold); painter.setFont(font)
        w, h = self.width(), self.height()
        for label, rect in [('北', (w//2-20, 4, 40, 32)), ('南', (w//2-20, h-36, 40, 32)),
                            ('西', (4, h//2-16, 40, 32)), ('东', (w-44, h//2-16, 40, 32))]:
            painter.setPen(QColor(20, 20, 20, 220))
            painter.drawText(rect[0]+1, rect[1]+1, rect[2], rect[3], Qt.AlignmentFlag.AlignCenter, label)
            painter.setPen(self.color if label in self.active else QColor('white'))
            painter.drawText(*rect, Qt.AlignmentFlag.AlignCenter, label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None
