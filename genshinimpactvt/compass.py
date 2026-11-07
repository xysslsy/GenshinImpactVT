"""Transparent eight-way rim highlight, rendered only when needed."""
import math
from .subtitle_text import directions
from PySide6.QtCore import Qt, QPointF, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QRadialGradient, QConicalGradient, QImage
from PySide6.QtWidgets import QWidget


def ambient_position(active, width, height):
    """An anchor on the indicated rim sector. Conflicts produce no light."""
    if {'东','西'} <= active or {'南','北'} <= active:
        return None
    x = int('东' in active)-int('西' in active)
    y = int('南' in active)-int('北' in active)
    if not (x or y): return None
    length=math.hypot(x,y);side=min(width,height)
    return width/2+x/length*side*.41, height/2+y/length*side*.41, side*.16


def rim_highlight(active,width,height,color,strength):
    image=QImage(width,height,QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    anchor=ambient_position(active,width,height)
    if anchor is None:return image
    center=QPointF(width/2,height/2);radius=min(width,height)*.48
    angle=math.degrees(math.atan2(center.y()-anchor[1],anchor[0]-center.x()))
    radial=QRadialGradient(center,radius)
    for stop,alpha in ((0.,0),(.58,0),(.70,65),(.84,190),(.94,165),(1.,0)):
        tint=QColor(color);tint.setAlpha(round(alpha*strength));radial.setColorAt(stop,tint)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(image.rect(),radial)
    # Angular feathering gives a region of the circumference, rather than a point light.
    angular=QConicalGradient(center,angle-180)
    for stop,alpha in ((0.,0),(.5-42/360,0),(.5-28/360,150),(.5,255),(.5+28/360,150),(.5+42/360,0),(1.,0)):
        angular.setColorAt(stop,QColor(255,255,255,alpha))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.fillRect(image.rect(),angular);painter.end()
    return image


class Compass(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAutoFillBackground(False);self.setStyleSheet('background:transparent;')
        self.resize(240, 240)
        self.color = QColor('#4080ff')
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
        size=max(140,min(420,int(size)));center=self.frameGeometry().center()
        self.resize(size,size);self.move(center.x()-size//2,center.y()-size//2);self.update()

    def hideEvent(self,event):
        if self._phase=='out':self.clear()
        else:
            self.animation.stop();self._opacity=1. if self.active else 0.;self._phase='hold' if self.active else 'off'
        super().hideEvent(event)

    def closeEvent(self,event):
        self.clear();super().closeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow=ambient_position(self.active,self.width(),self.height())
        if self.glow_enabled and glow and self._opacity>0:
            key=(tuple(sorted(self.active)),self.width(),self.height(),self.color.rgba(),self.strength)
            if key!=self._glow_cache_key:
                self._glow_image=rim_highlight(self.active,self.width(),self.height(),self.color,self.strength)
                self._glow_cache_key=key
            painter.save();painter.setOpacity(self._opacity)
            painter.drawImage(0,0,self._glow_image);painter.restore()
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
