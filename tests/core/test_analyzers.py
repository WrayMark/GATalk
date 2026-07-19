from __future__ import annotations

import numpy as np
import pytest

from scenelens.core.analyzers import AnalyzerRegistry, AnalyzerRequest
from scenelens.modules.visual_review import MODULE_ID
from scenelens.modules.visual_review.analyzers import (
    BASIC_MEASUREMENTS_ANALYZER_ID,
    PAIRED_REGION_ANALYZER_ID,
    BasicImageMeasurementsAnalyzer,
)
from scenelens.modules.visual_review.registry import create_visual_review_registry


def test_analyzer_registry_exposes_stable_module_identity():
    analyzer = BasicImageMeasurementsAnalyzer()
    registry = AnalyzerRegistry()
    registry.register(analyzer)

    restored = registry.get(MODULE_ID, BASIC_MEASUREMENTS_ANALYZER_ID)

    assert restored is analyzer
    assert restored.descriptor.version == "1"
    assert restored.descriptor.parameter_schema["type"] == "object"
    with pytest.raises(ValueError):
        registry.register(analyzer)


def test_basic_analyzer_cache_key_and_output_are_deterministic():
    analyzer = BasicImageMeasurementsAnalyzer()
    rgb = np.zeros((16, 16, 3), dtype=np.uint8)
    rgb[:, 8:] = (180, 120, 60)
    request = AnalyzerRequest(
        inputs={"rgb": rgb},
        input_hashes={"rgb": "fixed-input-sha256"},
        parameters=analyzer.default_parameters(
            palette_colours=2,
            palette_seed=123,
            palette_max_samples=128,
        ),
    )

    first = analyzer.run(request)
    second = analyzer.run(request)

    assert analyzer.cache_key(request) == analyzer.cache_key(request)
    assert first.palette == second.palette
    assert first.luminance_histogram.tolist() == pytest.approx(
        second.luminance_histogram.tolist()
    )


def test_paired_region_analyzer_is_registered_with_stable_identity():
    registry = create_visual_review_registry()

    analyzer = registry.get(MODULE_ID, PAIRED_REGION_ANALYZER_ID)

    assert analyzer.descriptor.version == "1"
    assert "reference.normalized_rect" in analyzer.descriptor.supported_inputs
