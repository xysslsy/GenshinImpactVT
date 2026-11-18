"""Subtitle controls and an image-based region picker (no desktop capture)."""
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QCheckBox,
    QComboBox, QPushButton, QDialog, QDialogButtonBox, QSpinBox)
from .desktop_subtitle import DesktopSubtitle
from .settings_ui import SettingsCard, SettingsDisclosure, SettingsSection, setting_note, settings_form, slider_spin_field
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


class SubtitlePage(SettingsSection):
    def __init__(self, enabled, mode, interval, ocr_available=True):
        super().__init__()
        regular = SettingsCard('字幕与方向')
        self.enabled = QCheckBox('启用字幕识别与方向提醒')
        self.enabled.setChecked(enabled)
        self.show_footer = QCheckBox('在视频内显示字幕')
        self.show_footer.setChecked(True)
        self.show_desktop = QCheckBox('在屏幕底部显示字幕')
        self.show_desktop.setToolTip('字幕独立于视频窗口显示，鼠标可穿过字幕。')
        self.desktop_font_size = QSpinBox()
        self.desktop_font_size.setRange(DesktopSubtitle.MIN_FONT_SIZE, DesktopSubtitle.MAX_FONT_SIZE)
        self.desktop_font_size.setValue(DesktopSubtitle.DEFAULT_FONT_SIZE)
        self.desktop_font_size.setSuffix(' px')
        self.desktop_size_field = slider_spin_field(self.desktop_font_size, '屏幕字幕大小')
        self.refresh = QPushButton('重新读取字幕')
        self.refresh.setToolTip('切回自动识别，保持当前视频和播放位置。')
        regular.form.addRow(self.enabled)
        regular.form.addRow(self.show_footer)
        regular.form.addRow(self.show_desktop)
        regular.form.addRow('屏幕字幕大小', self.desktop_size_field)
        regular.form.addRow(self.refresh)

        current = SettingsCard('当前识别')
        self.status = setting_note('正在等待视频…' if enabled else '字幕识别已关闭')
        self.text = QLabel('—')
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        current.form.addRow(self.status)
        current.form.addRow(self.text)

        advanced = SettingsCard('')
        self.auto_on_video = QCheckBox('启动和切视频时自动识别')
        self.auto_on_video.setChecked(True)
        self.auto_on_video.setToolTip('每轮最多尝试 3 次。关闭后保留手动选择的模式。')
        self.mode = QComboBox()
        modes = [('自动 · B站中文字幕', 'auto'), ('手动 · 网页字幕', 'dom')]
        if ocr_available:
            modes.append(('手动 · 画面 OCR', 'ocr'))
        for title, value in modes:
            self.mode.addItem(title, value)
        self.mode.setCurrentIndex(max(0, self.mode.findData(mode)))
        self.player = QPushButton('打开纯播放器')
        self.full_page = QPushButton('返回完整网页')
        advanced.form.addRow(self.auto_on_video)
        advanced.form.addRow('识别方式', self.mode)
        advanced.form.addRow('B站播放器', self.player)
        advanced.form.addRow('', self.full_page)

        self.ocr_options = QWidget()
        ocr_form = settings_form()
        self.ocr_options.setLayout(ocr_form)
        self.pick = QPushButton('框选字幕区域')
        self.reset = QPushButton('恢复默认区域')
        self.interval = QComboBox()
        for title, value in [('省电 · 每秒约 1 次', 1000), ('均衡 · 每秒约 2 次', 500), ('灵敏 · 每秒约 3 次', 350)]:
            self.interval.addItem(title, value)
        self.interval.setCurrentIndex(max(0, self.interval.findData(interval)))
        self.demo = QPushButton('打开识别示例')
        self.preview = setting_note('开启视频后可框选字幕区域。')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ocr_form.addRow('字幕区域', self.pick)
        ocr_form.addRow('', self.reset)
        ocr_form.addRow('识别频率', self.interval)
        ocr_form.addRow(self.demo)
        ocr_form.addRow(self.preview)
        advanced.form.addRow(self.ocr_options)
        self.advanced = SettingsDisclosure('高级设置 · 普通用户可忽略', advanced)
        self.add(regular)
        self.add(current)
        self.add(self.advanced)
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()

    def update_mode(self):
        self.ocr_options.setVisible(self.mode.currentData() == 'ocr')

    def set_preview(self, image):
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(640, 120,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
