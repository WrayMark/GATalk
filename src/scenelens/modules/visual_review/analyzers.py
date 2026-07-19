from __future__ import annotations

from typing import Any

import numpy as np

from scenelens.analysis.luminance import three_value_ratios
from scenelens.analysis.models import (
    ImageMeasurements,
    LuminanceComparison,
    SharedPaletteResult,
)
from scenelens.analysis.palette import (
    DEFAULT_MAX_SAMPLE_PIXELS,
    DEFAULT_RANDOM_SEED,
)
from scenelens.analysis.pipeline import measure_image
from scenelens.analysis.shared_palette import extract_shared_oklab_palette
from scenelens.analysis.region_analysis import (
    DEFAULT_HUE_BINS,
    DEFAULT_MAX_REGION_COLOUR_SAMPLES,
    DEFAULT_NEUTRAL_CHROMA_THRESHOLD,
    PairedRegionAnalysis,
    analyze_paired_regions,
)
from scenelens.core.analyzers import (
    AnalyzerDescriptor,
    AnalyzerRequest,
    deterministic_analyzer_cache_key,
)
from scenelens.modules.visual_review import MODULE_ID


BASIC_MEASUREMENTS_ANALYZER_ID = "basic_image_measurements"
SHARED_PALETTE_ANALYZER_ID = "shared_oklab_palette"
LUMINANCE_COMPARISON_ANALYZER_ID = "three_value_luminance_comparison"
PAIRED_REGION_ANALYZER_ID = "paired_region_comparison"


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


class SharedPaletteAnalyzer:
    descriptor = AnalyzerDescriptor(
        module_id=MODULE_ID,
        analyzer_id=SHARED_PALETTE_ANALYZER_ID,
        display_name="共享 Oklab 色板",
        version="1",
        supported_inputs=(
            "reference.numpy.rgb.uint8",
            "current.numpy.rgb.uint8",
        ),
        parameter_schema={
            "type": "object",
            "required": [
                "colour_count",
                "random_seed",
                "max_samples_per_image",
                "colour_space",
                "sampling",
            ],
            "properties": {
                "colour_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 32,
                },
                "random_seed": {"type": "integer"},
                "max_samples_per_image": {"type": "integer", "minimum": 1},
                "colour_space": {"const": "Oklab"},
                "sampling": {"const": "equal-bounded-spatial-v1"},
            },
        },
        output_schema={
            "type": "object",
            "required": [
                "colours",
                "reference_sample_count",
                "current_sample_count",
            ],
        },
    )

    @staticmethod
    def default_parameters(
        colour_count: int = 8,
        random_seed: int = DEFAULT_RANDOM_SEED,
        max_samples_per_image: int = DEFAULT_MAX_SAMPLE_PIXELS,
    ) -> dict[str, Any]:
        return {
            "colour_count": int(colour_count),
            "random_seed": int(random_seed),
            "max_samples_per_image": int(max_samples_per_image),
            "colour_space": "Oklab",
            "sampling": "equal-bounded-spatial-v1",
        }

    def run(self, request: AnalyzerRequest) -> SharedPaletteResult:
        parameters = request.parameters
        return extract_shared_oklab_palette(
            np.asarray(request.inputs["reference_rgb"], dtype=np.uint8),
            np.asarray(request.inputs["current_rgb"], dtype=np.uint8),
            colour_count=int(parameters["colour_count"]),
            random_seed=int(parameters["random_seed"]),
            max_samples_per_image=int(parameters["max_samples_per_image"]),
        )

    def cache_key(self, request: AnalyzerRequest) -> str:
        return deterministic_analyzer_cache_key(self.descriptor, request)


class LuminanceComparisonAnalyzer:
    descriptor = AnalyzerDescriptor(
        module_id=MODULE_ID,
        analyzer_id=LUMINANCE_COMPARISON_ANALYZER_ID,
        display_name="三阶明度比例比较",
        version="1",
        supported_inputs=(
            "reference.numpy.rgb.uint8",
            "current.numpy.rgb.uint8",
        ),
        parameter_schema={
            "type": "object",
            "required": ["low_threshold", "high_threshold", "luminance"],
            "properties": {
                "low_threshold": {
                    "type": "number",
                    "exclusiveMinimum": 0.0,
                },
                "high_threshold": {
                    "type": "number",
                    "exclusiveMaximum": 1.0,
                },
                "luminance": {
                    "const": "linear-srgb-rec709-to-display-srgb-v1"
                },
            },
        },
        output_schema={
            "type": "object",
            "required": [
                "low_threshold",
                "high_threshold",
                "reference_ratios",
                "current_ratios",
            ],
        },
    )

    @staticmethod
    def default_parameters(
        low_threshold: float = 1.0 / 3.0,
        high_threshold: float = 2.0 / 3.0,
    ) -> dict[str, Any]:
        return {
            "low_threshold": float(low_threshold),
            "high_threshold": float(high_threshold),
            "luminance": "linear-srgb-rec709-to-display-srgb-v1",
        }

    def run(self, request: AnalyzerRequest) -> LuminanceComparison:
        low = float(request.parameters["low_threshold"])
        high = float(request.parameters["high_threshold"])
        return LuminanceComparison(
            low_threshold=low,
            high_threshold=high,
            reference_ratios=three_value_ratios(
                np.asarray(request.inputs["reference_rgb"], dtype=np.uint8),
                low,
                high,
            ),
            current_ratios=three_value_ratios(
                np.asarray(request.inputs["current_rgb"], dtype=np.uint8),
                low,
                high,
            ),
        )

    def cache_key(self, request: AnalyzerRequest) -> str:
        return deterministic_analyzer_cache_key(self.descriptor, request)


class PairedRegionAnalyzer:
    descriptor = AnalyzerDescriptor(
        module_id=MODULE_ID,
        analyzer_id=PAIRED_REGION_ANALYZER_ID,
        display_name="成对区域明度与色彩比较",
        version="1",
        supported_inputs=(
            "reference.numpy.rgb.uint8",
            "current.numpy.rgb.uint8",
            "reference.normalized_rect",
            "current.normalized_rect",
            "shared_palette.oklab_centres",
        ),
        parameter_schema={
            "type": "object",
            "required": [
                "low_threshold",
                "high_threshold",
                "neutral_chroma_threshold",
                "hue_bins",
                "max_colour_samples",
                "luminance_percentiles",
                "colour_space",
            ],
        },
        output_schema={
            "type": "object",
            "required": [
                "reference",
                "current",
                "low_threshold",
                "high_threshold",
                "neutral_chroma_threshold",
            ],
        },
    )

    @staticmethod
    def default_parameters(
        low_threshold: float = 1.0 / 3.0,
        high_threshold: float = 2.0 / 3.0,
        neutral_chroma_threshold: float = DEFAULT_NEUTRAL_CHROMA_THRESHOLD,
        hue_bins: int = DEFAULT_HUE_BINS,
        max_colour_samples: int = DEFAULT_MAX_REGION_COLOUR_SAMPLES,
    ) -> dict[str, Any]:
        return {
            "low_threshold": float(low_threshold),
            "high_threshold": float(high_threshold),
            "neutral_chroma_threshold": float(neutral_chroma_threshold),
            "hue_bins": int(hue_bins),
            "max_colour_samples": int(max_colour_samples),
            "luminance_percentiles": "linear-srgb-relative-luminance-v1",
            "three_value_luminance": "display-srgb-from-linear-v1",
            "colour_space": "Oklab",
            "hue_statistics": "neutral-filtered-chroma-weighted-circular-v1",
            "colour_sampling": "bounded-spatial-area-v1",
        }

    def run(self, request: AnalyzerRequest) -> PairedRegionAnalysis:
        parameters = request.parameters
        return analyze_paired_regions(
            np.asarray(request.inputs["reference_rgb"], dtype=np.uint8),
            np.asarray(request.inputs["current_rgb"], dtype=np.uint8),
            tuple(request.inputs["reference_rect"]),
            tuple(request.inputs["current_rect"]),
            np.asarray(
                request.inputs["shared_palette_centres"],
                dtype=np.float64,
            ),
            low_threshold=float(parameters["low_threshold"]),
            high_threshold=float(parameters["high_threshold"]),
            neutral_chroma_threshold=float(
                parameters["neutral_chroma_threshold"]
            ),
            hue_bins=int(parameters["hue_bins"]),
            max_colour_samples=int(parameters["max_colour_samples"]),
        )

    def cache_key(self, request: AnalyzerRequest) -> str:
        return deterministic_analyzer_cache_key(self.descriptor, request)
