from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QLocale, QTranslator
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QDockWidget,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QTreeWidget,
    QWidget,
)


from scenelens.core.locales import (
    SOURCE_LOCALE,
    normalize_locale,
    set_current_locale,
)


def resolve_requested_locale(requested: str, system_locale: str | None = None) -> str:
    if requested == "system":
        return normalize_locale(system_locale or QLocale.system().name())
    return normalize_locale(requested)


class CatalogTranslator(QTranslator):
    def __init__(self, manager: LocalizationManager) -> None:
        super().__init__(manager)
        self.manager = manager

    def translate(self, context, source_text, disambiguation=None, n=-1):
        del context, disambiguation, n
        translated = self.manager.translate_text(str(source_text or ""))
        return translated if translated != source_text else ""


class LocalizationManager(QObject):
    def __init__(self, app: QApplication, requested_locale: str = SOURCE_LOCALE) -> None:
        super().__init__(app)
        self.app = app
        self.requested_locale = requested_locale
        self.locale = SOURCE_LOCALE
        self._strings: dict[str, str] = {}
        self._patterns: list[tuple[re.Pattern[str], str]] = []
        self.catalog_status = "complete"
        self.translation_stage = "source"
        self.translated_count = 0
        self.reviewed_count = 0
        self.total_count = 0
        self._state: dict[int, dict[str, Any]] = {}
        self._translating = False
        self._translator = CatalogTranslator(self)
        self.app.installTranslator(self._translator)
        self.app.installEventFilter(self)
        self.set_locale(requested_locale)

    def set_locale(self, requested_locale: str) -> None:
        self.requested_locale = requested_locale
        self.locale = resolve_requested_locale(requested_locale)
        set_current_locale(self.locale)
        self._load_catalog()
        for widget in self.app.topLevelWidgets():
            self.translate_tree(widget)
            QCoreApplication.sendEvent(widget, QEvent(QEvent.Type.LanguageChange))

    def translate_text(self, source: str) -> str:
        if not source or self.locale == SOURCE_LOCALE:
            return source
        exact = self._strings.get(source)
        if exact:
            return exact
        for pattern, target in self._patterns:
            match = pattern.fullmatch(source)
            if not match:
                continue
            result = target
            for index, value in enumerate(match.groups()):
                result = result.replace("{" + str(index) + "}", value)
            return result
        return source

    def translate_tree(self, root: QObject) -> None:
        if self._translating:
            return
        self._translating = True
        try:
            self._translate_object(root)
            for child in root.findChildren(QObject):
                self._translate_object(child)
        finally:
            self._translating = False

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() in {QEvent.Type.Show, QEvent.Type.LayoutRequest}
            and isinstance(watched, QWidget)
            and watched.isWindow()
            and not self._translating
        ):
            self.translate_tree(watched)
        return super().eventFilter(watched, event)

    def _load_catalog(self) -> None:
        self._strings = {}
        self._patterns = []
        self.catalog_status = "complete"
        self.translation_stage = "source"
        self.translated_count = 0
        self.reviewed_count = 0
        self.total_count = 0
        if self.locale == SOURCE_LOCALE:
            return
        resource = files("scenelens.i18n").joinpath(f"{self.locale}.json")
        try:
            payload = json.loads(resource.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        self._strings = {
            str(key): str(value)
            for key, value in dict(payload.get("strings", {})).items()
            if str(value).strip()
        }
        self.catalog_status = str(payload.get("status", "preview"))
        self.translation_stage = str(
            payload.get("translation_stage", "reviewed_subset")
        )
        self.translated_count = int(payload.get("translated_count", 0))
        self.reviewed_count = int(payload.get("reviewed_count", 0))
        self.total_count = int(payload.get("total_count", len(self._strings)))
        for item in payload.get("patterns", []):
            source = str(item.get("source", ""))
            target = str(item.get("target", ""))
            if not source or not target:
                continue
            parts = re.split(r"(\{\d+\})", source)
            expression = ""
            groups = 0
            for part in parts:
                if re.fullmatch(r"\{\d+\}", part):
                    expression += "(.*?)"
                    groups += 1
                else:
                    expression += re.escape(part)
            if groups:
                self._patterns.append((re.compile(expression, re.DOTALL), target))

    def _source(self, obj: QObject, key: str, current: str) -> str:
        state = self._state.setdefault(id(obj), {})
        source_key = f"{key}:source"
        last_key = f"{key}:last"
        source = state.get(source_key)
        last = state.get(last_key)
        if source is None or current not in {source, last}:
            source = current
            state[source_key] = source
        return str(source)

    def _apply(self, obj: QObject, key: str, current: str, setter) -> None:
        source = self._source(obj, key, current)
        target = self.translate_text(source)
        if current != target:
            setter(target)
        self._state.setdefault(id(obj), {})[f"{key}:last"] = target

    def _translate_object(self, obj: QObject) -> None:
        if isinstance(obj, QWidget):
            self._apply(obj, "windowTitle", obj.windowTitle(), obj.setWindowTitle)
            self._apply(obj, "toolTip", obj.toolTip(), obj.setToolTip)
            self._apply(obj, "statusTip", obj.statusTip(), obj.setStatusTip)
        if isinstance(obj, QLabel):
            self._apply(obj, "text", obj.text(), obj.setText)
        if isinstance(obj, QAbstractButton):
            source = self._source(obj, "text", obj.text())
            target = self.translate_text(source).replace("&", "&&")
            if obj.text() != target:
                obj.setText(target)
            self._state.setdefault(id(obj), {})["text:last"] = target
        if isinstance(obj, QGroupBox):
            self._apply(obj, "title", obj.title(), obj.setTitle)
        if isinstance(obj, QDockWidget):
            self._apply(obj, "dockTitle", obj.windowTitle(), obj.setWindowTitle)
        if isinstance(obj, QMenu):
            self._apply(obj, "menuTitle", obj.title(), obj.setTitle)
        if isinstance(obj, QAction):
            self._apply(obj, "actionText", obj.text(), obj.setText)
            self._apply(obj, "actionTip", obj.toolTip(), obj.setToolTip)
            self._apply(obj, "actionStatus", obj.statusTip(), obj.setStatusTip)
        if isinstance(obj, (QLineEdit, QTextEdit, QPlainTextEdit)):
            self._apply(
                obj,
                "placeholder",
                obj.placeholderText(),
                obj.setPlaceholderText,
            )
        if isinstance(obj, QTabWidget):
            self._translate_tabs(obj)
        if isinstance(obj, QComboBox) and not obj.property("gatalkSkipItemTranslation"):
            self._translate_combo(obj)
        if isinstance(obj, QTableWidget):
            self._translate_table_headers(obj)
        if isinstance(obj, QTreeWidget):
            self._translate_tree_headers(obj)

    def _translate_tabs(self, tabs: QTabWidget) -> None:
        state = self._state.setdefault(id(tabs), {})
        source = state.get("tabs:source")
        last = state.get("tabs:last")
        current = tuple(tabs.tabText(index) for index in range(tabs.count()))
        if source is None or (current != source and current != last):
            source = current
            state["tabs:source"] = source
        target = tuple(self.translate_text(value) for value in source)
        for index, value in enumerate(target):
            if tabs.tabText(index) != value:
                tabs.setTabText(index, value)
        state["tabs:last"] = target

    def _translate_combo(self, combo: QComboBox) -> None:
        state = self._state.setdefault(id(combo), {})
        source = state.get("combo:source")
        last = state.get("combo:last")
        current = tuple(combo.itemText(index) for index in range(combo.count()))
        if source is None or (current != source and current != last):
            source = current
            state["combo:source"] = source
        target = tuple(self.translate_text(value) for value in source)
        combo.blockSignals(True)
        try:
            for index, value in enumerate(target):
                if combo.itemText(index) != value:
                    combo.setItemText(index, value)
        finally:
            combo.blockSignals(False)
        state["combo:last"] = target

    def _translate_table_headers(self, table: QTableWidget) -> None:
        for index in range(table.columnCount()):
            item = table.horizontalHeaderItem(index)
            if item is not None:
                self._apply(
                    item,
                    f"tableHeader:{index}",
                    item.text(),
                    item.setText,
                )

    def _translate_tree_headers(self, tree: QTreeWidget) -> None:
        item = tree.headerItem()
        if item is None:
            return
        for index in range(tree.columnCount()):
            source = item.text(index)
            self._apply(
                item,
                f"treeHeader:{index}",
                source,
                lambda value, column=index: item.setText(column, value),
            )


def configure_localization(app: QApplication, requested_locale: str) -> LocalizationManager:
    manager = app.property("gatalkLocalizationManager")
    if isinstance(manager, LocalizationManager):
        manager.set_locale(requested_locale)
        return manager
    manager = LocalizationManager(app, requested_locale)
    app.setProperty("gatalkLocalizationManager", manager)
    return manager


def localization_manager(app: QApplication | None = None) -> LocalizationManager | None:
    target = app or QApplication.instance()
    if not isinstance(target, QApplication):
        return None
    manager = target.property("gatalkLocalizationManager")
    return manager if isinstance(manager, LocalizationManager) else None


def tr(source: str) -> str:
    manager = localization_manager()
    return manager.translate_text(source) if manager else source
