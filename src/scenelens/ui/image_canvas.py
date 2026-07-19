from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from scenelens.imaging.loader import is_supported_image


class ImageCanvas(QGraphicsView):
    file_dropped = Signal(str)
    view_state_changed = Signal(float, float, float)

    def __init__(self, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation
        )
        self._scene.addItem(self._pixmap_item)

        self._placeholder = QGraphicsTextItem(placeholder)
        self._placeholder.setDefaultTextColor(QColor("#9AA0A6"))
        self._scene.addItem(self._placeholder)

        self._has_image = False
        self._zoom_factor = 1.0
        self._center_normalized = QPointF(0.5, 0.5)
        self._updating_view = False

        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setBackgroundBrush(QBrush(QColor("#17191C")))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.horizontalScrollBar().valueChanged.connect(self._scroll_changed)
        self.verticalScrollBar().valueChanged.connect(self._scroll_changed)
        self._layout_placeholder()

    @property
    def has_image(self) -> bool:
        return self._has_image

    def set_image(self, image: QImage, reset_view: bool = False) -> None:
        previous_size = self._pixmap_item.pixmap().size()
        pixmap = QPixmap.fromImage(image)
        self._pixmap_item.setPixmap(pixmap)
        self._pixmap_item.setVisible(True)
        self._placeholder.setVisible(False)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._has_image = True

        if reset_view or previous_size != pixmap.size():
            self._zoom_factor = 1.0
            self._center_normalized = QPointF(0.5, 0.5)
        self._apply_view_state()

    def clear_image(self) -> None:
        self._pixmap_item.setPixmap(QPixmap())
        self._pixmap_item.setVisible(False)
        self._placeholder.setVisible(True)
        self._scene.setSceneRect(QRectF(0.0, 0.0, 640.0, 480.0))
        self._has_image = False
        self._zoom_factor = 1.0
        self._center_normalized = QPointF(0.5, 0.5)
        self.resetTransform()
        self._layout_placeholder()

    def reset_view(self) -> None:
        if not self._has_image:
            return
        self._zoom_factor = 1.0
        self._center_normalized = QPointF(0.5, 0.5)
        self._apply_view_state()
        self._emit_view_state()

    def apply_external_view_state(
        self, zoom_factor: float, center_x: float, center_y: float
    ) -> None:
        if not self._has_image:
            return
        self._zoom_factor = max(0.25, min(32.0, float(zoom_factor)))
        self._center_normalized = QPointF(
            max(0.0, min(1.0, float(center_x))),
            max(0.0, min(1.0, float(center_y))),
        )
        self._apply_view_state()

    def current_view_state(self) -> tuple[float, float, float]:
        if not self._has_image:
            return 1.0, 0.5, 0.5
        center = self.mapToScene(self.viewport().rect().center())
        rect = self._scene.sceneRect()
        center_x = 0.5 if rect.width() <= 0 else center.x() / rect.width()
        center_y = 0.5 if rect.height() <= 0 else center.y() / rect.height()
        return (
            self._zoom_factor,
            max(0.0, min(1.0, center_x)),
            max(0.0, min(1.0, center_y)),
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._first_supported_path(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._first_supported_path(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._first_supported_path(event)
        if path is None:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self.file_dropped.emit(str(path))

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self._has_image:
            super().wheelEvent(event)
            return
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            return
        self._capture_center()
        self._zoom_factor = max(
            0.25,
            min(32.0, self._zoom_factor * (1.18**steps)),
        )
        self._apply_view_state()
        self._emit_view_state()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._has_image:
            self._capture_center()
            self._emit_view_state()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._has_image:
            self.reset_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        if self._has_image:
            self._capture_center()
        super().resizeEvent(event)
        if self._has_image:
            self._apply_view_state()
        else:
            self._layout_placeholder()

    def _first_supported_path(self, event) -> Path | None:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_file() and is_supported_image(path):
                return path
        return None

    def _fit_scale(self) -> float:
        rect = self._scene.sceneRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return 1.0
        viewport = self.viewport().size()
        available_width = max(1.0, viewport.width() - 16.0)
        available_height = max(1.0, viewport.height() - 16.0)
        return min(
            available_width / rect.width(),
            available_height / rect.height(),
        )

    def _apply_view_state(self) -> None:
        if not self._has_image:
            return
        self._updating_view = True
        try:
            scale = self._fit_scale() * self._zoom_factor
            self.setTransform(QTransform.fromScale(scale, scale))
            rect = self._scene.sceneRect()
            self.centerOn(
                rect.width() * self._center_normalized.x(),
                rect.height() * self._center_normalized.y(),
            )
        finally:
            self._updating_view = False

    def _capture_center(self) -> None:
        if not self._has_image:
            return
        _, center_x, center_y = self.current_view_state()
        self._center_normalized = QPointF(center_x, center_y)

    def _scroll_changed(self, _value: int) -> None:
        if self._updating_view or not self._has_image:
            return
        self._capture_center()
        self._emit_view_state()

    def _emit_view_state(self) -> None:
        zoom, center_x, center_y = self.current_view_state()
        self.view_state_changed.emit(zoom, center_x, center_y)

    def _layout_placeholder(self) -> None:
        bounds = self._placeholder.boundingRect()
        scene_width = max(640.0, float(self.viewport().width()))
        scene_height = max(480.0, float(self.viewport().height()))
        self._scene.setSceneRect(0.0, 0.0, scene_width, scene_height)
        self._placeholder.setPos(
            (scene_width - bounds.width()) / 2.0,
            (scene_height - bounds.height()) / 2.0,
        )

