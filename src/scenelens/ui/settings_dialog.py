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
from scenelens.core.locales import (
    NATIVE_PREVIEW_LABELS,
    SUPPORTED_LANGUAGES,
    SYSTEM_LANGUAGE_LABELS,
    current_locale,
)
from scenelens.ui.localization import (
    localization_manager,
    resolve_requested_locale,
    tr,
)


class GlobalSettingsDialog(QDialog):
    settings_applied = Signal(object)
    clear_layouts_requested = Signal()

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self._base_settings = settings
        self.setWindowTitle("GATalk — 全局设置")
        self.setModal(True)
        self.resize(680, 650)
        self.setMinimumSize(620, 590)

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
        self.language_combo = QComboBox()
        self.language_combo.setProperty("gatalkSkipItemTranslation", True)
        self.language_combo.addItem(
            SYSTEM_LANGUAGE_LABELS.get(
                current_locale(),
                SYSTEM_LANGUAGE_LABELS["zh-CN"],
            ),
            "system",
        )
        for language in SUPPORTED_LANGUAGES:
            suffix = (
                ""
                if language.release_stage == "source"
                else f" · {NATIVE_PREVIEW_LABELS[language.locale]}"
            )
            self.language_combo.addItem(
                language.native_name + suffix,
                language.locale,
            )
        form.addRow("界面语言", self.language_combo)
        language_note = QLabel("保存后立即应用，并在以后启动时保持。")
        language_note.setProperty("role", "muted")
        language_note.setWordWrap(True)
        form.addRow("", language_note)
        self.language_quality_note = QLabel()
        self.language_quality_note.setProperty("tone", "warning")
        self.language_quality_note.setWordWrap(True)
        self.language_quality_note.setMinimumHeight(72)
        form.addRow("翻译状态", self.language_quality_note)
        self.language_combo.currentIndexChanged.connect(
            self._update_language_quality
        )
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
        for combo in (
            self.language_combo,
            self.theme_combo,
            self.accent_combo,
            self.font_combo,
            self.density_combo,
        ):
            combo.setMinimumHeight(34)
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
        self._update_language_quality()

    def current_settings(self) -> AppSettings:
        return replace(
            self._base_settings,
            ui_language=str(self.language_combo.currentData()),
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
            (self.language_combo, settings.ui_language),
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

    def _update_language_quality(self) -> None:
        locale = str(self.language_combo.currentData() or "system")
        resolved_locale = resolve_requested_locale(locale)
        if resolved_locale == "zh-CN":
            self.language_quality_note.setText("简体中文为完整基准语言。")
            return
        manager = localization_manager()
        stage = "preview"
        reviewed = 0
        if manager is not None and manager.locale == resolved_locale:
            translated = manager.translated_count
            total = manager.total_count
            reviewed = manager.reviewed_count
            stage = manager.translation_stage
        else:
            translated = 0
            total = 0
            try:
                from importlib.resources import files
                import json
                payload = json.loads(
                    files("scenelens.i18n")
                    .joinpath(f"{resolved_locale}.json")
                    .read_text(encoding="utf-8")
                )
                translated = int(payload.get("translated_count", 0))
                total = int(payload.get("total_count", 0))
                reviewed = int(payload.get("reviewed_count", 0))
                stage = str(payload.get("translation_stage", "preview"))
            except (FileNotFoundError, OSError, ValueError, TypeError):
                pass
        if stage == "machine_draft":
            self.language_quality_note.setText(
                f"{tr('预览语言包')}：{translated}/{total or '—'}；"
                f"{tr('已校核核心术语')} {reviewed}。"
                f"{tr('翻译初稿，正式发布前需母语审校。')}"
            )
        else:
            self.language_quality_note.setText(
                f"{tr('预览语言包')}：{translated}/{total or '—'}；"
                f"{tr('未覆盖内容回退为简体中文。')}"
            )
