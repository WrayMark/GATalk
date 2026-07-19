from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scenelens.analysis.models import LuminanceComparison, SharedPaletteResult


class ComparisonPanel(QWidget):
    palette_selected = Signal(int)
    thresholds_changed = Signal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        contents = QWidget()
        self.content_layout = QVBoxLayout(contents)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        scroll.setWidget(contents)

        palette_box = QGroupBox("算法推断 · 共享 Oklab 色板")
        palette_layout = QVBoxLayout(palette_box)
        palette_note = QLabel(
            "双方等量采样后共同聚类。点击一行可在左右画布查看该聚类来源；"
            "再次点击或按 Esc 退出。"
        )
        palette_note.setWordWrap(True)
        palette_layout.addWidget(palette_note)
        self.palette_table = QTableWidget(0, 7)
        self.palette_table.setHorizontalHeaderLabels(
            ("颜色", "HEX", "Oklab", "参考", "当前", "差异", "来源")
        )
        self.palette_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.palette_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.palette_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.palette_table.verticalHeader().setVisible(False)
        palette_header = self.palette_table.horizontalHeader()
        palette_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        palette_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column, width in {
            0: 34,
            1: 64,
            3: 46,
            4: 46,
            5: 58,
            6: 66,
        }.items():
            self.palette_table.setColumnWidth(column, width)
        self.palette_table.cellClicked.connect(
            lambda row, _column: self.palette_selected.emit(row)
        )
        palette_layout.addWidget(self.palette_table)
        self.palette_sample_label = QLabel("等待参考图与当前截图")
        self.palette_sample_label.setStyleSheet("color: #9AA0A6;")
        palette_layout.addWidget(self.palette_sample_label)
        self.content_layout.addWidget(palette_box)

        luminance_box = QGroupBox("测量结果 · 三阶明度比例")
        luminance_layout = QVBoxLayout(luminance_box)
        threshold_form = QFormLayout()
        threshold_row = QWidget()
        threshold_row_layout = QHBoxLayout(threshold_row)
        threshold_row_layout.setContentsMargins(0, 0, 0, 0)
        self.low_threshold = QDoubleSpinBox()
        self.low_threshold.setRange(1.0, 98.0)
        self.low_threshold.setDecimals(1)
        self.low_threshold.setSuffix("%")
        self.low_threshold.setValue(100.0 / 3.0)
        self.high_threshold = QDoubleSpinBox()
        self.high_threshold.setRange(2.0, 99.0)
        self.high_threshold.setDecimals(1)
        self.high_threshold.setSuffix("%")
        self.high_threshold.setValue(200.0 / 3.0)
        threshold_row_layout.addWidget(QLabel("暗部 <"))
        threshold_row_layout.addWidget(self.low_threshold)
        threshold_row_layout.addWidget(QLabel("亮部 ≥"))
        threshold_row_layout.addWidget(self.high_threshold)
        threshold_form.addRow("阈值：", threshold_row)
        luminance_layout.addLayout(threshold_form)
        self.low_threshold.valueChanged.connect(self._emit_thresholds)
        self.high_threshold.valueChanged.connect(self._emit_thresholds)

        self.luminance_table = QTableWidget(3, 4)
        self.luminance_table.setHorizontalHeaderLabels(
            ("区间", "参考图", "当前截图", "差异")
        )
        self.luminance_table.verticalHeader().setVisible(False)
        self.luminance_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.luminance_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        luminance_layout.addWidget(self.luminance_table)

        thumbnails = QHBoxLayout()
        self.reference_thumbnail = self._thumbnail_label("参考图三阶缩略图")
        self.current_thumbnail = self._thumbnail_label("当前截图三阶缩略图")
        thumbnails.addWidget(self.reference_thumbnail)
        thumbnails.addWidget(self.current_thumbnail)
        luminance_layout.addLayout(thumbnails)
        note = QLabel("仅显示可测量差异，不自动生成好坏判断。")
        note.setStyleSheet("color: #9AA0A6;")
        note.setWordWrap(True)
        luminance_layout.addWidget(note)
        self.content_layout.addWidget(luminance_box)
        self.content_layout.addStretch(1)

    def set_region_panel(self, panel: QWidget) -> None:
        self.content_layout.insertWidget(
            max(0, self.content_layout.count() - 1),
            panel,
        )

    def clear(self) -> None:
        self.palette_table.setRowCount(0)
        self.palette_sample_label.setText("等待参考图与当前截图")
        self.luminance_table.clearContents()
        self.reference_thumbnail.setPixmap(QPixmap())
        self.reference_thumbnail.setText("参考图三阶缩略图")
        self.current_thumbnail.setPixmap(QPixmap())
        self.current_thumbnail.setText("当前截图三阶缩略图")

    def set_thresholds(self, low: float, high: float) -> None:
        self.low_threshold.blockSignals(True)
        self.high_threshold.blockSignals(True)
        try:
            self.low_threshold.setValue(float(low) * 100.0)
            self.high_threshold.setValue(float(high) * 100.0)
        finally:
            self.low_threshold.blockSignals(False)
            self.high_threshold.blockSignals(False)

    def thresholds(self) -> tuple[float, float]:
        return (
            self.low_threshold.value() / 100.0,
            self.high_threshold.value() / 100.0,
        )

    def set_shared_palette(self, result: SharedPaletteResult) -> None:
        self.palette_table.setRowCount(len(result.colours))
        for row, item in enumerate(result.colours):
            colour = QTableWidgetItem("")
            colour.setBackground(QColor(*item.rgb))
            colour.setToolTip(
                f"RGB {item.rgb[0]}, {item.rgb[1]}, {item.rgb[2]}"
            )
            self.palette_table.setItem(row, 0, colour)
            self.palette_table.setItem(row, 1, QTableWidgetItem(item.hex_colour))
            oklab_text = (
                f"{item.oklab[0]:.3f}, {item.oklab[1]:+.3f}, "
                f"{item.oklab[2]:+.3f}"
            )
            oklab_item = QTableWidgetItem(oklab_text)
            oklab_item.setToolTip(oklab_text)
            self.palette_table.setItem(
                row,
                2,
                oklab_item,
            )
            self.palette_table.setItem(
                row,
                3,
                QTableWidgetItem(f"{item.reference_proportion * 100:.1f}%"),
            )
            self.palette_table.setItem(
                row,
                4,
                QTableWidgetItem(f"{item.current_proportion * 100:.1f}%"),
            )
            self.palette_table.setItem(
                row,
                5,
                QTableWidgetItem(f"{item.proportion_difference * 100:+.1f} pp"),
            )
            self.palette_table.setItem(
                row,
                6,
                QTableWidgetItem("算法推断"),
            )
        self.palette_sample_label.setText(
            f"参考/当前各采样 {result.reference_sample_count:,} 像素；"
            "固定聚类中心用于来源遮罩。"
        )

    def set_luminance(
        self,
        result: LuminanceComparison,
        reference_thumbnail: QImage,
        current_thumbnail: QImage,
    ) -> None:
        labels = ("暗部", "中间调", "亮部")
        for row, label in enumerate(labels):
            reference = result.reference_ratios[row]
            current = result.current_ratios[row]
            values = (
                label,
                f"{reference * 100:.1f}%",
                f"{current * 100:.1f}%",
                f"{(current - reference) * 100:+.1f} pp",
            )
            for column, value in enumerate(values):
                self.luminance_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        self._set_thumbnail(self.reference_thumbnail, reference_thumbnail)
        self._set_thumbnail(self.current_thumbnail, current_thumbnail)

    def clear_palette_selection(self) -> None:
        self.palette_table.clearSelection()

    def _emit_thresholds(self) -> None:
        low, high = self.thresholds()
        if low >= high:
            return
        self.thresholds_changed.emit(low, high)

    @staticmethod
    def _thumbnail_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setMinimumSize(130, 90)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background: #15171A; color: #80868B;")
        return label

    @staticmethod
    def _set_thumbnail(label: QLabel, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image).scaled(
            150,
            90,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setText("")
        label.setPixmap(pixmap)
