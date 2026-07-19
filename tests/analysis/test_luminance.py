import numpy as np
import pytest

from scenelens.analysis.luminance import (
    display_luminance,
    gaussian_blur,
    luminance_histogram,
    quantize_luminance,
    relative_luminance,
)


def test_relative_luminance_uses_linear_srgb():
    rgb = np.array(
        [[[0, 0, 0], [255, 255, 255], [128, 128, 128]]],
        dtype=np.uint8,
    )

    values = relative_luminance(rgb)

    assert values[0, 0] == pytest.approx(0.0)
    assert values[0, 1] == pytest.approx(1.0)
    assert values[0, 2] == pytest.approx(0.21586, abs=2e-4)
    assert display_luminance(rgb)[0, 2] == pytest.approx(128 / 255, abs=2e-3)


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        (3, {0, 127, 255}),
        (5, {0, 63, 127, 191, 255}),
    ],
)
def test_luminance_quantization_has_requested_levels(levels, expected):
    gradient = np.arange(256, dtype=np.uint8)[np.newaxis, :, np.newaxis]
    rgb = np.repeat(gradient, 3, axis=2)

    result = quantize_luminance(rgb, levels)

    assert set(np.unique(result)) == expected
    assert result.shape == rgb.shape


def test_histogram_is_normalized_and_respects_mask():
    rgb = np.array(
        [[[0, 0, 0], [255, 255, 255]]],
        dtype=np.uint8,
    )
    mask = np.array([[True, False]])

    histogram = luminance_histogram(rgb, mask=mask)

    assert histogram.sum() == pytest.approx(1.0)
    assert histogram[0] == pytest.approx(1.0)
    assert histogram[-1] == pytest.approx(0.0)


def test_gaussian_blur_keeps_shape_and_dtype():
    rgb = np.zeros((31, 31, 3), dtype=np.uint8)
    rgb[15, 15] = 255

    blurred = gaussian_blur(rgb, sigma=3.0)

    assert blurred.shape == rgb.shape
    assert blurred.dtype == np.uint8
    assert 0 < blurred[15, 15, 0] < 255

