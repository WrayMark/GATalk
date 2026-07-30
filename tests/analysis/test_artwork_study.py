import numpy as np
import pytest

from scenelens.analysis.artwork_study import (
    ANALYZER_VERSION,
    analyze_artwork,
    format_local_analysis_summary,
)
from scenelens.analysis.pipeline import measure_image


def test_artwork_analysis_is_deterministic_and_reports_normalized_spatial_cells():
    rgb = np.zeros((90, 120, 3), dtype=np.uint8)
    rgb[:, :40] = (18, 25, 38)
    rgb[:45, 40:80] = (220, 150, 55)
    rgb[45:, 40:80] = (75, 130, 92)
    rgb[:, 80:] = (180, 190, 205)
    measurements = measure_image(rgb, palette_colours=8)

    first = analyze_artwork(rgb, measurements)
    second = analyze_artwork(rgb, measurements)

    assert first.to_dict() == second.to_dict()
    assert first.analyzer_version == ANALYZER_VERSION
    assert len(first.spatial_cells) == 9
    assert sum(first.value_structure["three_value_ratios"]) == pytest.approx(1.0)
    assert max(item.attention_proxy for item in first.spatial_cells) == pytest.approx(
        1.0
    )
    for item in first.spatial_cells:
        x, y, width, height = item.normalized_rect
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0
        assert x + width <= 1.0 + 1e-12
        assert y + height <= 1.0 + 1e-12


def test_artwork_analysis_labels_attention_as_proxy_not_saliency_truth():
    rgb = np.full((48, 64, 3), 127, dtype=np.uint8)
    result = analyze_artwork(rgb, measure_image(rgb))
    summary = format_local_analysis_summary(result)

    assert "注意力代理" in summary
    assert "不等同于真实视觉焦点" in summary
    assert any("不等同于眼动" in item for item in result.limitations)


def test_artwork_analysis_keeps_original_array_read_only():
    rgb = np.zeros((40, 60, 3), dtype=np.uint8)
    rgb[::2, ::2] = (255, 80, 10)
    original = rgb.copy()

    analyze_artwork(rgb, measure_image(rgb))

    assert np.array_equal(rgb, original)
