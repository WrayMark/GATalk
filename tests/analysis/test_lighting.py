import numpy as np

from scenelens.analysis.lighting import (
    clipping_warning,
    exposure_false_colour,
    lighting_luminance_proxy,
    luminance_blur,
    silhouette_map,
    thumbnail_observation,
)


def _gradient() -> np.ndarray:
    row = np.linspace(0, 255, 64, dtype=np.uint8)
    gray = np.repeat(row[None, :], 32, axis=0)
    return np.repeat(gray[..., None], 3, axis=2)


def test_false_colour_and_clipping_warning_are_read_only() -> None:
    source = _gradient()
    original = source.copy()
    false_colour = exposure_false_colour(source)
    warning = clipping_warning(source, shadow_threshold=0.05)
    assert np.array_equal(source, original)
    assert false_colour.shape == source.shape
    assert tuple(warning[0, 0]) == (30, 90, 255)
    assert tuple(warning[0, -1]) == (255, 45, 35)


def test_silhouette_threshold_is_adjustable() -> None:
    source = _gradient()
    low = silhouette_map(source, threshold=0.25)
    high = silhouette_map(source, threshold=0.75)
    assert np.count_nonzero(low) > np.count_nonzero(high)


def test_observation_modes_preserve_canvas_dimensions() -> None:
    source = _gradient()
    for rendered in (
        thumbnail_observation(source, maximum_side=16),
        luminance_blur(source, sigma=2.0),
        lighting_luminance_proxy(source, sigma=2.0),
    ):
        assert rendered.shape == source.shape
        assert rendered.dtype == np.uint8


def test_lighting_proxy_is_not_a_material_removal_operation() -> None:
    source = _gradient()
    result = lighting_luminance_proxy(source)
    assert np.array_equal(result[..., 0], result[..., 1])
    assert not np.shares_memory(result, source)
