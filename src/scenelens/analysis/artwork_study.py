from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from scenelens.analysis.distributions import (
    hue_saturation_distribution,
    value_band_ratios,
)
from scenelens.analysis.luminance import relative_luminance
from scenelens.analysis.models import ImageMeasurements, UInt8Image
from scenelens.analysis.palette import rgb_to_oklab


ANALYZER_ID = "single_image_formal_evidence"
ANALYZER_VERSION = "1.0.0"
DEFAULT_GRID_SIZE = 3
DEFAULT_MAXIMUM_SIDE = 1024
DEFAULT_NEUTRAL_CHROMA_THRESHOLD = 0.03


@dataclass(frozen=True)
class SpatialCellEvidence:
    row: int
    column: int
    normalized_rect: tuple[float, float, float, float]
    mean_linear_luminance: float
    luminance_contrast: float
    edge_density: float
    mean_saturation: float
    mean_oklab_chroma: float
    warmth_oklab_b: float
    attention_proxy: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "column": self.column,
            "normalized_rect": list(self.normalized_rect),
            "mean_linear_luminance": self.mean_linear_luminance,
            "luminance_contrast": self.luminance_contrast,
            "edge_density": self.edge_density,
            "mean_saturation": self.mean_saturation,
            "mean_oklab_chroma": self.mean_oklab_chroma,
            "warmth_oklab_b": self.warmth_oklab_b,
            "attention_proxy": self.attention_proxy,
        }


@dataclass(frozen=True)
class ArtworkLocalAnalysis:
    analyzer_id: str
    analyzer_version: str
    parameters: dict[str, Any]
    image_size: tuple[int, int]
    value_structure: dict[str, Any]
    colour_structure: dict[str, Any]
    spatial_cells: tuple[SpatialCellEvidence, ...]
    structure: dict[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzer_id": self.analyzer_id,
            "analyzer_version": self.analyzer_version,
            "parameters": dict(self.parameters),
            "image_size": list(self.image_size),
            "value_structure": dict(self.value_structure),
            "colour_structure": dict(self.colour_structure),
            "spatial_cells": [item.to_dict() for item in self.spatial_cells],
            "structure": dict(self.structure),
            "limitations": list(self.limitations),
        }


def analyze_artwork(
    rgb: UInt8Image,
    measurements: ImageMeasurements,
    *,
    grid_size: int = DEFAULT_GRID_SIZE,
    maximum_side: int = DEFAULT_MAXIMUM_SIDE,
    neutral_chroma_threshold: float = DEFAULT_NEUTRAL_CHROMA_THRESHOLD,
) -> ArtworkLocalAnalysis:
    _validate_rgb(rgb)
    if grid_size < 2 or grid_size > 8:
        raise ValueError("grid_size must stay between 2 and 8")
    if maximum_side < 128:
        raise ValueError("maximum_side must be at least 128")
    if neutral_chroma_threshold < 0.0:
        raise ValueError("neutral_chroma_threshold must not be negative")

    sampled = _bounded_resize(rgb, maximum_side)
    linear = relative_luminance(sampled)
    p10, p50, p90 = np.percentile(linear, (10.0, 50.0, 90.0))
    value_three = value_band_ratios(sampled, (1.0 / 3.0, 2.0 / 3.0))
    value_five = value_band_ratios(sampled, (0.2, 0.4, 0.6, 0.8))

    distribution = hue_saturation_distribution(sampled)
    pixels = np.ascontiguousarray(sampled.reshape(-1, 3))
    oklab = rgb_to_oklab(pixels.astype(np.float64) / 255.0)
    chroma = np.hypot(oklab[:, 1], oklab[:, 2])
    neutral_ratio = float(np.mean(chroma < neutral_chroma_threshold))

    raw_cells = _spatial_evidence(sampled, grid_size)
    proxy_values = _attention_proxy(raw_cells)
    cells = tuple(
        SpatialCellEvidence(
            row=item["row"],
            column=item["column"],
            normalized_rect=item["normalized_rect"],
            mean_linear_luminance=item["mean_linear_luminance"],
            luminance_contrast=item["luminance_contrast"],
            edge_density=item["edge_density"],
            mean_saturation=item["mean_saturation"],
            mean_oklab_chroma=item["mean_oklab_chroma"],
            warmth_oklab_b=item["warmth_oklab_b"],
            attention_proxy=float(proxy_values[index]),
        )
        for index, item in enumerate(raw_cells)
    )

    gray = cv2.cvtColor(sampled, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    upper = edges[: max(1, edges.shape[0] // 2)]
    lower = edges[edges.shape[0] // 2 :]
    return ArtworkLocalAnalysis(
        analyzer_id=ANALYZER_ID,
        analyzer_version=ANALYZER_VERSION,
        parameters={
            "grid_size": grid_size,
            "maximum_side": maximum_side,
            "neutral_chroma_threshold": neutral_chroma_threshold,
            "three_value_thresholds": [1.0 / 3.0, 2.0 / 3.0],
            "five_value_thresholds": [0.2, 0.4, 0.6, 0.8],
            "edge_method": "Canny(80,160)",
            "attention_proxy_features": [
                "luminance_contrast",
                "edge_density",
                "oklab_chroma",
            ],
        },
        image_size=(int(rgb.shape[1]), int(rgb.shape[0])),
        value_structure={
            "mean_linear_luminance": float(np.mean(linear)),
            "luminance_standard_deviation": float(np.std(linear)),
            "p10": float(p10),
            "p50": float(p50),
            "p90": float(p90),
            "effective_span_p10_p90": float(p90 - p10),
            "three_value_ratios": list(value_three),
            "five_value_ratios": list(value_five),
        },
        colour_structure={
            "palette": [
                {
                    "hex": item.hex_colour,
                    "rgb": list(item.rgb),
                    "oklab": list(item.oklab),
                    "proportion": item.proportion,
                }
                for item in measurements.palette
            ],
            "mean_saturation": float(distribution["mean_saturation"]),
            "neutral_ratio": neutral_ratio,
            "hue_proportions": list(distribution["hue_proportions"]),
            "hue_bin_count": int(distribution["hue_bins_degrees"]),
        },
        spatial_cells=cells,
        structure={
            "global_edge_density": float(np.mean(edges > 0)),
            "upper_edge_density": float(np.mean(upper > 0)),
            "lower_edge_density": float(np.mean(lower > 0)),
            "detail_vertical_bias": float(
                np.mean(lower > 0) - np.mean(upper > 0)
            ),
        },
        limitations=(
            "注意力代理只综合局部反差、边缘密度和彩度，不等同于眼动或语义显著性。",
            "单张成图无法可靠还原真实灯光参数、材质节点、镜头焦距或制作流程。",
            "空间网格用于提供可复核位置证据，不替代主美的整体视觉判断。",
        ),
    )


def format_local_analysis_summary(
    analysis: ArtworkLocalAnalysis,
) -> str:
    value = analysis.value_structure
    colour = analysis.colour_structure
    cells = sorted(
        analysis.spatial_cells,
        key=lambda item: item.attention_proxy,
        reverse=True,
    )
    top = "、".join(
        f"{item.row + 1}-{item.column + 1}"
        for item in cells[:3]
    )
    three = value["three_value_ratios"]
    return (
        "测量结果\n"
        f"平均线性明度 {value['mean_linear_luminance']:.3f}；"
        f"P10/P50/P90 = {value['p10']:.3f}/"
        f"{value['p50']:.3f}/{value['p90']:.3f}。\n"
        f"三阶明度：暗 {three[0] * 100:.1f}% / "
        f"中 {three[1] * 100:.1f}% / 亮 {three[2] * 100:.1f}%。\n"
        f"平均饱和度 {colour['mean_saturation']:.3f}；"
        f"低彩度比例 {colour['neutral_ratio'] * 100:.1f}%。\n"
        f"全图边缘密度 {analysis.structure['global_edge_density']:.3f}。\n\n"
        "算法推断\n"
        f"九宫格注意力代理较高的位置：{top}。"
        "此结果不等同于真实视觉焦点，需结合题材、尺度和叙事人工判断。"
    )


def _spatial_evidence(
    rgb: UInt8Image,
    grid_size: int,
) -> list[dict[str, Any]]:
    height, width = rgb.shape[:2]
    cells: list[dict[str, Any]] = []
    for row in range(grid_size):
        top = round(row * height / grid_size)
        bottom = round((row + 1) * height / grid_size)
        for column in range(grid_size):
            left = round(column * width / grid_size)
            right = round((column + 1) * width / grid_size)
            crop = np.ascontiguousarray(rgb[top:bottom, left:right])
            linear = relative_luminance(crop)
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 80, 160)
            hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
            sample = crop.reshape(-1, 3).astype(np.float64) / 255.0
            oklab = rgb_to_oklab(sample)
            chroma = np.hypot(oklab[:, 1], oklab[:, 2])
            cells.append(
                {
                    "row": row,
                    "column": column,
                    "normalized_rect": (
                        column / grid_size,
                        row / grid_size,
                        1.0 / grid_size,
                        1.0 / grid_size,
                    ),
                    "mean_linear_luminance": float(np.mean(linear)),
                    "luminance_contrast": float(np.std(linear)),
                    "edge_density": float(np.mean(edges > 0)),
                    "mean_saturation": float(
                        np.mean(hsv[..., 1].astype(np.float32) / 255.0)
                    ),
                    "mean_oklab_chroma": float(np.mean(chroma)),
                    "warmth_oklab_b": float(np.mean(oklab[:, 2])),
                }
            )
    return cells


def _attention_proxy(cells: list[dict[str, Any]]) -> np.ndarray:
    values = np.asarray(
        [
            [
                item["luminance_contrast"],
                item["edge_density"],
                item["mean_oklab_chroma"],
            ]
            for item in cells
        ],
        dtype=np.float64,
    )
    minimum = np.min(values, axis=0)
    span = np.ptp(values, axis=0)
    normalized = np.divide(
        values - minimum,
        span,
        out=np.zeros_like(values),
        where=span > 1e-12,
    )
    score = (
        normalized[:, 0] * 0.45
        + normalized[:, 1] * 0.35
        + normalized[:, 2] * 0.20
    )
    maximum = float(np.max(score))
    return score if maximum <= 1e-12 else score / maximum


def _bounded_resize(rgb: UInt8Image, maximum_side: int) -> UInt8Image:
    height, width = rgb.shape[:2]
    if max(width, height) <= maximum_side:
        return np.ascontiguousarray(rgb)
    scale = maximum_side / float(max(width, height))
    resized = cv2.resize(
        rgb,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return np.ascontiguousarray(resized)


def _validate_rgb(rgb: UInt8Image) -> None:
    if (
        rgb.dtype != np.uint8
        or rgb.ndim != 3
        or rgb.shape[2] != 3
        or rgb.shape[0] < 1
        or rgb.shape[1] < 1
    ):
        raise ValueError("rgb must be a non-empty uint8 RGB image")
