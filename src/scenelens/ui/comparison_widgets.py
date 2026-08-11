from __future__ import annotations

from PySide6.QtCore import QRectF, Signal, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from scenelens.analysis.models import (
    DistributionComparison,
    LuminanceComparison,
    PaletteColour,
    SharedPaletteResult,
)


class ComparisonDistributionWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._reference: tuple[float, ...] = ()
        self._current: tuple[float, ...] = ()
        self._show_reference = True
        self._show_current = True
        self._left_label = "0"
        self._right_label = "1"
        self.setMinimumHeight(165)

    def set_result(self, result: DistributionComparison) -> None:
        self._reference = result.reference_values
        self._current = result.current_values
        self._left_label = _range_label(result.metric, result.range_min)
        self._right_label = _range_label(result.metric, result.range_max)
        self.update()

    def clear(self) -> None:
        self._reference = ()
        self._current = ()
        self.update()

    def set_series_visible(self, reference: bool, current: bool) -> None:
        self._show_reference = reference
        self._show_current = current
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colours = self.palette()
        plot = QRectF(self.rect()).adjusted(10.0, 10.0, -10.0, -24.0)
        painter.fillRect(plot, colours.color(QPalette.ColorRole.Base))
        painter.setPen(QPen(colours.color(QPalette.ColorRole.Mid), 1.0))
        painter.drawRect(plot)
        if not self._reference and not self._current:
            painter.setPen(colours.color(QPalette.ColorRole.PlaceholderText))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "等待双图分析")
            return
        peak = max((*self._reference, *self._current, 0.0))
        if peak > 0.0:
            if self._show_reference:
                self._draw_series(
                    painter, plot, self._reference, peak, QColor("#4EC9B0"), 0.20
                )
            if self._show_current:
                self._draw_series(
                    painter, plot, self._current, peak, QColor("#E7A34B"), 0.13
                )
        painter.setPen(colours.color(QPalette.ColorRole.PlaceholderText))
        labels = QRectF(plot.left(), plot.bottom() + 4.0, plot.width(), 16.0)
        painter.drawText(labels, Qt.AlignmentFlag.AlignLeft, self._left_label)
        painter.drawText(labels, Qt.AlignmentFlag.AlignRight, self._right_label)

    @staticmethod
    def _draw_series(
        painter: QPainter,
        plot: QRectF,
        values: tuple[float, ...],
        peak: float,
        colour: QColor,
        opacity: float,
    ) -> None:
        if not values:
            return
        path = QPainterPath()
        path.moveTo(plot.left(), plot.bottom())
        denominator = max(1, len(values) - 1)
        for index, value in enumerate(values):
            x = plot.left() + plot.width() * index / denominator
            y = plot.bottom() - plot.height() * value / peak
            path.lineTo(x, y)
        path.lineTo(plot.right(), plot.bottom())
        path.closeSubpath()
        fill = QColor(colour)
        fill.setAlphaF(opacity)
        painter.fillPath(path, fill)
        painter.setPen(QPen(colour, 2.0))
        painter.drawPath(path)


def _range_label(metric: str, value: float) -> str:
    if metric == "oklab_hue":
        return f"{value:.0f}°"
    return f"{value:.2f}"


class ComparisonPanel(QWidget):
    palette_selected = Signal(int)
    independent_palette_selected = Signal(str, int)
    thresholds_changed = Signal(float, float)
    distribution_parameters_changed = Signal()

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

        overview_box = QGroupBox("双图证据概览")
        overview_layout = QVBoxLayout(overview_box)
        overview_note = QLabel(
            "参考图与当前截图使用同一坐标尺度绘制。曲线只表达分布差异，"
            "不自动判断优劣。"
        )
        overview_note.setWordWrap(True)
        overview_layout.addWidget(overview_note)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("观察指标"))
        self.distribution_metric = QComboBox()
        self.distribution_metric.addItem("线性 sRGB 相对明度", "relative_luminance")
        self.distribution_metric.addItem("Oklab 明度 L", "oklab_lightness")
        self.distribution_metric.addItem("Oklab 彩度 C", "oklab_chroma")
        self.distribution_metric.addItem("Oklab 色相（排除低彩度）", "oklab_hue")
        self.distribution_metric.addItem("HSV 饱和度", "hsv_saturation")
        controls.addWidget(self.distribution_metric, 1)
        controls.addWidget(QLabel("精度"))
        self.distribution_bins = QComboBox()
        for count in (16, 32, 64, 128):
            self.distribution_bins.addItem(f"{count} 档", count)
        self.distribution_bins.setCurrentIndex(1)
        controls.addWidget(self.distribution_bins)
        overview_layout.addLayout(controls)
        legend = QHBoxLayout()
        self.show_reference_distribution = QCheckBox("参考图 · 青绿色")
        self.show_reference_distribution.setChecked(True)
        self.show_current_distribution = QCheckBox("当前截图 · 橙色")
        self.show_current_distribution.setChecked(True)
        legend.addWidget(self.show_reference_distribution)
        legend.addWidget(self.show_current_distribution)
        legend.addStretch(1)
        overview_layout.addLayout(legend)
        self.distribution_chart = ComparisonDistributionWidget()
        overview_layout.addWidget(self.distribution_chart)
        self.distribution_note = QLabel("低彩度过滤：Oklab C < 0.04；两图等规则统计。")
        self.distribution_note.setProperty("role", "muted")
        self.distribution_note.setWordWrap(True)
        overview_layout.addWidget(self.distribution_note)

        palette_heading = QLabel("独立色板并置")
        palette_heading.setStyleSheet("font-weight: 600;")
        overview_layout.addWidget(palette_heading)
        self.independent_palette_table = QTableWidget(0, 4)
        self.independent_palette_table.setHorizontalHeaderLabels(
            ("参考图颜色", "面积", "当前截图颜色", "面积")
        )
        self.independent_palette_table.verticalHeader().setVisible(False)
        self.independent_palette_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.independent_palette_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.independent_palette_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.independent_palette_table.cellClicked.connect(
            self._independent_palette_clicked
        )
        overview_layout.addWidget(self.independent_palette_table)
        self.content_layout.addWidget(overview_box)

        self.distribution_metric.currentIndexChanged.connect(
            self.distribution_parameters_changed
        )
        self.distribution_bins.currentIndexChanged.connect(
            self.distribution_parameters_changed
        )
        self.show_reference_distribution.toggled.connect(
            self._distribution_visibility_changed
        )
        self.show_current_distribution.toggled.connect(
            self._distribution_visibility_changed
        )

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
        self.palette_sample_label.setProperty("role", "muted")
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
        note.setProperty("role", "muted")
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
        self.distribution_chart.clear()
        self.independent_palette_table.setRowCount(0)
        self.palette_table.setRowCount(0)
        self.palette_sample_label.setText("等待参考图与当前截图")
        self.luminance_table.clearContents()
        self.reference_thumbnail.setPixmap(QPixmap())
        self.reference_thumbnail.setText("参考图三阶缩略图")
        self.current_thumbnail.setPixmap(QPixmap())
        self.current_thumbnail.setText("当前截图三阶缩略图")

    def distribution_parameters(self) -> tuple[str, int, float]:
        return (
            str(self.distribution_metric.currentData()),
            int(self.distribution_bins.currentData()),
            0.04,
        )

    def set_distribution(self, result: DistributionComparison) -> None:
        self.distribution_chart.set_result(result)
        if result.metric == "oklab_hue":
            self.distribution_note.setText(
                "低彩度过滤：Oklab C < 0.04。"
                f"参考图中性色 {result.reference_excluded_ratio * 100:.1f}%，"
                f"当前截图 {result.current_excluded_ratio * 100:.1f}%。"
            )
        else:
            self.distribution_note.setText(
                "两图使用相同范围和档位；纵轴为各档像素占比。"
            )

    def set_independent_palettes(
        self,
        reference: tuple[PaletteColour, ...],
        current: tuple[PaletteColour, ...],
    ) -> None:
        self.independent_palette_table.setRowCount(max(len(reference), len(current)))
        for row in range(self.independent_palette_table.rowCount()):
            if row < len(reference):
                self._set_palette_pair_cells(row, 0, reference[row])
            if row < len(current):
                self._set_palette_pair_cells(row, 2, current[row])

    def _set_palette_pair_cells(
        self, row: int, column: int, colour: PaletteColour
    ) -> None:
        swatch = QTableWidgetItem(colour.hex_colour)
        swatch.setBackground(QColor(*colour.rgb))
        swatch_pixmap = QPixmap(24, 16)
        swatch_pixmap.fill(QColor(*colour.rgb))
        swatch.setIcon(QIcon(swatch_pixmap))
        swatch.setToolTip(
            f"{colour.hex_colour}\nOklab "
            f"{colour.oklab[0]:.3f}, {colour.oklab[1]:+.3f}, {colour.oklab[2]:+.3f}"
        )
        ratio = QTableWidgetItem(f"{colour.proportion * 100:.1f}%")
        self.independent_palette_table.setItem(row, column, swatch)
        self.independent_palette_table.setItem(row, column + 1, ratio)

    def _independent_palette_clicked(self, row: int, column: int) -> None:
        role = "reference" if column < 2 else "current"
        self.independent_palette_selected.emit(role, row)

    def _distribution_visibility_changed(self) -> None:
        self.distribution_chart.set_series_visible(
            self.show_reference_distribution.isChecked(),
            self.show_current_distribution.isChecked(),
        )

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
        label.setObjectName("analysisThumbnail")
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
