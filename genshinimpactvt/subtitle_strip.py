"""Small event-driven subtitle view; no polling, capture or model work."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QHBoxLayout,QVBoxLayout,QLabel


class SubtitleStrip(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('subtitleStrip');self.setMinimumHeight(66);self.setMaximumHeight(118)
        self.setStyleSheet('''QFrame#subtitleStrip {background:#f7f8fa;border:1px solid #e5e7eb;border-radius:8px;}
            QLabel {background:transparent;border:0;}
            QLabel#captionText {font-size:16px;font-weight:500;color:#292d34;}
            QLabel#captionSource {font-size:11px;color:#6c7480;}''')
        layout=QVBoxLayout(self);layout.setContentsMargins(14,8,14,10);layout.setSpacing(4)
        row=QHBoxLayout();heading=QLabel('当前字幕');heading.setObjectName('captionSource');row.addWidget(heading)
        row.addStretch();self.source=QLabel('');self.source.setObjectName('captionSource');row.addWidget(self.source);layout.addLayout(row)
        self.text=QLabel();self.text.setObjectName('captionText');self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.text)
        self.enabled=False;self.current='';self.set_recognition_enabled(False)

    def set_recognition_enabled(self,enabled):
        self.enabled=bool(enabled)
        if not self.enabled or not self.current:self.set_caption('','')

    def set_caption(self,text,source):
        self.current=str(text or '').strip()[:500]
        self.source.setText({'platform':'B站 AI/CC','dom':'网页字幕','ocr':'画面 OCR'}.get(source,'') if self.current else '')
        self.text.setText(self.current or ('等待当前字幕…' if self.enabled else '开启字幕识别后，当前字幕会显示在这里'))
        self.text.setToolTip(self.current)
