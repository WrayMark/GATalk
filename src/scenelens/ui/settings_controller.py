from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QObject, QTimer, Signal, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolBar,
)

from scenelens.storage.app_settings import AppSettings, AppSettingsStore
from scenelens.ui.settings_dialog import GlobalSettingsDialog
from scenelens.ui.theme import apply_appearance
from scenelens.ui.command_palette import CommandEntry, CommandPaletteDialog
from scenelens.ui.localization import configure_localization


class GlobalSettingsController(QObject):
    settings_changed = Signal(object)
    task_center_requested = Signal(object)
    diagnostics_requested = Signal(object)
    global_search_requested = Signal(object)

    def __init__(
        self,
        app: QApplication,
        store: AppSettingsStore | None = None,
    ) -> None:
        super().__init__(app)
        self.app = app
        self.store = store or AppSettingsStore()
        self.settings = self.store.load()
        self.localization = configure_localization(
            self.app, self.settings.ui_language
        )
        self._window_keys: dict[QMainWindow, str] = {}
        self.last_persistence_error = ""
        apply_appearance(self.app, self.settings)
        self.app.styleHints().colorSchemeChanged.connect(
            self._system_theme_changed
        )

    def register_window(self, window: QMainWindow, key: str) -> None:
        if window in self._window_keys:
            return
        self._window_keys[window] = key
        window.installEventFilter(self)
        settings_menu = window.menuBar().addMenu("设置")
        action = QAction("全局设置…", window)
        action.setObjectName("globalSettingsAction")
        action.setShortcut(QKeySequence("Ctrl+,"))
        action.triggered.connect(
            lambda _checked=False, value=window: self.open_dialog(value)
        )
        settings_menu.addAction(action)
        tools_menu = window.menuBar().addMenu("工具")
        palette_action = QAction("命令面板…", window)
        palette_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        palette_action.triggered.connect(
            lambda _checked=False, value=window: self.open_command_palette(value)
        )
        tools_menu.addAction(palette_action)
        task_action = QAction("任务与供应商状态…", window)
        task_action.setShortcut(QKeySequence("Ctrl+Shift+J"))
        task_action.triggered.connect(
            lambda _checked=False, value=window: self.task_center_requested.emit(value)
        )
        tools_menu.addAction(task_action)
        diagnostics_action = QAction("项目诊断与恢复检查…", window)
        diagnostics_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        diagnostics_action.triggered.connect(
            lambda _checked=False, value=window: self.diagnostics_requested.emit(value)
        )
        tools_menu.addAction(diagnostics_action)
        help_menu = window.menuBar().addMenu("帮助")
        shortcuts_action = QAction("快捷键", window)
        shortcuts_action.setShortcut(QKeySequence("F1"))
        shortcuts_action.triggered.connect(
            lambda _checked=False, value=window: self.show_shortcuts(value)
        )
        help_menu.addAction(shortcuts_action)
        self._install_workspace_navigation(window)
        if self.settings.remember_window_layout:
            QTimer.singleShot(
                0,
                lambda value=window, layout_key=key: (
                    self._restore_window(value, layout_key)
                ),
            )

    def open_dialog(self, parent: QMainWindow | None = None) -> None:
        dialog = GlobalSettingsDialog(self.settings, parent)
        dialog.settings_applied.connect(self.apply_settings)
        dialog.clear_layouts_requested.connect(self.clear_window_layouts)
        dialog.exec()

    def open_command_palette(self, parent: QMainWindow) -> None:
        entries = [
                CommandEntry(
                    "全局检索",
                    "Ctrl+K",
                    lambda: self.global_search_requested.emit(parent),
                ),
                CommandEntry(
                    "打开全局设置",
                    "Ctrl+,",
                    lambda: self.open_dialog(parent),
                ),
                CommandEntry(
                    "打开任务与供应商状态",
                    "Ctrl+Shift+J",
                    lambda: self.task_center_requested.emit(parent),
                ),
                CommandEntry(
                    "打开项目诊断与恢复检查",
                    "Ctrl+Shift+D",
                    lambda: self.diagnostics_requested.emit(parent),
                ),
                CommandEntry(
                    "查看全局快捷键",
                    "F1",
                    lambda: self.show_shortcuts(parent),
                ),
            ]
        home_signal = getattr(parent, "workspace_home_requested", None)
        if home_signal is not None:
            entries.insert(
                0,
                CommandEntry(
                    "返回工作台首页",
                    "Ctrl+Shift+H",
                    home_signal.emit,
                ),
            )
        CommandPaletteDialog(
            tuple(entries),
            parent,
        ).exec()

    def _install_workspace_navigation(self, window: QMainWindow) -> None:
        home_signal = getattr(window, "workspace_home_requested", None)
        if home_signal is None:
            return
        toolbar = QToolBar("全局导航", window)
        toolbar.setObjectName("gatalkGlobalNavigation")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        home = QPushButton("←  工作台首页")
        home.setObjectName("workspaceHomeButton")
        home.setProperty("primary", True)
        home.setMinimumSize(152, 38)
        home.setToolTip("返回工作台首页（Ctrl+Shift+H）")
        home.clicked.connect(lambda _checked=False: home_signal.emit())
        toolbar.addWidget(home)
        toolbar.addSeparator()
        search = toolbar.addAction("全局检索")
        search.setToolTip("搜索项目、资料、任务和研究（Ctrl+K）")
        search.triggered.connect(
            lambda _checked=False: self.global_search_requested.emit(window)
        )
        task = toolbar.addAction("任务中心")
        task.triggered.connect(
            lambda _checked=False: self.task_center_requested.emit(window)
        )
        settings = toolbar.addAction("全局设置")
        settings.triggered.connect(
            lambda _checked=False: self.open_dialog(window)
        )
        existing = [
            value
            for value in window.findChildren(QToolBar)
            if value is not toolbar
        ]
        if existing:
            window.insertToolBar(existing[0], toolbar)
            window.insertToolBarBreak(existing[0])
        else:
            window.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

    def show_shortcuts(self, parent: QMainWindow) -> None:
        QMessageBox.information(
            parent,
            "GATalk 全局快捷键",
            "Ctrl+K  全局检索\n"
            "Ctrl+Shift+P  命令面板\n"
            "Ctrl+,  全局设置\n"
            "Ctrl+Shift+J  任务与供应商状态\n"
            "Ctrl+Shift+D  项目诊断\n"
            "Ctrl+Shift+H  返回工作台首页\n"
            "Ctrl+N / Ctrl+O / Ctrl+S  新建 / 打开 / 保存\n"
            "Ctrl+Z / Ctrl+Shift+Z  撤销 / 重做（支持的编辑界面）\n"
            "Shift 或 Ctrl  多选列表项\n"
            "F1  快捷键说明",
        )

    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.store.save(self.settings)
        self.localization.set_locale(self.settings.ui_language)
        apply_appearance(self.app, self.settings)
        self.settings_changed.emit(self.settings)

    def clear_window_layouts(self) -> None:
        self.settings = self.settings.without_window_layouts()
        self.store.save(self.settings)
        self.settings_changed.emit(self.settings)

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.Close
            and watched in self._window_keys
            and self.settings.remember_window_layout
        ):
            try:
                self._save_window(
                    watched,
                    self._window_keys[watched],
                )
                self.last_persistence_error = ""
            except OSError as exc:
                # A locked-down or roaming Windows profile must not trap the
                # application in a close-event loop. The layout remains only
                # in memory and can be retried next session.
                self.last_persistence_error = str(exc)
        return super().eventFilter(watched, event)

    def _save_window(self, window: QMainWindow, key: str) -> None:
        geometry = bytes(window.saveGeometry().toBase64()).decode("ascii")
        state = bytes(window.saveState().toBase64()).decode("ascii")
        self.settings = self.settings.with_window_layout(
            key,
            geometry=geometry,
            state=state,
        )
        self.store.save(self.settings)

    def _restore_window(self, window: QMainWindow, key: str) -> None:
        layout = self.settings.window_layouts.get(key)
        if not layout:
            return
        geometry = str(layout.get("geometry", ""))
        state = str(layout.get("state", ""))
        if geometry:
            window.restoreGeometry(
                QByteArray.fromBase64(geometry.encode("ascii"))
            )
        if state:
            window.restoreState(
                QByteArray.fromBase64(state.encode("ascii"))
            )

    def _system_theme_changed(self, _scheme) -> None:
        if self.settings.theme_mode == "system":
            apply_appearance(self.app, self.settings)
            self.settings_changed.emit(self.settings)
