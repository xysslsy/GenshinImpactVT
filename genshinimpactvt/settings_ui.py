"""Shared layout for the native settings tabs."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QFormLayout, QFrame, QHBoxLayout, QLabel, QScrollArea, QSlider,
                               QTabWidget, QToolButton, QVBoxLayout, QWidget)


class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('settingsView')
        self.setStyleSheet('''
            #settingsView, #settingsSection { background: #f3f6f5; }
            QLabel#settingsTitle { background: transparent; color: #172a2b; font-size: 24px; font-weight: 700; }
            QTabWidget::pane { border: 0; background: #f3f6f5; }
            QTabBar::tab { color: #526565; background: #eef2f1; padding: 7px 10px; margin-right: 3px; border-radius: 6px; }
            QTabBar::tab:selected { color: #114d46; background: #dcece7; font-weight: 650; }
            QTabBar::tab:hover:!selected { background: #e4ebe9; }
            QFrame#settingsCard { background: #fff; border: 1px solid #dce5e2; border-radius: 9px; }
            QLabel#settingsCardTitle { background: transparent; color: #173a36; font-weight: 700; }
            QLabel#settingsNote { background: transparent; color: #526867; font-size: 12px; }
            QLabel#keyHint { color: #173a36; background: #eaf2ef; padding: 2px 8px; border-radius: 4px; }
            QToolButton#settingsDisclosure { background: #eaf0ee; color: #365450; border: 0; border-radius: 7px; padding: 7px; text-align: left; }
            QToolButton#settingsDisclosure:hover { background: #dfeae6; }
            QPushButton#settingsAction { color: #fff; background: #24675c; border-color: #24675c; }
            QPushButton#settingsAction:hover { background: #1a584e; }
            QCheckBox { background: transparent; }
            QComboBox, QSpinBox { border: 1px solid #cbd9d5; border-radius: 6px; padding: 4px 7px; background: #fff; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 17, 22, 13)
        layout.setSpacing(10)
        title = QLabel('设置')
        title.setObjectName('settingsTitle')
        layout.addWidget(title)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.tabBar().setExpanding(False)
        layout.addWidget(self.tabs, 1)
        self.sections = {}

    def add_section(self, key, title, content):
        content.setObjectName('settingsSection')
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.sections[key] = self.tabs.addTab(scroll, title)

    def show_section(self, key):
        self.tabs.setCurrentIndex(self.sections[key])


class SettingsSection(QWidget):
    def __init__(self):
        super().__init__()
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(0, 13, 6, 8)
        self.content.setSpacing(10)
        self.content.addStretch()

    def add(self, widget):
        self.content.insertWidget(self.content.count() - 1, widget)


def settings_form():
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(8)
    return form


class SettingsCard(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName('settingsCard')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 9, 13, 12)
        layout.setSpacing(8)
        if title:
            header = QLabel(title)
            header.setObjectName('settingsCardTitle')
            layout.addWidget(header)
        self.form = settings_form()
        layout.addLayout(self.form)


class SettingsDisclosure(QWidget):
    def __init__(self, title, content):
        super().__init__()
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setObjectName('settingsDisclosure')
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setIconSize(QSize(13, 13))
        self.content = content
        self.content.hide()
        self.toggle.toggled.connect(self.refresh_expansion)
        box.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        box.addWidget(content)

    def set_expanded(self, expanded):
        self.toggle.setChecked(expanded)

    def refresh_expansion(self, expanded):
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)


def setting_note(text):
    label = QLabel(text)
    label.setObjectName('settingsNote')
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def slider_field(slider, value):
    field = QWidget()
    field.setMaximumWidth(360)
    row = QHBoxLayout(field)
    row.setContentsMargins(0, 0, 0, 0)
    value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    value.setMinimumWidth(45)
    row.addWidget(slider, 1)
    row.addWidget(value)
    return field


def slider_spin_field(spinbox, label):
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setAccessibleName(f'{label}滑杆')
    spinbox.setAccessibleName(f'{label}数值')
    slider.setRange(spinbox.minimum(), spinbox.maximum())
    slider.setSingleStep(spinbox.singleStep())
    slider.setValue(spinbox.value())
    slider.valueChanged.connect(spinbox.setValue)
    spinbox.valueChanged.connect(slider.setValue)
    return slider_field(slider, spinbox)
