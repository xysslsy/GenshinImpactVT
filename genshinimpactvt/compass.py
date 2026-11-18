"""Transparent eight-way direction cues for the minimap overlay."""
import math
from .subtitle_text import directions
from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


def direction_angle(active):
    if {'东', '西'} <= active or {'南', '北'} <= active:
        return None
    east = int('东' in active) - int('西' in active)
    north = int('北' in active) - int('南' in active)
    return math.degrees(math.atan2(north, east)) if east or north else None


def active_label_color(color):
    pale = QColor('#f2f7fa')
    return QColor.fromRgbF((color.redF() + 2 * pale.redF()) / 3,
                           (color.greenF() + 2 * pale.greenF()) / 3,
                           (color.blueF() + 2 * pale.blueF()) / 3)


def direction_highlight(active, width, height, color, pixel_ratio=1.0):
    image = QImage(round(width * pixel_ratio), round(height * pixel_ratio),
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(pixel_ratio)
    image.fill(Qt.GlobalColor.transparent)
    angle = direction_angle(active)
    if angle is None:
        return image

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(width / 2, height / 2)
    scale = min(width, height) / 320
    painter.scale(scale, scale)
    rim = QRectF(-111, -111, 222, 222)
    segments = ((-42, -26, 7, 170), (-16, 16, 12, 255), (26, 42, 7, 170))
    outline = QColor('#0a2029')

    def pen(ink, line_width, alpha):
        tint = QColor(ink)
        tint.setAlpha(alpha)
        painter.setPen(QPen(tint, line_width, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

    for start, end, line_width, brightness in segments:
        arc = (rim, round((angle + start) * 16), (end - start) * 16)
        # Graduated translucent strokes form a cached halo behind the crisp rim.
        for spread, alpha in ((22, 5), (18, 8), (14, 12), (10, 19), (7, 25)):
            pen(color, line_width + spread, alpha * brightness // 255)
            painter.drawArc(*arc)
        pen(outline, line_width + 4, 215)
        painter.drawArc(*arc)
        pen(color.lighter(120), line_width, brightness)
        painter.drawArc(*arc)

    painter.rotate(-angle)
    for tip, height, brightness in ((36, 9, 255), (50, 7, 185)):
        arrow = QPainterPath()
        arrow.moveTo(tip - 9, -height)
        arrow.lineTo(tip, 0)
        arrow.lineTo(tip - 9, height)
        pen(outline, 7, 230)
        painter.drawPath(arrow)
        pen(color.lighter(120), 3.5, brightness)
        painter.drawPath(arrow)
    painter.end()
    return image


class Compass(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAutoFillBackground(False);self.setStyleSheet('background:transparent;')
        self.resize(240, 240)
        self.color = QColor('#8de7ff')
        self.glow_enabled=True;self.strength=.75;self.hold_seconds=5
        self.active = set()
        self._drag = None
        self._opacity=0.;self._phase='off'
        self._glow_cache_key=None;self._glow_image=None
        self.animation=QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._animate_opacity)
        self.animation.finished.connect(self._animation_finished)
        self.expiry = QTimer(self); self.expiry.setSingleShot(True)
        self.expiry.timeout.connect(self._fade_out)

    def set_text(self, text):
        active=directions(text)
        if not active: return  # Subtitle gaps must not cancel the last direction cue.
        changed=active!=self.active
        self.active=active
        if self.isVisible() and self.glow_enabled and (changed or self._phase in ('off','out')):
            self._start_animation(0. if changed else self._opacity,1.,160,'in')
        else:
            self.animation.stop();self._opacity=1.;self._phase='hold';self.update()
        self.expiry.start(self.hold_seconds*1000)

    def set_hold_seconds(self, seconds):
        self.hold_seconds=max(1,min(30,int(seconds)))
        if self.expiry.isActive(): self.expiry.start(self.hold_seconds*1000)

    def clear(self):
        self.expiry.stop();self.animation.stop()
        self.active=set();self._opacity=0.;self._phase='off';self.update()

    def _start_animation(self,start,end,duration,phase):
        self.animation.stop();self._phase=phase;self._opacity=start
        self.animation.setDuration(duration);self.animation.setStartValue(start);self.animation.setEndValue(end)
        self.animation.start();self.update()

    def _animate_opacity(self,value):
        self._opacity=float(value);self.update()

    def _animation_finished(self):
        if self._phase=='out':self.clear()
        else:self._phase='hold'

    def _fade_out(self):
        if not self.isVisible() or not self.glow_enabled:
            self.clear();return
        self._start_animation(self._opacity,0.,450,'out')

    def set_glow_enabled(self,enabled):
        self.glow_enabled=bool(enabled)
        if not enabled:
            self.animation.stop();self._opacity=1. if self.active else 0.
            if self._phase=='out':self.clear()
        self.update()

    def set_strength(self,percent):
        self.strength=max(.15,min(1.,percent/100));self.update()

    def set_extent(self,size):
        size = max(140, min(420, int(size)))
        center = self.frameGeometry().center()
        self.resize(size, size)
        area = self.screen().availableGeometry()
        x = max(area.left(), min(center.x() - size // 2, area.right() - size + 1))
        y = max(area.top(), min(center.y() - size // 2, area.bottom() - size + 1))
        self.move(x, y)
        self.update()

    def place_at_startup(self, position, screen):
        if isinstance(position, QPoint):
            saved_frame = QRect(position, self.size())
            if any(display.availableGeometry().contains(saved_frame) for display in QGuiApplication.screens()):
                self.move(position)
                return
        self.move(screen.availableGeometry().topLeft() + QPoint(12, 12))

    def hideEvent(self,event):
        if self._phase=='out':self.clear()
        else:
            self.animation.stop();self._opacity=1. if self.active else 0.;self._phase='hold' if self.active else 'off'
        super().hideEvent(event)

    def closeEvent(self,event):
        self.clear();super().closeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.glow_enabled and self.active and self._opacity>0:
            pixel_ratio = self.devicePixelRatioF()
            key = (tuple(sorted(self.active)), self.width(), self.height(), self.color.rgba(), pixel_ratio)
            if key!=self._glow_cache_key:
                self._glow_image = direction_highlight(self.active, self.width(), self.height(), self.color, pixel_ratio)
                self._glow_cache_key=key
            painter.save();painter.setOpacity(self._opacity * self.strength)
            painter.drawImage(0,0,self._glow_image);painter.restore()
        font = QFont('Microsoft YaHei UI', 16, QFont.Weight.Bold); painter.setFont(font)
        w, h = self.width(), self.height()
        label_tint = active_label_color(self.color)
        for label, rect in [('北', (w//2-20, 4, 40, 32)), ('南', (w//2-20, h-36, 40, 32)),
                            ('西', (4, h//2-16, 40, 32)), ('东', (w-44, h//2-16, 40, 32))]:
            painter.setPen(QColor(20, 20, 20, 220))
            painter.drawText(rect[0]+1, rect[1]+1, rect[2], rect[3], Qt.AlignmentFlag.AlignCenter, label)
            painter.setPen(label_tint if label in self.active else QColor('white'))
            painter.drawText(*rect, Qt.AlignmentFlag.AlignCenter, label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None
