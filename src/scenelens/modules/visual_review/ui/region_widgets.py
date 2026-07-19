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

from scenelens.analysis.models import SharedPaletteResult
from scenelens.analysis.region_analysis import PairedRegionAnalysis
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
    region_palette_selected = Signal(int)

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

        self.details_box = QGroupBox("当前区域详细比较")
        self.details_box.setCheckable(True)
        self.details_box.setChecked(True)
        details_layout = QVBoxLayout(self.details_box)
        self.analysis_status_label = QLabel("选择完整区域对后开始分析。")
        self.analysis_status_label.setWordWrap(True)
        self.analysis_status_label.setStyleSheet("color: #9AA0A6;")
        details_layout.addWidget(self.analysis_status_label)
        self.metrics_table = QTableWidget(0, 5)
        self.metrics_table.setHorizontalHeaderLabels(
            ("指标", "参考", "当前", "差异", "类型")
        )
        self.metrics_table.verticalHeader().setVisible(False)
        self.metrics_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.metrics_table.setMinimumHeight(255)
        self.metrics_table.horizontalHeader().setStretchLastSection(True)
        details_layout.addWidget(self.metrics_table)
        self.hue_distribution_label = QLabel("色相分布：等待分析。")
        self.hue_distribution_label.setWordWrap(True)
        self.hue_distribution_label.setToolTip(
            "低于中性色阈值的像素不进入色相分布。"
        )
        details_layout.addWidget(self.hue_distribution_label)
        palette_label = QLabel("区域内共享色板组成")
        palette_label.setStyleSheet("font-weight: 600;")
        details_layout.addWidget(palette_label)
        self.region_palette_table = QTableWidget(0, 6)
        self.region_palette_table.setHorizontalHeaderLabels(
            ("颜色", "HEX", "参考", "当前", "差异", "类型")
        )
        self.region_palette_table.verticalHeader().setVisible(False)
        self.region_palette_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.region_palette_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.region_palette_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.region_palette_table.setMinimumHeight(150)
        self.region_palette_table.cellClicked.connect(
            lambda row, _column: self.region_palette_selected.emit(row)
        )
        details_layout.addWidget(self.region_palette_table)
        self.analysis_note = QLabel(
            "明度统计为测量结果；Oklab、色相与共享色板归类为算法推断。"
            "仅呈现差异，不生成好坏结论。"
        )
        self.analysis_note.setWordWrap(True)
        self.analysis_note.setStyleSheet("color: #9AA0A6;")
        details_layout.addWidget(self.analysis_note)
        self._detail_widgets = (
            self.analysis_status_label,
            self.metrics_table,
            self.hue_distribution_label,
            palette_label,
            self.region_palette_table,
            self.analysis_note,
        )
        self.details_box.toggled.connect(self._details_toggled)
        layout.addWidget(self.details_box)
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

    def clear_analysis(self, message: str = "选择完整区域对后开始分析。") -> None:
        self.analysis_status_label.setText(message)
        self.metrics_table.setRowCount(0)
        self.region_palette_table.setRowCount(0)
        self.hue_distribution_label.setText("色相分布：等待分析。")

    def set_analysis(
        self,
        result: PairedRegionAnalysis,
        shared_palette: SharedPaletteResult,
        *,
        stale: bool = False,
    ) -> None:
        reference = result.reference
        current = result.current
        status = "旧结果已过期，正在等待重新分析。" if stale else "分析已完成。"
        self.analysis_status_label.setText(
            f"{status} 参考 {reference.pixel_count:,} px；"
            f"当前 {current.pixel_count:,} px；"
            f"色彩采样 {reference.colour_sample_count:,} / "
            f"{current.colour_sample_count:,}。"
        )
        metrics = [
            (
                "平均线性明度",
                reference.mean_linear_luminance,
                current.mean_linear_luminance,
                "",
                "测量结果",
            ),
            (
                "Oklab L 均值",
                reference.mean_oklab_l,
                current.mean_oklab_l,
                "",
                "算法推断",
            ),
            (
                "Oklab a 均值",
                reference.mean_oklab[1],
                current.mean_oklab[1],
                "",
                "算法推断",
            ),
            (
                "Oklab b 均值",
                reference.mean_oklab[2],
                current.mean_oklab[2],
                "",
                "算法推断",
            ),
            (
                "明度标准差",
                reference.luminance_standard_deviation,
                current.luminance_standard_deviation,
                "",
                "测量结果",
            ),
            (
                "P10 明度",
                reference.luminance_p10,
                current.luminance_p10,
                "",
                "测量结果",
            ),
            (
                "P50 明度",
                reference.luminance_p50,
                current.luminance_p50,
                "",
                "测量结果",
            ),
            (
                "P90 明度",
                reference.luminance_p90,
                current.luminance_p90,
                "",
                "测量结果",
            ),
            (
                "P10–P90 跨度",
                reference.effective_luminance_span,
                current.effective_luminance_span,
                "",
                "测量结果",
            ),
            (
                "平均彩度",
                reference.mean_chroma,
                current.mean_chroma,
                "",
                "算法推断",
            ),
            (
                "彩度中位数",
                reference.median_chroma,
                current.median_chroma,
                "",
                "算法推断",
            ),
            (
                "中性色比例",
                reference.neutral_ratio,
                current.neutral_ratio,
                "%",
                "算法推断",
            ),
            (
                "色相圆形均值",
                reference.hue_mean_degrees,
                current.hue_mean_degrees,
                "°",
                "算法推断",
            ),
            (
                "暗部比例",
                reference.three_value_ratios[0],
                current.three_value_ratios[0],
                "%",
                "测量结果",
            ),
            (
                "中间调比例",
                reference.three_value_ratios[1],
                current.three_value_ratios[1],
                "%",
                "测量结果",
            ),
            (
                "亮部比例",
                reference.three_value_ratios[2],
                current.three_value_ratios[2],
                "%",
                "测量结果",
            ),
        ]
        self.metrics_table.setRowCount(len(metrics))
        for row, (name, ref_value, current_value, unit, source) in enumerate(
            metrics
        ):
            is_percent = unit == "%"
            scale = 100.0 if is_percent else 1.0
            suffix = "%" if is_percent else unit
            difference_suffix = " pp" if is_percent else ""
            reference_text = (
                "无有效色相"
                if ref_value is None
                else f"{ref_value * scale:.3f}{suffix}"
            )
            current_text = (
                "无有效色相"
                if current_value is None
                else f"{current_value * scale:.3f}{suffix}"
            )
            difference_text = (
                "—"
                if ref_value is None or current_value is None
                else (
                    f"{(current_value - ref_value) * scale:+.3f}"
                    f"{difference_suffix or suffix}"
                )
            )
            values = (
                name,
                reference_text,
                current_text,
                difference_text,
                source,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    "差异定义为当前截图减参考图。"
                    if column == 3
                    else value
                )
                self.metrics_table.setItem(row, column, item)
        self.metrics_table.resizeColumnsToContents()
        bin_width = 360.0 / result.hue_bins
        reference_hue = " / ".join(
            (
                f"{index * bin_width:.0f}°"
                f" {value * 100:.1f}%"
            )
            for index, value in enumerate(reference.hue_distribution)
        )
        current_hue = " / ".join(
            (
                f"{index * bin_width:.0f}°"
                f" {value * 100:.1f}%"
            )
            for index, value in enumerate(current.hue_distribution)
        )
        self.hue_distribution_label.setText(
            f"色相分布（{result.hue_bins} 区间）\n"
            f"参考：{reference_hue}\n当前：{current_hue}"
        )

        colour_count = min(
            len(shared_palette.colours),
            len(reference.shared_palette_proportions),
            len(current.shared_palette_proportions),
        )
        self.region_palette_table.setRowCount(colour_count)
        for row in range(colour_count):
            colour = shared_palette.colours[row]
            reference_ratio = reference.shared_palette_proportions[row]
            current_ratio = current.shared_palette_proportions[row]
            swatch = QTableWidgetItem("")
            swatch.setBackground(QColor(*colour.rgb))
            values = (
                swatch,
                QTableWidgetItem(colour.hex_colour),
                QTableWidgetItem(f"{reference_ratio * 100:.1f}%"),
                QTableWidgetItem(f"{current_ratio * 100:.1f}%"),
                QTableWidgetItem(
                    f"{(current_ratio - reference_ratio) * 100:+.1f} pp"
                ),
                QTableWidgetItem("算法推断"),
            )
            for column, item in enumerate(values):
                item.setToolTip(
                    (
                        "点击此行，只在当前成对区域内查看该颜色来源。"
                        if column == 0
                        else item.text()
                    )
                )
                self.region_palette_table.setItem(row, column, item)
        self.region_palette_table.resizeColumnsToContents()
        self.analysis_note.setText(
            "明度统计为测量结果；Oklab、色相与共享色板归类为算法推断。"
            f"低彩度阈值为 Oklab C < {result.neutral_chroma_threshold:.3f}。"
            "仅呈现差异，不生成好坏结论。"
        )

    def clear_region_palette_selection(self) -> None:
        self.region_palette_table.clearSelection()

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

    def _details_toggled(self, expanded: bool) -> None:
        for widget in self._detail_widgets:
            widget.setVisible(expanded)
