from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


@dataclass(frozen=True)
class CommandEntry:
    title: str
    shortcut: str
    callback: Callable[[], None]


class CommandPaletteDialog(QDialog):
    def __init__(self, commands: tuple[CommandEntry, ...], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("命令面板")
        self.setMinimumWidth(560)
        self._commands = commands
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("输入命令名称…")
        self.search.textChanged.connect(self._refresh)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemActivated.connect(self._activate)
        layout.addWidget(self.list)
        self._refresh()
        self.search.setFocus()

    def _refresh(self) -> None:
        query = self.search.text().strip().casefold()
        self.list.clear()
        for index, command in enumerate(self._commands):
            if query and query not in command.title.casefold():
                continue
            row = QListWidgetItem(
                f"{command.title}    {command.shortcut}".rstrip()
            )
            row.setData(32, index)
            self.list.addItem(row)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _activate(self, row: QListWidgetItem) -> None:
        index = int(row.data(32))
        self.accept()
        self._commands[index].callback()

