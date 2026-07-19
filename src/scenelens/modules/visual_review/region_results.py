from __future__ import annotations

from typing import Any

from scenelens.analysis.region_analysis import (
    PairedRegionAnalysis,
    RegionStatistics,
)


def paired_region_to_payload(result: PairedRegionAnalysis) -> dict[str, Any]:
    return {
        "reference": _statistics_to_payload(result.reference),
        "current": _statistics_to_payload(result.current),
        "low_threshold": result.low_threshold,
        "high_threshold": result.high_threshold,
        "neutral_chroma_threshold": result.neutral_chroma_threshold,
        "hue_bins": result.hue_bins,
        "max_colour_samples": result.max_colour_samples,
    }


def paired_region_from_payload(
    payload: dict[str, Any],
) -> PairedRegionAnalysis:
    return PairedRegionAnalysis(
        reference=_statistics_from_payload(payload["reference"]),
        current=_statistics_from_payload(payload["current"]),
        low_threshold=float(payload["low_threshold"]),
        high_threshold=float(payload["high_threshold"]),
        neutral_chroma_threshold=float(
            payload["neutral_chroma_threshold"]
        ),
        hue_bins=int(payload["hue_bins"]),
        max_colour_samples=int(payload["max_colour_samples"]),
    )


def _statistics_to_payload(result: RegionStatistics) -> dict[str, Any]:
    return {
        "pixel_count": result.pixel_count,
        "colour_sample_count": result.colour_sample_count,
        "mean_linear_luminance": result.mean_linear_luminance,
        "mean_oklab_l": result.mean_oklab_l,
        "luminance_standard_deviation": (
            result.luminance_standard_deviation
        ),
        "luminance_p10": result.luminance_p10,
        "luminance_p50": result.luminance_p50,
        "luminance_p90": result.luminance_p90,
        "effective_luminance_span": result.effective_luminance_span,
        "three_value_ratios": list(result.three_value_ratios),
        "mean_oklab": list(result.mean_oklab),
        "mean_chroma": result.mean_chroma,
        "median_chroma": result.median_chroma,
        "neutral_ratio": result.neutral_ratio,
        "chromatic_pixel_count": result.chromatic_pixel_count,
        "hue_mean_degrees": result.hue_mean_degrees,
        "hue_distribution": list(result.hue_distribution),
        "shared_palette_proportions": list(
            result.shared_palette_proportions
        ),
    }


def _statistics_from_payload(payload: dict[str, Any]) -> RegionStatistics:
    hue_mean = payload["hue_mean_degrees"]
    return RegionStatistics(
        pixel_count=int(payload["pixel_count"]),
        colour_sample_count=int(payload["colour_sample_count"]),
        mean_linear_luminance=float(payload["mean_linear_luminance"]),
        mean_oklab_l=float(payload["mean_oklab_l"]),
        luminance_standard_deviation=float(
            payload["luminance_standard_deviation"]
        ),
        luminance_p10=float(payload["luminance_p10"]),
        luminance_p50=float(payload["luminance_p50"]),
        luminance_p90=float(payload["luminance_p90"]),
        effective_luminance_span=float(
            payload["effective_luminance_span"]
        ),
        three_value_ratios=tuple(
            float(value) for value in payload["three_value_ratios"]
        ),
        mean_oklab=tuple(float(value) for value in payload["mean_oklab"]),
        mean_chroma=float(payload["mean_chroma"]),
        median_chroma=float(payload["median_chroma"]),
        neutral_ratio=float(payload["neutral_ratio"]),
        chromatic_pixel_count=int(payload["chromatic_pixel_count"]),
        hue_mean_degrees=None if hue_mean is None else float(hue_mean),
        hue_distribution=tuple(
            float(value) for value in payload["hue_distribution"]
        ),
        shared_palette_proportions=tuple(
            float(value)
            for value in payload["shared_palette_proportions"]
        ),
    )
