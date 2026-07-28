import numpy as np

from scenelens.imaging.qt import numpy_to_qimage
from scenelens.ui.image_canvas import (
    AnnotationOverlaySpec,
    GuideOverlaySpec,
    ImageCanvas,
)


def test_structured_lighting_annotations_render_and_clear(qtbot) -> None:
    canvas = ImageCanvas("placeholder")
    qtbot.addWidget(canvas)
    image = np.full((100, 200, 3), 80, dtype=np.uint8)
    canvas.set_image(numpy_to_qimage(image))
    canvas.set_annotation_overlays(
        [
            AnnotationOverlaySpec(
                annotation_id="arrow",
                kind="light_arrow",
                points=((0.1, 0.1), (0.5, 0.5)),
                label="主光方向",
            ),
            AnnotationOverlaySpec(
                annotation_id="area",
                kind="darken_area",
                points=((0.6, 0.2), (0.8, 0.4)),
                label="压暗",
            ),
        ]
    )
    assert canvas.annotation_overlay_count >= 5
    canvas.clear_annotation_overlays()
    assert canvas.annotation_overlay_count == 0


def test_composition_guide_scales_with_image_and_survives_image_change(
    qtbot,
) -> None:
    canvas = ImageCanvas("placeholder")
    qtbot.addWidget(canvas)
    guide = GuideOverlaySpec(
        "thirds",
        "三分法（九宫格）",
        (
            ((1.0 / 3.0, 0.0), (1.0 / 3.0, 1.0)),
            ((0.0, 1.0 / 3.0), (1.0, 1.0 / 3.0)),
        ),
    )
    canvas.set_guide_overlay(guide)
    canvas.set_image(
        numpy_to_qimage(np.full((100, 200, 3), 80, dtype=np.uint8))
    )
    assert canvas.guide_overlay_count == 3

    canvas.set_image(
        numpy_to_qimage(np.full((200, 400, 3), 80, dtype=np.uint8))
    )
    assert canvas.guide_overlay_count == 3
    canvas.clear_guide_overlay()
    assert canvas.guide_overlay_count == 0
