from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QObject, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from scenelens.storage.app_settings import AppSettings, AppSettingsStore
from scenelens.ui.settings_dialog import GlobalSettingsDialog
from scenelens.ui.theme import apply_appearance


class GlobalSettingsController(QObject):
    settings_changed = Signal(object)

    def __init__(
        self,
        app: QApplication,
        store: AppSettingsStore | None = None,
    ) -> None:
        super().__init__(app)
        self.app = app
        self.store = store or AppSettingsStore()
        self.settings = self.store.load()
        self._window_keys: dict[QMainWindow, str] = {}
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

    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        apply_appearance(self.app, self.settings)
        try:
            self.store.save(self.settings)
        except OSError:
            QMessageBox.warning(
                self.app.activeWindow(),
                "GATalk 设置",
                "设置已经应用，但无法保存到本机。"
                "下次启动时可能恢复默认设置。",
            )
        self.settings_changed.emit(self.settings)

    def clear_window_layouts(self) -> None:
        self.settings = self.settings.without_window_layouts()
        try:
            self.store.save(self.settings)
        except OSError:
            return
        self.settings_changed.emit(self.settings)

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.Close
            and watched in self._window_keys
            and self.settings.remember_window_layout
        ):
            self._save_window(
                watched,
                self._window_keys[watched],
            )
        return super().eventFilter(watched, event)

    def _save_window(self, window: QMainWindow, key: str) -> None:
        geometry = bytes(window.saveGeometry().toBase64()).decode("ascii")
        state = bytes(window.saveState().toBase64()).decode("ascii")
        self.settings = self.settings.with_window_layout(
            key,
            geometry=geometry,
            state=state,
        )
        try:
            self.store.save(self.settings)
        except OSError:
            pass

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
