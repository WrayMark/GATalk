from __future__ import annotations

from dataclasses import dataclass
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
    QPainterPath,
    QPen,
    QPolygonF,
    QPixmap,
    QResizeEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsEllipseItem,
    QGraphicsPixmapItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
)

from scenelens.imaging.loader import is_supported_image


@dataclass(frozen=True)
class RegionOverlaySpec:
    region_id: str
    name: str
    normalized_rect: tuple[float, float, float, float]
    colour: str
    selected: bool = False
    muted: bool = False


@dataclass(frozen=True)
class AnnotationOverlaySpec:
    annotation_id: str
    kind: str
    points: tuple[tuple[float, float], ...]
    label: str
    colour: str = "#FFD166"


class _RegionOverlayItem(QGraphicsRectItem):
    _HANDLE_SIZE_SCREEN = 8.0
    _MIN_SIZE_SCENE = 4.0

    def __init__(
        self,
        owner: ImageCanvas,
        spec: RegionOverlaySpec,
        rect: QRectF,
    ) -> None:
        super().__init__(rect)
        self.owner = owner
        self.region_id = spec.region_id
        self.name = spec.name
        self.colour = QColor(spec.colour)
        self.muted = spec.muted
        self._resize_handle: str | None = None
        self._resize_origin = QRectF()
        self._geometry_before_press = QRectF()
        self.setZValue(10.0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.label_background = QGraphicsRectItem(self)
        label_brush = QColor(self.colour)
        label_brush.setAlpha(190 if spec.selected else 135)
        self.label_background.setBrush(QBrush(label_brush))
        self.label_background.setPen(QPen(Qt.PenStyle.NoPen))
        self.label_background.setZValue(0.5)
        self.label = QGraphicsSimpleTextItem(spec.name, self)
        self.label.setBrush(QBrush(QColor("#FFFFFF")))
        self.label.setZValue(1.0)
        self.label.setOpacity(0.45 if spec.muted else 1.0)
        self._update_label()
        self.setSelected(spec.selected)
        self.set_editable(owner.region_mode)

    def set_editable(self, enabled: bool) -> None:
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton
            if enabled
            else Qt.MouseButton.NoButton
        )
        self.update()

    def scene_geometry(self) -> QRectF:
        mapped = self.mapRectToScene(self.rect())
        return mapped.boundingRect() if hasattr(mapped, "boundingRect") else mapped

    def paint(self, painter, option, widget=None) -> None:
        del option, widget
        painter.setBrush(Qt.BrushStyle.NoBrush)
        alpha = 215 if self.isSelected() else (70 if self.muted else 145)
        pen = QPen(
            QColor(
                self.colour.red(),
                self.colour.green(),
                self.colour.blue(),
                alpha,
            )
        )
        pen.setCosmetic(True)
        pen.setWidth(2 if self.isSelected() else 1)
        painter.setPen(pen)
        painter.drawRect(self.rect())
        if self.isSelected() and self.owner.region_mode:
            painter.setBrush(QBrush(self.colour))
            painter.setPen(QPen(QColor("#FFFFFF")))
            size = self._handle_scene_size()
            for point in self._handle_points(self.rect()).values():
                painter.drawRect(
                    QRectF(
                        point.x() - size / 2.0,
                        point.y() - size / 2.0,
                        size,
                        size,
                    )
                )

    def mousePressEvent(self, event) -> None:
        self._geometry_before_press = self.scene_geometry()
        if self.owner.region_mode and event.button() == Qt.MouseButton.LeftButton:
            handle = self._hit_handle(event.pos())
            if handle is not None:
                self._resize_handle = handle
                self._resize_origin = self.scene_geometry()
                self.setPos(0.0, 0.0)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resize_handle is None:
            super().mouseMoveEvent(event)
            return
        point = event.scenePos()
        bounds = self.owner.image_scene_rect()
        point.setX(max(bounds.left(), min(bounds.right(), point.x())))
        point.setY(max(bounds.top(), min(bounds.bottom(), point.y())))
        rect = QRectF(self._resize_origin)
        handle = self._resize_handle
        if "l" in handle:
            rect.setLeft(min(point.x(), rect.right() - self._MIN_SIZE_SCENE))
        if "r" in handle:
            rect.setRight(max(point.x(), rect.left() + self._MIN_SIZE_SCENE))
        if "t" in handle:
            rect.setTop(min(point.y(), rect.bottom() - self._MIN_SIZE_SCENE))
        if "b" in handle:
            rect.setBottom(max(point.y(), rect.top() + self._MIN_SIZE_SCENE))
        self.setRect(rect.normalized())
        self._update_label()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._resize_handle is not None:
            self._resize_handle = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)
        self._update_label()
        if self.scene_geometry() != self._geometry_before_press:
            self.owner._region_item_geometry_finished(self)

    def itemChange(self, change, value):
        if (
            change
            == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and self.owner.region_mode
        ):
            next_pos = QPointF(value)
            bounds = self.owner.image_scene_rect()
            local = self.rect()
            next_pos.setX(
                max(
                    bounds.left() - local.left(),
                    min(bounds.right() - local.right(), next_pos.x()),
                )
            )
            next_pos.setY(
                max(
                    bounds.top() - local.top(),
                    min(bounds.bottom() - local.bottom(), next_pos.y()),
                )
            )
            return next_pos
        if (
            change
            == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged
            and bool(value)
        ):
            self.owner.region_selected.emit(self.region_id)
        return super().itemChange(change, value)

    def _update_label(self) -> None:
        label_x = self.rect().left() + 4.0
        label_y = self.rect().top() + 3.0
        self.label.setPos(label_x, label_y)
        bounds = self.label.boundingRect()
        self.label_background.setRect(
            label_x - 3.0,
            label_y - 2.0,
            bounds.width() + 6.0,
            bounds.height() + 4.0,
        )
        self.label.setToolTip(self.name)

    def _handle_scene_size(self) -> float:
        scale = max(0.01, abs(self.owner.transform().m11()))
        return self._HANDLE_SIZE_SCREEN / scale

    @staticmethod
    def _handle_points(rect: QRectF) -> dict[str, QPointF]:
        return {
            "lt": rect.topLeft(),
            "t": QPointF(rect.center().x(), rect.top()),
            "rt": rect.topRight(),
            "r": QPointF(rect.right(), rect.center().y()),
            "rb": rect.bottomRight(),
            "b": QPointF(rect.center().x(), rect.bottom()),
            "lb": rect.bottomLeft(),
            "l": QPointF(rect.left(), rect.center().y()),
        }

    def _hit_handle(self, point: QPointF) -> str | None:
        if not self.isSelected():
            return None
        tolerance = self._handle_scene_size()
        for name, handle_point in self._handle_points(self.rect()).items():
            if (
                abs(point.x() - handle_point.x()) <= tolerance
                and abs(point.y() - handle_point.y()) <= tolerance
            ):
                return name
        return None


class ImageCanvas(QGraphicsView):
    file_dropped = Signal(str)
    view_state_changed = Signal(float, float, float)
    region_created = Signal(object)
    region_creation_rejected = Signal(str)
    region_selected = Signal(str)
    region_geometry_changed = Signal(str, object)

    def __init__(self, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation
        )
        self._scene.addItem(self._pixmap_item)
        self._overlay_item = QGraphicsPixmapItem()
        self._overlay_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation
        )
        self._overlay_item.setZValue(1.0)
        self._overlay_item.setVisible(False)
        self._scene.addItem(self._overlay_item)

        self._placeholder = QGraphicsTextItem(placeholder)
        self._placeholder.setDefaultTextColor(QColor("#9AA0A6"))
        self._scene.addItem(self._placeholder)

        self._has_image = False
        self._region_mode = False
        self._regions_visible = True
        self._region_items: dict[str, _RegionOverlayItem] = {}
        self._annotation_items: list[QGraphicsItem] = []
        self._region_drag_start: QPointF | None = None
        self._region_rubber_band: QGraphicsRectItem | None = None
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

    @property
    def has_overlay(self) -> bool:
        return self._overlay_item.isVisible()

    @property
    def region_mode(self) -> bool:
        return self._region_mode

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
        self.clear_overlay()
        self.clear_region_overlays()
        self.clear_annotation_overlays()
        self._placeholder.setVisible(True)
        self._scene.setSceneRect(QRectF(0.0, 0.0, 640.0, 480.0))
        self._has_image = False
        self._zoom_factor = 1.0
        self._center_normalized = QPointF(0.5, 0.5)
        self.resetTransform()
        self._layout_placeholder()

    def set_overlay(self, image: QImage) -> None:
        if not self._has_image:
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.size() != self._pixmap_item.pixmap().size():
            raise ValueError("overlay size must match the current image")
        self._overlay_item.setPixmap(pixmap)
        self._overlay_item.setVisible(True)

    def clear_overlay(self) -> None:
        self._overlay_item.setPixmap(QPixmap())
        self._overlay_item.setVisible(False)

    def image_scene_rect(self) -> QRectF:
        return QRectF(self._pixmap_item.pixmap().rect())

    def set_region_mode(self, enabled: bool) -> None:
        self._region_mode = bool(enabled)
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag
            if self._region_mode
            else QGraphicsView.DragMode.ScrollHandDrag
        )
        self.viewport().setCursor(
            Qt.CursorShape.CrossCursor
            if self._region_mode
            else Qt.CursorShape.ArrowCursor
        )
        for item in self._region_items.values():
            item.set_editable(self._region_mode)
        if not self._region_mode:
            self.cancel_region_creation()

    def set_regions_visible(self, visible: bool) -> None:
        self._regions_visible = bool(visible)
        for item in self._region_items.values():
            item.setVisible(self._regions_visible)

    def set_region_overlays(
        self,
        specs: tuple[RegionOverlaySpec, ...] | list[RegionOverlaySpec],
    ) -> None:
        self.clear_region_overlays()
        if not self._has_image:
            return
        width = self.image_scene_rect().width()
        height = self.image_scene_rect().height()
        for spec in specs:
            x, y, region_width, region_height = spec.normalized_rect
            item = _RegionOverlayItem(
                self,
                spec,
                QRectF(
                    x * width,
                    y * height,
                    region_width * width,
                    region_height * height,
                ),
            )
            item.setVisible(self._regions_visible)
            self._scene.addItem(item)
            self._region_items[spec.region_id] = item

    def clear_region_overlays(self) -> None:
        self.cancel_region_creation()
        for item in self._region_items.values():
            self._scene.removeItem(item)
        self._region_items.clear()

    def set_annotation_overlays(
        self,
        specs: tuple[AnnotationOverlaySpec, ...]
        | list[AnnotationOverlaySpec],
    ) -> None:
        self.clear_annotation_overlays()
        if not self._has_image:
            return
        bounds = self.image_scene_rect()
        for spec in specs:
            points = [
                QPointF(
                    max(0.0, min(1.0, x)) * bounds.width(),
                    max(0.0, min(1.0, y)) * bounds.height(),
                )
                for x, y in spec.points
            ]
            if not points:
                continue
            colour = QColor(spec.colour)
            pen = QPen(colour)
            pen.setCosmetic(True)
            pen.setWidth(3 if spec.kind == "light_arrow" else 2)
            if (
                spec.kind
                in {"light_area", "darken_area", "visual_weight"}
                and len(points) >= 2
            ):
                rect = QRectF(points[0], points[-1]).normalized()
                if spec.kind == "visual_weight":
                    area_item = QGraphicsEllipseItem(rect)
                else:
                    area_item = QGraphicsRectItem(rect)
                fill = QColor(colour)
                fill.setAlpha(35 if spec.kind != "darken_area" else 75)
                area_item.setBrush(QBrush(fill))
                area_item.setPen(pen)
                area_item.setZValue(30.0)
                area_item.setToolTip(spec.label)
                self._scene.addItem(area_item)
                self._annotation_items.append(area_item)
                label = QGraphicsSimpleTextItem(spec.label)
                label.setBrush(QBrush(colour))
                label.setPos(rect.topLeft() + QPointF(5.0, 5.0))
                label.setZValue(32.0)
                self._scene.addItem(label)
                self._annotation_items.append(label)
                continue
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            path_item = QGraphicsPathItem(path)
            path_item.setPen(pen)
            path_item.setZValue(30.0)
            path_item.setToolTip(spec.label)
            self._scene.addItem(path_item)
            self._annotation_items.append(path_item)

            if spec.kind == "light_arrow" and len(points) >= 2:
                start, end = points[-2], points[-1]
                direction = start - end
                length = max(
                    1.0,
                    (direction.x() ** 2 + direction.y() ** 2) ** 0.5,
                )
                unit_x = direction.x() / length
                unit_y = direction.y() / length
                scale = 16.0
                left = QPointF(
                    end.x() + (unit_x - unit_y * 0.55) * scale,
                    end.y() + (unit_y + unit_x * 0.55) * scale,
                )
                right = QPointF(
                    end.x() + (unit_x + unit_y * 0.55) * scale,
                    end.y() + (unit_y - unit_x * 0.55) * scale,
                )
                arrow = QGraphicsPolygonItem(QPolygonF([end, left, right]))
                arrow.setBrush(QBrush(colour))
                arrow.setPen(QPen(Qt.PenStyle.NoPen))
                arrow.setZValue(31.0)
                self._scene.addItem(arrow)
                self._annotation_items.append(arrow)

            label = QGraphicsSimpleTextItem(spec.label)
            label.setBrush(QBrush(colour))
            label.setPos(points[0] + QPointF(5.0, 5.0))
            label.setZValue(32.0)
            self._scene.addItem(label)
            self._annotation_items.append(label)

    def clear_annotation_overlays(self) -> None:
        for item in self._annotation_items:
            self._scene.removeItem(item)
        self._annotation_items.clear()

    @property
    def annotation_overlay_count(self) -> int:
        return len(self._annotation_items)

    def select_region(self, region_id: str | None) -> None:
        for item_id, item in self._region_items.items():
            item.setSelected(item_id == region_id)

    def cancel_region_creation(self) -> None:
        self._region_drag_start = None
        if self._region_rubber_band is not None:
            self._scene.removeItem(self._region_rubber_band)
            self._region_rubber_band = None

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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            self._region_mode
            and self._has_image
            and event.button() == Qt.MouseButton.LeftButton
        ):
            item = self.itemAt(event.position().toPoint())
            while item is not None and not isinstance(item, _RegionOverlayItem):
                item = item.parentItem()
            if item is None:
                start = self._clamp_to_image(
                    self.mapToScene(event.position().toPoint())
                )
                self._region_drag_start = start
                self._region_rubber_band = QGraphicsRectItem(QRectF(start, start))
                pen = QPen(QColor("#4FC3F7"))
                pen.setCosmetic(True)
                pen.setStyle(Qt.PenStyle.DashLine)
                self._region_rubber_band.setPen(pen)
                self._region_rubber_band.setBrush(
                    QBrush(QColor(79, 195, 247, 35))
                )
                self._region_rubber_band.setZValue(20.0)
                self._scene.addItem(self._region_rubber_band)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._region_drag_start is not None and self._region_rubber_band is not None:
            current = self._clamp_to_image(
                self.mapToScene(event.position().toPoint())
            )
            self._region_rubber_band.setRect(
                QRectF(self._region_drag_start, current).normalized()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._region_drag_start is not None:
            current = self._clamp_to_image(
                self.mapToScene(event.position().toPoint())
            )
            rect = QRectF(self._region_drag_start, current).normalized()
            self.cancel_region_creation()
            image_rect = self.image_scene_rect()
            if (
                image_rect.width() > 0
                and image_rect.height() > 0
                and rect.width() > 0
                and rect.height() > 0
            ):
                self.region_created.emit(
                    (
                        rect.x() / image_rect.width(),
                        rect.y() / image_rect.height(),
                        rect.width() / image_rect.width(),
                        rect.height() / image_rect.height(),
                    )
                )
            else:
                self.region_creation_rejected.emit(
                    "区域必须具有可见的宽度和高度，请重新拖动。"
                )
            event.accept()
            return
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

    def _clamp_to_image(self, point: QPointF) -> QPointF:
        bounds = self.image_scene_rect()
        return QPointF(
            max(bounds.left(), min(bounds.right(), point.x())),
            max(bounds.top(), min(bounds.bottom(), point.y())),
        )

    def _region_item_geometry_finished(self, item: _RegionOverlayItem) -> None:
        bounds = self.image_scene_rect()
        rect = item.scene_geometry().intersected(bounds)
        if bounds.width() <= 0 or bounds.height() <= 0 or rect.isEmpty():
            return
        self.region_geometry_changed.emit(
            item.region_id,
            (
                rect.x() / bounds.width(),
                rect.y() / bounds.height(),
                rect.width() / bounds.width(),
                rect.height() / bounds.height(),
            ),
        )

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
