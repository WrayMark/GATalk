from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scenelens.modules.visual_review.presets import PresetCatalog


@dataclass(frozen=True)
class RegionListRow:
    row_id: str
    row_kind: str
    number: int | None
    colour: str
    name: str
    semantic_type: str
    reference_status: str
    current_status: str
    analysis_status: str
    reference_region_id: str | None = None
    current_region_id: str | None = None


class RegionMetadataDialog(QDialog):
    def __init__(
        self,
        title: str,
        presets: PresetCatalog,
        *,
        name: str = "",
        semantic_type: str = "自定义",
        notes: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(390)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(name)
        form.addRow("名称：", self.name_edit)
        self.semantic_combo = QComboBox()
        self.semantic_combo.setEditable(True)
        for option in presets.field("region_label").options:
            self.semantic_combo.addItem(option.label, option.id)
        index = self.semantic_combo.findText(semantic_type)
        if index >= 0:
            self.semantic_combo.setCurrentIndex(index)
        else:
            self.semantic_combo.setEditText(semantic_type)
        form.addRow("语义：", self.semantic_combo)
        self.notes_edit: QLineEdit | None = None
        if notes is not None:
            self.notes_edit = QLineEdit(notes)
            form.addRow("备注：", self.notes_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str]:
        return (
            self.name_edit.text().strip(),
            self.semantic_combo.currentText().strip(),
            "" if self.notes_edit is None else self.notes_edit.text().strip(),
        )

    def _accept_if_valid(self) -> None:
        name, semantic, _notes = self.values()
        if not name:
            self.name_edit.setFocus()
            return
        if not semantic:
            self.semantic_combo.setFocus()
            return
        self.accept()


class RegionPairPanel(QGroupBox):
    mode_toggled = Signal(bool)
    overlays_toggled = Signal(bool)
    pair_requested = Signal()
    copy_previous_requested = Signal()
    selected = Signal(str, str)
    edit_requested = Signal(str, str)
    delete_requested = Signal(str, str)
    reanalyze_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("成对区域")
        layout = QVBoxLayout(self)
        self.hint_label = QLabel(
            "进入区域模式后，分别在参考图和当前截图拖出矩形，再建立配对。"
        )
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #9AA0A6;")
        layout.addWidget(self.hint_label)

        tools = QHBoxLayout()
        self.mode_button = QPushButton("进入区域模式")
        self.mode_button.setCheckable(True)
        self.mode_button.toggled.connect(self._mode_changed)
        tools.addWidget(self.mode_button)
        self.pair_button = QPushButton("建立配对")
        self.pair_button.clicked.connect(self.pair_requested)
        tools.addWidget(self.pair_button)
        self.copy_button = QPushButton("复制上一版本")
        self.copy_button.clicked.connect(self.copy_previous_requested)
        tools.addWidget(self.copy_button)
        layout.addLayout(tools)

        options = QHBoxLayout()
        self.show_overlays = QCheckBox("显示区域叠层")
        self.show_overlays.setChecked(True)
        self.show_overlays.toggled.connect(self.overlays_toggled)
        options.addWidget(self.show_overlays)
        options.addStretch(1)
        layout.addLayout(options)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ("编号", "名称", "语义", "参考", "当前", "分析")
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(155)
        self.table.cellClicked.connect(self._row_selected)
        self.table.cellDoubleClicked.connect(self._row_edit)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        actions = QHBoxLayout()
        self.edit_button = QPushButton("编辑")
        self.edit_button.clicked.connect(self._edit_current)
        actions.addWidget(self.edit_button)
        self.delete_button = QPushButton("删除")
        self.delete_button.clicked.connect(self._delete_current)
        actions.addWidget(self.delete_button)
        self.reanalyze_button = QPushButton("重新分析")
        self.reanalyze_button.clicked.connect(self._reanalyze_current)
        actions.addWidget(self.reanalyze_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.selection_label = QLabel("尚未选择区域。")
        self.selection_label.setWordWrap(True)
        self.selection_label.setStyleSheet("color: #9AA0A6;")
        layout.addWidget(self.selection_label)
        self._rows: list[RegionListRow] = []
        self.set_editable(False)

    def set_rows(
        self,
        rows: tuple[RegionListRow, ...],
        selected_id: str | None = None,
    ) -> None:
        self._rows = list(rows)
        self.table.setRowCount(len(rows))
        selected_row = -1
        for row_index, row in enumerate(rows):
            number = "—" if row.number is None else str(row.number)
            number_item = QTableWidgetItem(number)
            number_item.setForeground(Qt.GlobalColor.white)
            number_item.setBackground(QColor(row.colour))
            values = (
                number_item,
                QTableWidgetItem(row.name),
                QTableWidgetItem(row.semantic_type),
                QTableWidgetItem(row.reference_status),
                QTableWidgetItem(row.current_status),
                QTableWidgetItem(row.analysis_status),
            )
            for column, item in enumerate(values):
                item.setData(Qt.ItemDataRole.UserRole, (row.row_kind, row.row_id))
                self.table.setItem(row_index, column, item)
            if row.row_id == selected_id:
                selected_row = row_index
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        self.table.resizeColumnsToContents()

    def set_editable(self, editable: bool) -> None:
        for widget in (
            self.mode_button,
            self.pair_button,
            self.copy_button,
            self.edit_button,
            self.delete_button,
        ):
            widget.setEnabled(editable)
        self.reanalyze_button.setEnabled(editable)

    def set_selection_text(self, text: str) -> None:
        self.selection_label.setText(text)

    def leave_region_mode(self) -> None:
        self.mode_button.setChecked(False)

    def current_row(self) -> RegionListRow | None:
        index = self.table.currentRow()
        if not 0 <= index < len(self._rows):
            return None
        return self._rows[index]

    def _mode_changed(self, active: bool) -> None:
        self.mode_button.setText(
            "退出区域模式（Esc）" if active else "进入区域模式"
        )
        self.hint_label.setText(
            (
                "区域模式：十字光标用于创建；选中区域后可移动或拖动手柄调整。"
                if active
                else "查看模式：画布恢复缩放和平移。"
            )
        )
        self.mode_toggled.emit(active)

    def _row_selected(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._rows):
            item = self._rows[row]
            self.selected.emit(item.row_kind, item.row_id)

    def _row_edit(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._rows):
            item = self._rows[row]
            self.edit_requested.emit(item.row_kind, item.row_id)

    def _edit_current(self) -> None:
        row = self.current_row()
        if row is not None:
            self.edit_requested.emit(row.row_kind, row.row_id)

    def _delete_current(self) -> None:
        row = self.current_row()
        if row is not None:
            self.delete_requested.emit(row.row_kind, row.row_id)

    def _reanalyze_current(self) -> None:
        row = self.current_row()
        if row is not None and row.row_kind == "pair":
            self.reanalyze_requested.emit(row.row_id)
