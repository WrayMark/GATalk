from __future__ import annotations

from typing import Any

from scenelens.analysis.models import (
    LuminanceComparison,
    SharedPaletteColour,
    SharedPaletteResult,
)


def shared_palette_to_payload(result: SharedPaletteResult) -> dict[str, Any]:
    return {
        "colours": [
            {
                "rgb": list(item.rgb),
                "oklab": [float(value) for value in item.oklab],
                "reference_proportion": float(item.reference_proportion),
                "current_proportion": float(item.current_proportion),
            }
            for item in result.colours
        ],
        "reference_sample_count": result.reference_sample_count,
        "current_sample_count": result.current_sample_count,
    }


def shared_palette_from_payload(payload: dict[str, Any]) -> SharedPaletteResult:
    return SharedPaletteResult(
        colours=tuple(
            SharedPaletteColour(
                rgb=tuple(int(value) for value in item["rgb"]),
                oklab=tuple(float(value) for value in item["oklab"]),
                reference_proportion=float(item["reference_proportion"]),
                current_proportion=float(item["current_proportion"]),
            )
            for item in payload["colours"]
        ),
        reference_sample_count=int(payload["reference_sample_count"]),
        current_sample_count=int(payload["current_sample_count"]),
    )


def luminance_comparison_to_payload(
    result: LuminanceComparison,
) -> dict[str, Any]:
    return {
        "low_threshold": result.low_threshold,
        "high_threshold": result.high_threshold,
        "reference_ratios": list(result.reference_ratios),
        "current_ratios": list(result.current_ratios),
    }


def luminance_comparison_from_payload(
    payload: dict[str, Any],
) -> LuminanceComparison:
    return LuminanceComparison(
        low_threshold=float(payload["low_threshold"]),
        high_threshold=float(payload["high_threshold"]),
        reference_ratios=tuple(
            float(value) for value in payload["reference_ratios"]
        ),
        current_ratios=tuple(
            float(value) for value in payload["current_ratios"]
        ),
    )
