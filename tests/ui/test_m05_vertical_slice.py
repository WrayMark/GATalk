from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtGui import QImage

from scenelens.ui.main_window import MainWindow


def test_canvas_view_state_can_be_synchronized(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    image = QImage(800, 400, QImage.Format.Format_RGB888)
    image.fill(0x808080)
    window.reference_pane.canvas.set_image(image, reset_view=True)
    window.current_pane.canvas.set_image(image, reset_view=True)

    window.reference_pane.canvas.apply_external_view_state(2.0, 0.25, 0.7)
    zoom, center_x, center_y = window.reference_pane.canvas.current_view_state()
    window._sync_from("reference", zoom, center_x, center_y)
    target_zoom, target_x, target_y = (
        window.current_pane.canvas.current_view_state()
    )

    assert target_zoom == zoom
    assert target_x == pytest.approx(center_x, abs=0.02)
    assert target_y == pytest.approx(center_y, abs=0.02)


def test_background_load_and_analysis_reaches_visible_result(
    qtbot,
    tmp_path: Path,
):
    path = tmp_path / "概念图 测试.png"
    Image.new("RGB", (320, 180), (65, 115, 165)).save(path)

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window._load_path("reference", str(path))

    qtbot.waitUntil(lambda: "reference" in window._images, timeout=10_000)
    qtbot.waitUntil(
        lambda: "色板采样" in window.analysis_widgets["reference"].sample_label.text(),
        timeout=10_000,
    )

    assert window.reference_pane.canvas.has_image
    assert window._images["reference"].source_path == path

    previous_generation = window._render_generation["reference"]
    grayscale_index = window.mode_combo.findData("grayscale")
    window.mode_combo.setCurrentIndex(grayscale_index)
    qtbot.waitUntil(
        lambda: window._render_generation["reference"] > previous_generation,
        timeout=10_000,
    )
    qtbot.waitUntil(lambda: window._active_jobs == 0, timeout=10_000)

    rendered = (
        window.reference_pane.canvas._pixmap_item.pixmap().toImage().pixelColor(0, 0)
    )
    assert rendered.red() == rendered.green() == rendered.blue()


def test_ab_mode_shows_exactly_one_image_pane(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window.comparison_combo.setCurrentIndex(
        window.comparison_combo.findData("ab")
    )

    assert window.reference_pane.isVisible()
    assert not window.current_pane.isVisible()

    window._toggle_ab()

    assert not window.reference_pane.isVisible()
    assert window.current_pane.isVisible()
