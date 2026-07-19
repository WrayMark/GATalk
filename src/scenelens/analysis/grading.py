from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

import cv2
import numpy as np

from scenelens.analysis.luminance import (
    linear_to_srgb,
    srgb_to_linear,
)
from scenelens.analysis.models import UInt8Image
from scenelens.analysis.palette import oklab_to_rgb, rgb_to_oklab


@dataclass(frozen=True)
class SafeGradeRecipe:
    exposure_stops: float = 0.0
    contrast: float = 0.0
    temperature: float = 0.0
    tint: float = 0.0
    shadows: float = 0.0
    midtones: float = 0.0
    highlights: float = 0.0
    saturation: float = 0.0
    reference_colour_transfer: float = 0.0
    strength_percent: int = 100
    normalized_rect: tuple[float, float, float, float] | None = None

    def validate(self) -> None:
        if not -4.0 <= self.exposure_stops <= 4.0:
            raise ValueError("exposure_stops must be inside -4..4")
        for key in (
            "contrast",
            "temperature",
            "tint",
            "shadows",
            "midtones",
            "highlights",
            "saturation",
        ):
            if not -1.0 <= float(getattr(self, key)) <= 1.0:
                raise ValueError(f"{key} must be inside -1..1")
        if not 0.0 <= self.reference_colour_transfer <= 1.0:
            raise ValueError(
                "reference_colour_transfer must be inside 0..1"
            )
        if not 0 <= self.strength_percent <= 100:
            raise ValueError("strength_percent must be inside 0..100")
        if self.normalized_rect is not None:
            x, y, width, height = self.normalized_rect
            if (
                x < 0.0
                or y < 0.0
                or width <= 0.0
                or height <= 0.0
                or x + width > 1.0 + 1e-9
                or y + height > 1.0 + 1e-9
            ):
                raise ValueError("normalized_rect must be inside 0..1")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if self.normalized_rect is not None:
            value["normalized_rect"] = list(self.normalized_rect)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SafeGradeRecipe:
        fields = dict(value)
        rect = fields.get("normalized_rect")
        if rect is not None:
            fields["normalized_rect"] = tuple(float(item) for item in rect)
        recipe = cls(**fields)
        recipe.validate()
        return recipe


class RecipeHistory:
    def __init__(self, initial: SafeGradeRecipe | None = None) -> None:
        self._items = [initial or SafeGradeRecipe()]
        self._index = 0

    @property
    def current(self) -> SafeGradeRecipe:
        return self._items[self._index]

    def push(self, recipe: SafeGradeRecipe) -> None:
        recipe.validate()
        del self._items[self._index + 1 :]
        self._items.append(recipe)
        self._index += 1

    def undo(self) -> SafeGradeRecipe:
        if self._index > 0:
            self._index -= 1
        return self.current

    def redo(self) -> SafeGradeRecipe:
        if self._index + 1 < len(self._items):
            self._index += 1
        return self.current


def apply_safe_grade(
    rgb: UInt8Image,
    recipe: SafeGradeRecipe,
    *,
    reference_rgb: UInt8Image | None = None,
) -> UInt8Image:
    recipe.validate()
    _validate_rgb(rgb)
    if recipe.reference_colour_transfer > 0.0 and reference_rgb is None:
        raise ValueError("reference colour transfer requires reference_rgb")
    original = srgb_to_linear(rgb.astype(np.float32) / 255.0)
    target = original.copy()
    target *= float(2.0**recipe.exposure_stops)

    temperature = recipe.temperature
    tint = recipe.tint
    multipliers = np.asarray(
        [
            1.0 + 0.22 * temperature + 0.08 * tint,
            1.0 - 0.12 * tint,
            1.0 - 0.22 * temperature + 0.08 * tint,
        ],
        dtype=np.float32,
    )
    target *= multipliers
    target = (target - 0.18) * (1.0 + recipe.contrast) + 0.18
    luminance = np.clip(
        target[..., 0] * 0.2126
        + target[..., 1] * 0.7152
        + target[..., 2] * 0.0722,
        0.0,
        1.0,
    )
    shadow_weight = np.square(1.0 - luminance)
    highlight_weight = np.square(luminance)
    midtone_weight = np.clip(1.0 - np.abs(luminance * 2.0 - 1.0), 0, 1)
    tone_delta = (
        recipe.shadows * shadow_weight
        + recipe.midtones * midtone_weight
        + recipe.highlights * highlight_weight
    ) * 0.25
    target += tone_delta[..., None]
    luminance_rgb = (
        target[..., 0] * 0.2126
        + target[..., 1] * 0.7152
        + target[..., 2] * 0.0722
    )[..., None]
    target = luminance_rgb + (
        target - luminance_rgb
    ) * (1.0 + recipe.saturation)
    target = np.clip(target, 0.0, 1.0)

    if recipe.reference_colour_transfer > 0.0:
        target_srgb = linear_to_srgb(target)
        transferred = _limited_oklab_transfer(
            target_srgb,
            reference_rgb,
            recipe.reference_colour_transfer,
        )
        target = srgb_to_linear(transferred)

    strength = recipe.strength_percent / 100.0
    graded = original * (1.0 - strength) + target * strength
    if recipe.normalized_rect is not None:
        mask = _rect_mask(rgb.shape[:2], recipe.normalized_rect)
        graded = np.where(mask[..., None], graded, original)
    result = np.rint(linear_to_srgb(graded) * 255.0).astype(np.uint8)
    return np.ascontiguousarray(result)


def preview_ladder(
    rgb: UInt8Image,
    recipe: SafeGradeRecipe,
    strengths: tuple[int, ...] = (5, 10, 15, 25, 50, 75, 100),
    *,
    reference_rgb: UInt8Image | None = None,
) -> tuple[tuple[int, UInt8Image], ...]:
    return tuple(
        (
            strength,
            apply_safe_grade(
                rgb,
                replace(recipe, strength_percent=strength),
                reference_rgb=reference_rgb,
            ),
        )
        for strength in strengths
    )


def _limited_oklab_transfer(
    current_srgb: np.ndarray,
    reference_rgb: UInt8Image,
    amount: float,
) -> np.ndarray:
    current_stats = _sample_oklab(
        np.rint(current_srgb * 255.0).astype(np.uint8)
    )
    reference_stats = _sample_oklab(reference_rgb)
    delta = np.clip(
        reference_stats - current_stats,
        np.asarray([-0.08, -0.08, -0.08]),
        np.asarray([0.08, 0.08, 0.08]),
    )
    output = np.empty_like(current_srgb, dtype=np.float64)
    for top in range(0, current_srgb.shape[0], 256):
        bottom = min(current_srgb.shape[0], top + 256)
        strip = current_srgb[top:bottom].reshape(-1, 3)
        oklab = rgb_to_oklab(strip)
        oklab += delta * amount
        output[top:bottom] = oklab_to_rgb(oklab).reshape(
            bottom - top,
            current_srgb.shape[1],
            3,
        )
    return np.clip(output, 0.0, 1.0).astype(np.float32)


def _sample_oklab(rgb: UInt8Image) -> np.ndarray:
    height, width = rgb.shape[:2]
    maximum = 60_000
    sampled = rgb
    if height * width > maximum:
        scale = (maximum / float(height * width)) ** 0.5
        sampled = cv2.resize(
            rgb,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return np.mean(
        rgb_to_oklab(
            sampled.reshape(-1, 3).astype(np.float64) / 255.0
        ),
        axis=0,
    )


def _rect_mask(
    shape: tuple[int, int],
    rect: tuple[float, float, float, float],
) -> np.ndarray:
    height, width = shape
    x, y, rect_width, rect_height = rect
    left = max(0, min(width - 1, int(np.floor(x * width))))
    top = max(0, min(height - 1, int(np.floor(y * height))))
    right = max(left + 1, min(width, int(np.ceil((x + rect_width) * width))))
    bottom = max(
        top + 1,
        min(height, int(np.ceil((y + rect_height) * height))),
    )
    mask = np.zeros((height, width), dtype=bool)
    mask[top:bottom, left:right] = True
    return mask


def _validate_rgb(rgb: UInt8Image) -> None:
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be uint8 with shape (height, width, 3)")
