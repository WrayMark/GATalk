from pathlib import Path

import pytest
from PIL import Image

from scenelens.imaging.loader import load_image
from scenelens.modules.visual_review.regions import NormalizedRect


def test_normalized_rect_round_trips_independently_of_display_size():
    rect = NormalizedRect.from_pixel_points(200, 100, 800, 500, 1000, 800)

    assert rect == NormalizedRect(0.2, 0.125, 0.6, 0.5)
    assert rect.to_pixel_rect(1000, 800) == pytest.approx(
        (200.0, 100.0, 600.0, 400.0)
    )
    assert rect.to_pixel_rect(4000, 3200) == pytest.approx(
        (800.0, 400.0, 2400.0, 1600.0)
    )


def test_region_mapping_uses_exif_corrected_working_dimensions(tmp_path: Path):
    path = tmp_path / "旋转后的区域.jpg"
    image = Image.new("RGB", (20, 30), (80, 100, 120))
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)

    loaded = load_image(path)
    rect = NormalizedRect.from_pixel_points(
        3,
        2,
        18,
        12,
        *loaded.working_size,
    )

    assert loaded.original_size == (20, 30)
    assert loaded.working_size == (30, 20)
    assert rect == NormalizedRect(0.1, 0.1, 0.5, 0.5)
    assert rect.to_pixel_rect(*loaded.working_size) == pytest.approx(
        (3.0, 2.0, 15.0, 10.0)
    )


@pytest.mark.parametrize(
    "values",
    [
        (-0.1, 0.0, 0.5, 0.5),
        (0.0, 0.0, 0.0, 0.5),
        (0.8, 0.0, 0.3, 0.5),
        (0.0, 0.8, 0.5, 0.3),
    ],
)
def test_normalized_rect_rejects_empty_or_out_of_bounds_geometry(values):
    with pytest.raises(ValueError):
        NormalizedRect(*values)
