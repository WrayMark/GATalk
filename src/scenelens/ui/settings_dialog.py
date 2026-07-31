from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from scenelens.storage.app_settings import AppSettings


class GlobalSettingsDialog(QDialog):
    settings_applied = Signal(object)
    clear_layouts_requested = Signal()

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self._base_settings = settings
        self.setWindowTitle("GATalk — 全局设置")
        self.setModal(True)
        self.resize(570, 530)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)
        heading = QLabel("全局设置")
        heading.setObjectName("heroTitle")
        layout.addWidget(heading)
        description = QLabel(
            "这些设置作用于首页和全部工作台，并保存在本机；"
            "不会写入项目或上传。"
        )
        description.setWordWrap(True)
        description.setProperty("role", "muted")
        layout.addWidget(description)

        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(12)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随 Windows", "system")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        form.addRow("主题", self.theme_combo)

        self.accent_combo = QComboBox()
        for label, value in (
            ("主美紫", "violet"),
            ("工作台蓝", "blue"),
            ("青绿色", "teal"),
            ("暖橙色", "orange"),
        ):
            self.accent_combo.addItem(label, value)
        form.addRow("强调色", self.accent_combo)

        self.font_combo = QComboBox()
        for label, value in (
            ("较小 · 9 pt", 9),
            ("标准 · 10 pt", 10),
            ("较大 · 11 pt", 11),
            ("大 · 12 pt", 12),
        ):
            self.font_combo.addItem(label, value)
        form.addRow("界面字号", self.font_combo)

        self.density_combo = QComboBox()
        self.density_combo.addItem("紧凑", "compact")
        self.density_combo.addItem("舒适", "comfortable")
        self.density_combo.addItem("宽松", "spacious")
        form.addRow("控件密度", self.density_combo)
        layout.addLayout(form)

        self.remember_layout_check = QCheckBox(
            "记住每个工作台的窗口大小、停靠面板和工具栏布局"
        )
        layout.addWidget(self.remember_layout_check)
        layout_row = QHBoxLayout()
        layout_note = QLabel("关闭后仍保留数据，但启动时不再恢复。")
        layout_note.setProperty("role", "muted")
        layout_row.addWidget(layout_note, 1)
        self.clear_layout_button = QPushButton("清除已保存布局")
        self.clear_layout_button.clicked.connect(self._clear_layouts)
        layout_row.addWidget(self.clear_layout_button)
        layout.addLayout(layout_row)

        preview = QFrame()
        preview.setObjectName("settingsPreviewCard")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(16, 14, 16, 14)
        preview_title = QLabel("界面预览")
        preview_title.setObjectName("cardTitle")
        preview_layout.addWidget(preview_title)
        preview_text = QLabel(
            "GATalk 使用中性色建立层级，只把强调色用于当前页签、"
            "主要按钮和交互反馈。"
        )
        preview_text.setWordWrap(True)
        preview_text.setProperty("role", "muted")
        preview_layout.addWidget(preview_text)
        preview_action = QPushButton("主要操作")
        preview_action.setProperty("primary", True)
        preview_action.setEnabled(False)
        preview_layout.addWidget(preview_action)
        layout.addWidget(preview)
        layout.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("确定")
        buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText("取消")
        buttons.button(
            QDialogButtonBox.StandardButton.Apply
        ).setText("应用")
        buttons.button(
            QDialogButtonBox.StandardButton.RestoreDefaults
        ).setText("恢复默认")
        buttons.accepted.connect(self._apply_and_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(
            QDialogButtonBox.StandardButton.Apply
        ).clicked.connect(self._emit_settings)
        buttons.button(
            QDialogButtonBox.StandardButton.RestoreDefaults
        ).clicked.connect(self._restore_defaults)
        layout.addWidget(buttons)
        self._load(settings)

    def current_settings(self) -> AppSettings:
        return replace(
            self._base_settings,
            theme_mode=str(self.theme_combo.currentData()),
            accent=str(self.accent_combo.currentData()),
            font_size=int(self.font_combo.currentData()),
            density=str(self.density_combo.currentData()),
            remember_window_layout=(
                self.remember_layout_check.isChecked()
            ),
        )

    def _load(self, settings: AppSettings) -> None:
        for combo, value in (
            (self.theme_combo, settings.theme_mode),
            (self.accent_combo, settings.accent),
            (self.font_combo, settings.font_size),
            (self.density_combo, settings.density),
        ):
            index = combo.findData(value)
            combo.setCurrentIndex(max(0, index))
        self.remember_layout_check.setChecked(
            settings.remember_window_layout
        )

    def _emit_settings(self) -> None:
        value = self.current_settings()
        self._base_settings = value
        self.settings_applied.emit(value)

    def _apply_and_accept(self) -> None:
        self._emit_settings()
        self.accept()

    def _restore_defaults(self) -> None:
        defaults = AppSettings(
            window_layouts=self._base_settings.window_layouts
        )
        self._load(defaults)

    def _clear_layouts(self) -> None:
        self._base_settings = self._base_settings.without_window_layouts()
        self.clear_layouts_requested.emit()
        self.clear_layout_button.setText("已清除保存的布局")
        self.clear_layout_button.setEnabled(False)
