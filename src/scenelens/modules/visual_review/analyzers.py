from __future__ import annotations

from typing import Any

import numpy as np

from scenelens.analysis.models import ImageMeasurements
from scenelens.analysis.palette import (
    DEFAULT_MAX_SAMPLE_PIXELS,
    DEFAULT_RANDOM_SEED,
)
from scenelens.analysis.pipeline import measure_image
from scenelens.core.analyzers import (
    AnalyzerDescriptor,
    AnalyzerRequest,
    deterministic_analyzer_cache_key,
)
from scenelens.modules.visual_review import MODULE_ID


BASIC_MEASUREMENTS_ANALYZER_ID = "basic_image_measurements"


class BasicImageMeasurementsAnalyzer:
    descriptor = AnalyzerDescriptor(
        module_id=MODULE_ID,
        analyzer_id=BASIC_MEASUREMENTS_ANALYZER_ID,
        display_name="基础图片测量",
        version="1",
        supported_inputs=("numpy.rgb.uint8", "numpy.alpha.uint8?"),
        parameter_schema={
            "type": "object",
            "required": [
                "histogram_bins",
                "luminance",
                "palette_colours",
                "palette_seed",
                "palette_max_samples",
                "palette_space",
            ],
            "properties": {
                "histogram_bins": {"type": "integer", "minimum": 2},
                "luminance": {"type": "string"},
                "palette_colours": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 32,
                },
                "palette_seed": {"type": "integer"},
                "palette_max_samples": {"type": "integer", "minimum": 1},
                "palette_space": {"const": "Oklab"},
            },
        },
        output_schema={
            "type": "object",
            "required": [
                "luminance_histogram",
                "palette",
                "sampled_pixel_count",
            ],
        },
    )

    @staticmethod
    def default_parameters(
        palette_colours: int = 8,
        palette_seed: int = DEFAULT_RANDOM_SEED,
        palette_max_samples: int = DEFAULT_MAX_SAMPLE_PIXELS,
    ) -> dict[str, Any]:
        return {
            "histogram_bins": 256,
            "luminance": "linear-srgb-rec709-to-display-srgb-v1",
            "palette_colours": int(palette_colours),
            "palette_seed": int(palette_seed),
            "palette_max_samples": int(palette_max_samples),
            "palette_space": "Oklab",
        }

    def run(self, request: AnalyzerRequest) -> ImageMeasurements:
        rgb = np.asarray(request.inputs["rgb"], dtype=np.uint8)
        alpha_value = request.inputs.get("alpha")
        alpha = (
            None
            if alpha_value is None
            else np.asarray(alpha_value, dtype=np.uint8)
        )
        parameters = request.parameters
        return measure_image(
            rgb,
            alpha,
            palette_colours=int(parameters["palette_colours"]),
            palette_seed=int(parameters["palette_seed"]),
            palette_max_samples=int(parameters["palette_max_samples"]),
        )

    def cache_key(self, request: AnalyzerRequest) -> str:
        return deterministic_analyzer_cache_key(self.descriptor, request)
