from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from scenelens.analysis.models import ImageMeasurements, PaletteColour
from scenelens.imaging.loader import LoadedImage


class HistogramWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._values: tuple[float, ...] = ()
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_values(self, values) -> None:
        self._values = tuple(float(value) for value in values)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = QRectF(self.rect()).adjusted(8.0, 8.0, -8.0, -18.0)
        painter.fillRect(rect, QColor("#15171A"))
        painter.setPen(QPen(QColor("#3C4043"), 1.0))
        painter.drawRect(rect)

        if not self._values:
            painter.setPen(QColor("#80868B"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "等待分析")
            return

        peak = max(self._values)
        if peak <= 0:
            return
        bar_width = rect.width() / len(self._values)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#8AB4F8"))
        for index, value in enumerate(self._values):
            height = rect.height() * value / peak
            painter.drawRect(
                QRectF(
                    rect.left() + index * bar_width,
                    rect.bottom() - height,
                    max(1.0, bar_width),
                    height,
                )
            )
        painter.setPen(QColor("#9AA0A6"))
        painter.drawText(
            QRectF(rect.left(), rect.bottom() + 2.0, rect.width(), 14.0),
            Qt.AlignmentFlag.AlignLeft,
            "暗",
        )
        painter.drawText(
            QRectF(rect.left(), rect.bottom() + 2.0, rect.width(), 14.0),
            Qt.AlignmentFlag.AlignRight,
            "亮",
        )


class PaletteWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._palette: tuple[PaletteColour, ...] = ()
        self.setMinimumHeight(250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_palette(self, palette: tuple[PaletteColour, ...]) -> None:
        self._palette = palette
        row_count = max(1, len(palette))
        self.setMinimumHeight(row_count * 31 + 8)
        self.updateGeometry()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self._palette:
            painter.setPen(QColor("#80868B"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "等待分析")
            return

        metrics = QFontMetrics(self.font())
        row_height = 31.0
        for index, item in enumerate(self._palette):
            top = 4.0 + index * row_height
            colour_rect = QRectF(4.0, top, 54.0, 24.0)
            painter.fillRect(colour_rect, QColor(*item.rgb))
            painter.setPen(QPen(QColor("#5F6368"), 1.0))
            painter.drawRect(colour_rect)

            label = f"{item.hex_colour}   {item.proportion * 100:5.1f}%"
            painter.setPen(QColor("#E8EAED"))
            painter.drawText(
                QRectF(68.0, top, self.width() - 72.0, 24.0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                metrics.elidedText(
                    label,
                    Qt.TextElideMode.ElideRight,
                    max(20, self.width() - 76),
                ),
            )


class AnalysisSummaryWidget(QWidget):
    def __init__(self, empty_text: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.info_label = QLabel(empty_text)
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.info_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        histogram_title = QLabel("测量结果 · 明度直方图")
        histogram_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(histogram_title)
        self.histogram = HistogramWidget()
        layout.addWidget(self.histogram)

        palette_title = QLabel("算法推断 · Oklab 8 色色板")
        palette_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(palette_title)
        self.palette = PaletteWidget()
        layout.addWidget(self.palette)

        self.sample_label = QLabel("")
        self.sample_label.setStyleSheet("color: #9AA0A6;")
        layout.addWidget(self.sample_label)
        layout.addStretch(1)

    def set_loaded_image(self, image: LoadedImage) -> None:
        colour_note = (
            "已根据嵌入 ICC 转换为 sRGB"
            if image.icc_converted_to_srgb
            else "未发现可用 ICC，假定为 sRGB"
        )
        orientation_note = (
            "已应用 EXIF 方向" if image.exif_orientation_applied else "无需 EXIF 旋转"
        )
        warning_text = ""
        if image.warnings:
            warning_text = "\n提示：" + "；".join(image.warnings)
        self.info_label.setText(
            f"{image.source_path.name}\n"
            f"{image.working_size[0]} × {image.working_size[1]} · "
            f"{image.source_format}\n"
            f"{orientation_note} · {colour_note}"
            f"{warning_text}"
        )
        self.sample_label.setText("正在计算色板与直方图…")

    def set_measurements(self, measurements: ImageMeasurements) -> None:
        self.histogram.set_values(measurements.luminance_histogram)
        self.palette.set_palette(measurements.palette)
        self.sample_label.setText(
            f"色板采样 {measurements.sampled_pixel_count:,} 像素；"
            "结果不代表美术优劣。"
        )

