from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QVBoxLayout,
)


class CropGraphicsView(QGraphicsView):
    def __init__(self, image_path: str, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            raise ValueError("无法读取用于局部截图的图片。")
        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene().addItem(self._pixmap_item)
        self.scene().setSceneRect(self._pixmap_item.boundingRect())
        self._start: QPointF | None = None
        self._selection = QGraphicsRectItem()
        self._selection.setPen(QPen(QColor("#4CC9B0"), 2.0))
        self._selection.setBrush(QColor(76, 201, 176, 42))
        self._selection.setZValue(10)
        self.scene().addItem(self._selection)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fitInView(
            self._pixmap_item,
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fitInView(
            self._pixmap_item,
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = self._clamped_scene_point(event.position())
            self._selection.setRect(QRectF(self._start, self._start))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start is not None:
            current = self._clamped_scene_point(event.position())
            self._selection.setRect(QRectF(self._start, current).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._start is not None:
            current = self._clamped_scene_point(event.position())
            self._selection.setRect(QRectF(self._start, current).normalized())
            self._start = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def normalized_rect(self) -> tuple[float, float, float, float] | None:
        rect = self._selection.rect().intersected(
            self._pixmap_item.boundingRect()
        )
        bounds = self._pixmap_item.boundingRect()
        if rect.width() < 2.0 or rect.height() < 2.0:
            return None
        return (
            rect.left() / bounds.width(),
            rect.top() / bounds.height(),
            rect.width() / bounds.width(),
            rect.height() / bounds.height(),
        )

    def _clamped_scene_point(self, viewport_point: QPointF) -> QPointF:
        point = self.mapToScene(viewport_point.toPoint())
        bounds = self._pixmap_item.boundingRect()
        return QPointF(
            max(bounds.left(), min(bounds.right(), point.x())),
            max(bounds.top(), min(bounds.bottom(), point.y())),
        )


class ImageExcerptDialog(QDialog):
    def __init__(self, image_path: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("建立局部截图")
        self.resize(980, 720)
        layout = QVBoxLayout(self)
        instruction = QLabel(
            "在图片上拖出需要保存的范围。局部截图会作为派生资料保存，"
            "原始图片不会被修改。"
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)
        self.view = CropGraphicsView(image_path)
        layout.addWidget(self.view, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存局部截图")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if self.view.normalized_rect() is None:
            self.setWindowTitle("建立局部截图 — 请先拖出有效区域")
            return
        self.accept()

    def normalized_rect(self) -> tuple[float, float, float, float] | None:
        return self.view.normalized_rect()
