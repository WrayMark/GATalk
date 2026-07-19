from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy
import pytest

from scenelens.ui.image_canvas import ImageCanvas, RegionOverlaySpec


def _image() -> QImage:
    image = QImage(400, 240, QImage.Format.Format_RGB888)
    image.fill(Qt.GlobalColor.darkGray)
    return image


def _viewport_point(canvas: ImageCanvas, x: float, y: float) -> QPoint:
    return canvas.mapFromScene(QPointF(x, y))


def test_region_creation_uses_image_coordinates_at_current_zoom(qtbot):
    canvas = ImageCanvas("测试")
    qtbot.addWidget(canvas)
    canvas.resize(800, 500)
    canvas.show()
    canvas.set_image(_image(), reset_view=True)
    canvas.apply_external_view_state(1.5, 0.5, 0.5)
    canvas.set_region_mode(True)
    spy = QSignalSpy(canvas.region_created)
    start = _viewport_point(canvas, 80.0, 48.0)
    end = _viewport_point(canvas, 280.0, 168.0)

    qtbot.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas.viewport(), pos=end)
    qtbot.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)

    assert spy.count() == 1
    assert tuple(spy.at(0)[0]) == pytest.approx(
        (0.2, 0.2, 0.5, 0.5),
        abs=0.002,
    )


def test_region_overlay_move_and_resize_emit_normalized_geometry(qtbot):
    canvas = ImageCanvas("测试")
    qtbot.addWidget(canvas)
    canvas.resize(800, 500)
    canvas.show()
    canvas.set_image(_image(), reset_view=True)
    canvas.set_region_overlays(
        [
            RegionOverlaySpec(
                "region-1",
                "主体",
                (0.2, 0.2, 0.4, 0.4),
                "#4FC3F7",
                selected=True,
            )
        ]
    )
    canvas.set_region_mode(True)
    spy = QSignalSpy(canvas.region_geometry_changed)

    move_start = _viewport_point(canvas, 160.0, 96.0)
    move_end = _viewport_point(canvas, 200.0, 120.0)
    qtbot.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=move_start,
    )
    qtbot.mouseMove(canvas.viewport(), pos=move_end)
    qtbot.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=move_end,
    )

    assert spy.count() == 1
    moved = tuple(spy.at(0)[1])
    assert moved == pytest.approx((0.3, 0.3, 0.4, 0.4), abs=0.002)

    resize_start = _viewport_point(canvas, 280.0, 168.0)
    resize_end = _viewport_point(canvas, 320.0, 192.0)
    qtbot.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=resize_start,
    )
    qtbot.mouseMove(canvas.viewport(), pos=resize_end)
    qtbot.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=resize_end,
    )

    assert spy.count() == 2
    resized = tuple(spy.at(1)[1])
    assert resized == pytest.approx((0.3, 0.3, 0.5, 0.5), abs=0.002)


def test_view_mode_keeps_pan_and_region_mode_uses_cross_cursor(qtbot):
    canvas = ImageCanvas("测试")
    qtbot.addWidget(canvas)
    canvas.set_image(_image())

    canvas.set_region_mode(True)
    assert canvas.region_mode
    assert canvas.dragMode() == ImageCanvas.DragMode.NoDrag
    assert canvas.viewport().cursor().shape() == Qt.CursorShape.CrossCursor

    canvas.set_region_mode(False)
    assert not canvas.region_mode
    assert canvas.dragMode() == ImageCanvas.DragMode.ScrollHandDrag
    assert canvas.viewport().cursor().shape() == Qt.CursorShape.ArrowCursor
