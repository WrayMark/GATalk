from __future__ import annotations

from typing import Any

from scenelens.analysis.distributions import (
    hue_saturation_distribution,
    value_band_ratios,
)
from scenelens.analysis.luminance import three_value_ratios
from scenelens.analysis.models import ImageMeasurements
from scenelens.imaging.loader import LoadedImage
from scenelens.storage.models import (
    BriefFieldValue,
    FieldSource,
    ImageAssetRecord,
)


def build_reference_measurement_fields(
    image: LoadedImage,
    asset: ImageAssetRecord,
    measurements: ImageMeasurements,
    *,
    three_thresholds: tuple[float, float],
    five_thresholds: tuple[float, float, float, float],
    analyzer_id: str,
    analyzer_version: str,
    palette_seed: int,
    palette_max_samples: int,
) -> dict[str, BriefFieldValue]:
    evidence: dict[str, Any] = {
        "asset_sha256": asset.sha256,
        "analyzer_id": analyzer_id,
        "analyzer_version": analyzer_version,
    }
    distribution = hue_saturation_distribution(image.rgb)
    palette = [
        {
            "hex": item.hex_colour,
            "rgb": list(item.rgb),
            "oklab": [float(value) for value in item.oklab],
            "proportion": float(item.proportion),
        }
        for item in measurements.palette
    ]
    measurement = FieldSource.AUTOMATIC_MEASUREMENT
    inference = FieldSource.ALGORITHM_INFERENCE
    base = dict(confidence=None, evidence=evidence, user_confirmed=False)
    return {
        "image_dimensions": BriefFieldValue(
            value={
                "width": image.working_size[0],
                "height": image.working_size[1],
            },
            source=measurement,
            **base,
        ),
        "aspect_ratio": BriefFieldValue(
            value=float(image.working_size[0] / image.working_size[1]),
            source=measurement,
            **base,
        ),
        "source_format": BriefFieldValue(
            value=image.source_format,
            source=measurement,
            **base,
        ),
        "icc_status": BriefFieldValue(
            value=asset.icc_status,
            source=measurement,
            **base,
        ),
        "oklab_palette": BriefFieldValue(
            value=palette,
            source=inference,
            evidence={
                **evidence,
                "random_seed": int(palette_seed),
                "max_samples": int(palette_max_samples),
                "sampled_pixel_count": measurements.sampled_pixel_count,
            },
        ),
        "luminance_histogram": BriefFieldValue(
            value=[
                float(value) for value in measurements.luminance_histogram
            ],
            source=measurement,
            **base,
        ),
        "three_value_ratios": BriefFieldValue(
            value=list(
                three_value_ratios(
                    image.rgb,
                    three_thresholds[0],
                    three_thresholds[1],
                )
            ),
            source=measurement,
            evidence={
                **evidence,
                "thresholds": list(three_thresholds),
            },
        ),
        "five_value_ratios": BriefFieldValue(
            value=list(value_band_ratios(image.rgb, five_thresholds)),
            source=measurement,
            evidence={
                **evidence,
                "thresholds": list(five_thresholds),
            },
        ),
        "hue_distribution": BriefFieldValue(
            value={
                "bins_degrees": distribution["hue_bins_degrees"],
                "proportions": distribution["hue_proportions"],
            },
            source=measurement,
            **base,
        ),
        "saturation_distribution": BriefFieldValue(
            value={
                "bins": distribution["saturation_bins"],
                "proportions": distribution["saturation_proportions"],
                "mean": distribution["mean_saturation"],
            },
            source=measurement,
            **base,
        ),
    }
