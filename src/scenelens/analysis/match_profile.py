from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import cv2
import numpy as np

from scenelens.analysis.luminance import (
    display_luminance,
    three_value_ratios,
)
from scenelens.analysis.models import SharedPaletteResult, UInt8Image
from scenelens.analysis.palette import rgb_to_oklab
from scenelens.analysis.region_analysis import PairedRegionAnalysis


DEFAULT_MATCH_WEIGHTS: dict[str, float] = {
    "luminance_structure": 1.0,
    "three_value_balance": 1.0,
    "palette_area": 1.0,
    "chroma_neutral": 0.8,
    "warm_cool": 0.8,
    "region_relationships": 1.2,
    "local_contrast": 0.8,
    "visual_focus": 1.0,
    "lighting_atmosphere": 0.8,
    "spatial_depth": 0.8,
}


@dataclass(frozen=True)
class MatchDimension:
    dimension_id: str
    display_name: str
    similarity: float | None
    evidence_type: str
    explanation: str


@dataclass(frozen=True)
class MatchProfile:
    dimensions: tuple[MatchDimension, ...]
    weights: Mapping[str, float]
    estimated_match: float | None
    evidence_coverage: float


def build_match_profile(
    reference_rgb: UInt8Image,
    current_rgb: UInt8Image,
    *,
    shared_palette: SharedPaletteResult | None = None,
    paired_regions: Sequence[PairedRegionAnalysis] = (),
    weights: Mapping[str, float] | None = None,
) -> MatchProfile:
    configured = dict(DEFAULT_MATCH_WEIGHTS)
    if weights is not None:
        for key, value in weights.items():
            if key in configured:
                if float(value) < 0.0:
                    raise ValueError("match weights must not be negative")
                configured[key] = float(value)

    reference_luminance = display_luminance(reference_rgb)
    current_luminance = display_luminance(current_rgb)
    histogram_similarity = _histogram_similarity(
        reference_luminance,
        current_luminance,
    )
    reference_three = three_value_ratios(reference_rgb)
    current_three = three_value_ratios(current_rgb)
    three_similarity = _distribution_similarity(
        reference_three,
        current_three,
    )
    palette_similarity = None
    if shared_palette is not None and shared_palette.colours:
        palette_similarity = _distribution_similarity(
            [
                item.reference_proportion
                for item in shared_palette.colours
            ],
            [item.current_proportion for item in shared_palette.colours],
        )

    reference_colour = _colour_relationships(reference_rgb)
    current_colour = _colour_relationships(current_rgb)
    chroma_similarity = 1.0 - min(
        1.0,
        (
            abs(reference_colour[0] - current_colour[0]) / 0.2
            + abs(reference_colour[1] - current_colour[1])
        )
        / 2.0,
    )
    warm_similarity = 1.0 - min(
        1.0,
        abs(reference_colour[2] - current_colour[2]),
    )
    contrast_similarity = 1.0 - min(
        1.0,
        abs(
            float(np.std(reference_luminance))
            - float(np.std(current_luminance))
        )
        / 0.35,
    )
    region_similarity = _region_similarity(paired_regions)

    dimensions = (
        MatchDimension(
            "luminance_structure",
            "明度结构",
            histogram_similarity,
            "measurement",
            "比较显示明度直方图的分布距离。",
        ),
        MatchDimension(
            "three_value_balance",
            "黑白灰比例",
            three_similarity,
            "measurement",
            "比较当前三阶阈值下的暗部、中间调和亮部比例。",
        ),
        MatchDimension(
            "palette_area",
            "色板和面积关系",
            palette_similarity,
            "algorithm_inference",
            (
                "复用全图共享 Oklab 聚类中心比较双方面积组成。"
                if palette_similarity is not None
                else "尚无共享色板证据。"
            ),
        ),
        MatchDimension(
            "chroma_neutral",
            "彩度与中性色",
            chroma_similarity,
            "algorithm_inference",
            "比较有界采样的平均 Oklab 彩度和中性色比例。",
        ),
        MatchDimension(
            "warm_cool",
            "冷暖关系",
            warm_similarity,
            "algorithm_inference",
            "比较低彩度过滤后的暖色像素比例。",
        ),
        MatchDimension(
            "region_relationships",
            "区域关系",
            region_similarity,
            "algorithm_inference",
            (
                "汇总已配对区域的明度、彩度和三阶比例关系。"
                if region_similarity is not None
                else "尚无可用的成对区域分析。"
            ),
        ),
        MatchDimension(
            "local_contrast",
            "局部对比",
            contrast_similarity,
            "measurement",
            "比较双方全图显示明度标准差；不等同于美术好坏。",
        ),
        MatchDimension(
            "visual_focus",
            "视觉焦点",
            None,
            "art_judgment",
            "需要用户确认焦点区域或 AI 证据，当前不猜测。",
        ),
        MatchDimension(
            "lighting_atmosphere",
            "灯光氛围",
            None,
            "art_judgment",
            "仅凭全图统计不足以确认灯光氛围是否匹配。",
        ),
        MatchDimension(
            "spatial_depth",
            "空间层次",
            None,
            "art_judgment",
            "需要前中远景区域或深度证据，当前不自动断言。",
        ),
    )
    available_weight = sum(
        configured[item.dimension_id]
        for item in dimensions
        if item.similarity is not None
    )
    total_weight = sum(configured.values())
    estimated = None
    if available_weight > 0.0:
        estimated = sum(
            configured[item.dimension_id] * float(item.similarity)
            for item in dimensions
            if item.similarity is not None
        ) / available_weight
    coverage = (
        0.0 if total_weight == 0.0 else available_weight / total_weight
    )
    return MatchProfile(
        dimensions=dimensions,
        weights=configured,
        estimated_match=estimated,
        evidence_coverage=coverage,
    )


def _histogram_similarity(
    reference: np.ndarray,
    current: np.ndarray,
) -> float:
    reference_hist, _ = np.histogram(
        reference, bins=64, range=(0.0, 1.0)
    )
    current_hist, _ = np.histogram(
        current, bins=64, range=(0.0, 1.0)
    )
    return _distribution_similarity(reference_hist, current_hist)


def _distribution_similarity(
    reference: Sequence[float] | np.ndarray,
    current: Sequence[float] | np.ndarray,
) -> float:
    left = np.asarray(reference, dtype=np.float64)
    right = np.asarray(current, dtype=np.float64)
    if left.shape != right.shape or left.size == 0:
        raise ValueError("distributions must have the same non-empty shape")
    left_total = float(left.sum())
    right_total = float(right.sum())
    if left_total <= 0.0 or right_total <= 0.0:
        return 0.0
    left /= left_total
    right /= right_total
    return float(np.clip(1.0 - 0.5 * np.abs(left - right).sum(), 0.0, 1.0))


def _colour_relationships(rgb: UInt8Image) -> tuple[float, float, float]:
    height, width = rgb.shape[:2]
    maximum = 60_000
    if height * width > maximum:
        scale = (maximum / float(height * width)) ** 0.5
        rgb = cv2.resize(
            rgb,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    oklab = rgb_to_oklab(
        rgb.reshape(-1, 3).astype(np.float64) / 255.0
    )
    chroma = np.hypot(oklab[:, 1], oklab[:, 2])
    neutral = chroma < 0.03
    chromatic = ~neutral
    warm_ratio = (
        0.5
        if not np.any(chromatic)
        else float(np.mean(oklab[chromatic, 2] > 0.0))
    )
    return float(np.mean(chroma)), float(np.mean(neutral)), warm_ratio


def _region_similarity(
    regions: Sequence[PairedRegionAnalysis],
) -> float | None:
    if not regions:
        return None
    scores = []
    for analysis in regions:
        luminance = 1.0 - min(
            1.0,
            abs(
                analysis.reference.mean_linear_luminance
                - analysis.current.mean_linear_luminance
            )
            / 0.5,
        )
        chroma = 1.0 - min(
            1.0,
            abs(
                analysis.reference.mean_chroma
                - analysis.current.mean_chroma
            )
            / 0.2,
        )
        ratios = _distribution_similarity(
            analysis.reference.three_value_ratios,
            analysis.current.three_value_ratios,
        )
        scores.append((luminance + chroma + ratios) / 3.0)
    return float(np.mean(scores))
