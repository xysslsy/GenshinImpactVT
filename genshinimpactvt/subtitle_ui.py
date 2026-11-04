"""Subtitle controls and an image-based region picker (no desktop capture)."""
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QComboBox, QPushButton, QDialog, QDialogButtonBox)
from .subtitle_text import DEFAULT_REGION, valid_region


class RegionCanvas(QWidget):
    changed = Signal()

    def __init__(self, image, region):
        super().__init__()
        self.image = image; self.region = valid_region(region); self.anchor = None
        self.setMinimumSize(480, 270)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def image_rect(self):
        scale = min(self.width()/self.image.width(), self.height()/self.image.height())
        w, h = self.image.width()*scale, self.image.height()*scale
        return QRectF((self.width()-w)/2, (self.height()-h)/2, w, h)

    def paintEvent(self, event):
        p = QPainter(self); bounds = self.image_rect()
        p.fillRect(self.rect(), QColor('#202020'))
        p.drawImage(bounds, self.image)
        x,y,w,h = self.region
        selected = QRectF(bounds.x()+x*bounds.width(), bounds.y()+y*bounds.height(), w*bounds.width(), h*bounds.height())
        p.setPen(QPen(QColor('#4080ff'), 3)); p.setBrush(QColor(64,128,255,35)); p.drawRect(selected)

    def normalized(self, point):
        r = self.image_rect()
        return QPointF(max(0., min(1., (point.x()-r.x())/r.width())),
                       max(0., min(1., (point.y()-r.y())/r.height())))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.anchor = self.normalized(event.position())

    def mouseMoveEvent(self, event):
        if self.anchor is None:
            return
        end = self.normalized(event.position()); start = self.anchor
        self.region = (min(start.x(),end.x()), min(start.y(),end.y()),
                       abs(end.x()-start.x()), abs(end.y()-start.y()))
        self.update()

    def mouseReleaseEvent(self, event):
        if self.anchor is not None:
            self.mouseMoveEvent(event); self.anchor = None
            self.region = valid_region(self.region); self.update(); self.changed.emit()


class RegionDialog(QDialog):
    def __init__(self, image, region, parent):
        super().__init__(parent)
        self.setWindowTitle('框选视频字幕区域'); self.resize(900, 600)
        box = QVBoxLayout(self)
        note = QLabel('在这张视频快照上拖出字幕所在的矩形。只框字幕，避开弹幕和播放器按钮。')
        note.setWordWrap(True); box.addWidget(note)
        self.canvas = RegionCanvas(image, region); box.addWidget(self.canvas, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('保存区域')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); box.addWidget(buttons)


class SubtitlePage(QWidget):
    def __init__(self, enabled, mode, interval, ocr_available=True):
        super().__init__()
        box = QVBoxLayout(self); box.setContentsMargins(32,24,32,24); box.setSpacing(12)
        title = QLabel('字幕识别'); title.setObjectName('heading'); box.addWidget(title)
        note = QLabel('优先读取 B站已提供的 AI/CC 字幕，按视频时间提醒方向。轻量模式不录音、不运行本地模型。')
        note.setWordWrap(True); box.addWidget(note)
        self.enabled = QCheckBox('启用字幕识别与方向提醒'); self.enabled.setChecked(enabled); box.addWidget(self.enabled)
        self.show_footer=QCheckBox('在视频内显示透明字幕');self.show_footer.setChecked(True);box.addWidget(self.show_footer)
        self.mode = QComboBox()
        modes = [('轻量：B站平台字幕 + 网页字幕', 'auto'), ('仅使用网页当前显示的字幕', 'dom')]
        if ocr_available: modes.append(('高级：手动开启画面字幕 OCR', 'ocr'))
        for title, value in modes:
            self.mode.addItem(title, value)
        self.mode.setCurrentIndex(max(0, self.mode.findData(mode))); box.addWidget(self.mode)
        row = QHBoxLayout()
        self.pick = QPushButton('框选字幕区域'); self.reset = QPushButton('恢复默认区域'); self.show_compass = QPushButton('显示方向浮窗')
        row.addWidget(self.pick); row.addWidget(self.reset); row.addWidget(self.show_compass); box.addLayout(row)
        self.refresh = QPushButton('刷新字幕（登录后点击）'); box.addWidget(self.refresh)
        player_row=QHBoxLayout()
        self.player=QPushButton('打开官方纯播放器');self.full_page=QPushButton('返回完整 B站网页')
        player_row.addWidget(self.player);player_row.addWidget(self.full_page);box.addLayout(player_row)
        self.interval = QComboBox()
        for title,value in [('省电 · 每秒约 1 次', 1000), ('均衡 · 每秒约 2 次', 500), ('灵敏 · 每秒约 3 次', 350)]:
            self.interval.addItem(title, value)
        self.interval.setCurrentIndex(max(0, self.interval.findData(interval))); box.addWidget(self.interval)
        self.demo = QPushButton('打开本地识别示例'); box.addWidget(self.demo)
        self.status = QLabel('字幕识别已关闭'); self.status.setWordWrap(True); box.addWidget(self.status)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        label = QLabel('最近识别文字'); label.setObjectName('muted'); box.addWidget(label)
        self.text = QLabel('—'); self.text.setWordWrap(True); self.text.setMinimumHeight(45)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); box.addWidget(self.text)
        label = QLabel('最近一次字幕区域（仅用于画面 OCR）'); self.preview_title=label; label.setObjectName('muted'); box.addWidget(label)
        self.preview = QLabel('开启视频后可框选字幕区域'); self.preview.setMinimumHeight(80)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); box.addWidget(self.preview)
        hint = QLabel('请在软件内正常登录 B站，并在播放器的字幕选项里检查 AI/CC 字幕。平台未提供字幕时会提示，不会自动启用本地语音识别。')
        hint.setWordWrap(True); hint.setObjectName('muted'); box.addWidget(hint); box.addStretch()
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()

    def update_mode(self):
        ocr = self.mode.currentData() == 'ocr'
        for widget in (self.pick,self.reset,self.interval,self.demo,self.preview_title,self.preview):
            widget.setVisible(ocr)
        self.refresh.setVisible(self.mode.currentData() != 'ocr')

    def set_preview(self, image):
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(640, 120,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
