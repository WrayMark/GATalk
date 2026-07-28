from __future__ import annotations

from typing import Any, Mapping

import cv2
import numpy as np

from scenelens.analysis.luminance import display_luminance
from scenelens.analysis.models import ImageMeasurements, UInt8Image


EVIDENCE_DIGEST_VERSION = "1.0.0"


def build_review_evidence_digest(
    reference_rgb: UInt8Image,
    current_rgb: UInt8Image,
    *,
    low_threshold: float,
    high_threshold: float,
    measurements: Mapping[str, ImageMeasurements] | None = None,
    maximum_side: int = 256,
) -> dict[str, Any]:
    """Build bounded, reproducible evidence for a multimodal art review.

    Spatial cells are measurements, not saliency or aesthetic judgements.  The
    palette-derived colour summaries are explicitly labelled as approximations.
    """

    if not 0.0 < low_threshold < high_threshold < 1.0:
        raise ValueError("three-value thresholds must be ordered inside 0..1")
    if maximum_side < 64:
        raise ValueError("maximum_side must be at least 64")
    measurement_map = dict(measurements or {})
    reference = _image_digest(
        reference_rgb,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        measurement=measurement_map.get("reference"),
        maximum_side=maximum_side,
    )
    current = _image_digest(
        current_rgb,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        measurement=measurement_map.get("current"),
        maximum_side=maximum_side,
    )
    numeric_keys = (
        "mean_luminance",
        "luminance_std",
        "p10_luminance",
        "p50_luminance",
        "p90_luminance",
        "effective_luminance_span",
        "dark_ratio",
        "midtone_ratio",
        "bright_ratio",
        "shadow_clip_ratio",
        "highlight_clip_ratio",
        "mean_saturation",
        "neutral_ratio",
        "palette_mean_oklab_l",
        "palette_mean_chroma",
    )
    deltas = {
        key: _rounded(float(current[key]) - float(reference[key]))
        for key in numeric_keys
    }
    return {
        "digest_version": EVIDENCE_DIGEST_VERSION,
        "evidence_type": "measurement",
        "interpretation_limits": [
            "空间九宫格只记录亮度、局部反差和彩度，不等同于视觉焦点或显著性判断。",
            "色彩摘要由固定种子 Oklab 色板加权近似，不替代区域级原始像素测量。",
            "单张 LDR 截图不能恢复真实曝光、Lux、材质参数或 UE 灯光 Actor。",
        ],
        "three_value_thresholds": [
            _rounded(low_threshold),
            _rounded(high_threshold),
        ],
        "reference": reference,
        "current": current,
        "current_minus_reference": deltas,
        "spatial_cell_differences": _spatial_differences(
            reference["spatial_grid"],
            current["spatial_grid"],
        ),
    }


def _image_digest(
    rgb: UInt8Image,
    *,
    low_threshold: float,
    high_threshold: float,
    measurement: ImageMeasurements | None,
    maximum_side: int,
) -> dict[str, Any]:
    sample = _bounded_sample(rgb, maximum_side)
    luminance = display_luminance(sample)
    hsv = cv2.cvtColor(sample, cv2.COLOR_RGB2HSV)
    saturation = hsv[..., 1].astype(np.float32) / 255.0
    dark = luminance < low_threshold
    bright = luminance >= high_threshold
    middle = ~(dark | bright)
    p10, p50, p90 = np.percentile(luminance, (10.0, 50.0, 90.0))
    palette_l, palette_c, neutral = _palette_summary(measurement)
    return {
        "source_dimensions": [int(rgb.shape[1]), int(rgb.shape[0])],
        "sample_dimensions": [int(sample.shape[1]), int(sample.shape[0])],
        "mean_luminance": _rounded(float(np.mean(luminance))),
        "luminance_std": _rounded(float(np.std(luminance))),
        "p10_luminance": _rounded(float(p10)),
        "p50_luminance": _rounded(float(p50)),
        "p90_luminance": _rounded(float(p90)),
        "effective_luminance_span": _rounded(float(p90 - p10)),
        "dark_ratio": _rounded(float(np.mean(dark))),
        "midtone_ratio": _rounded(float(np.mean(middle))),
        "bright_ratio": _rounded(float(np.mean(bright))),
        "shadow_clip_ratio": _rounded(float(np.mean(luminance <= 0.02))),
        "highlight_clip_ratio": _rounded(float(np.mean(luminance >= 0.98))),
        "mean_saturation": _rounded(float(np.mean(saturation))),
        "neutral_ratio": _rounded(neutral),
        "palette_mean_oklab_l": _rounded(palette_l),
        "palette_mean_chroma": _rounded(palette_c),
        "spatial_grid": _spatial_grid(luminance, saturation),
    }


def _bounded_sample(rgb: UInt8Image, maximum_side: int) -> UInt8Image:
    height, width = rgb.shape[:2]
    scale = min(1.0, maximum_side / float(max(height, width)))
    if scale >= 1.0:
        return np.ascontiguousarray(rgb)
    size = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    return np.ascontiguousarray(
        cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
    )


def _palette_summary(
    measurement: ImageMeasurements | None,
) -> tuple[float, float, float]:
    if measurement is None or not measurement.palette:
        return 0.0, 0.0, 0.0
    mean_l = 0.0
    mean_chroma = 0.0
    neutral = 0.0
    for colour in measurement.palette:
        l_value, a_value, b_value = colour.oklab
        chroma = float((a_value * a_value + b_value * b_value) ** 0.5)
        mean_l += float(l_value) * colour.proportion
        mean_chroma += chroma * colour.proportion
        if chroma < 0.04:
            neutral += colour.proportion
    return mean_l, mean_chroma, neutral


def _spatial_grid(
    luminance: np.ndarray,
    saturation: np.ndarray,
) -> list[dict[str, Any]]:
    height, width = luminance.shape
    result: list[dict[str, Any]] = []
    for row in range(3):
        y0 = int(round(row * height / 3.0))
        y1 = int(round((row + 1) * height / 3.0))
        for column in range(3):
            x0 = int(round(column * width / 3.0))
            x1 = int(round((column + 1) * width / 3.0))
            lum = luminance[y0:y1, x0:x1]
            sat = saturation[y0:y1, x0:x1]
            result.append(
                {
                    "cell_id": f"r{row + 1}c{column + 1}",
                    "normalized_rect": {
                        "x": column / 3.0,
                        "y": row / 3.0,
                        "width": 1.0 / 3.0,
                        "height": 1.0 / 3.0,
                    },
                    "mean_luminance": _rounded(float(np.mean(lum))),
                    "local_contrast": _rounded(float(np.std(lum))),
                    "mean_saturation": _rounded(float(np.mean(sat))),
                }
            )
    return result


def _spatial_differences(
    reference: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_by_id = {str(item["cell_id"]): item for item in current}
    result = []
    for reference_item in reference:
        cell_id = str(reference_item["cell_id"])
        current_item = current_by_id[cell_id]
        result.append(
            {
                "cell_id": cell_id,
                "current_minus_reference": {
                    key: _rounded(
                        float(current_item[key]) - float(reference_item[key])
                    )
                    for key in (
                        "mean_luminance",
                        "local_contrast",
                        "mean_saturation",
                    )
                },
            }
        )
    return result


def _rounded(value: float) -> float:
    return round(float(value), 6)
