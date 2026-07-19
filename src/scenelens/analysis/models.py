from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


UInt8Image = NDArray[np.uint8]
FloatArray = NDArray[np.floating]


@dataclass(frozen=True)
class PaletteColour:
    rgb: tuple[int, int, int]
    oklab: tuple[float, float, float]
    proportion: float

    @property
    def hex_colour(self) -> str:
        return "#{:02X}{:02X}{:02X}".format(*self.rgb)


@dataclass(frozen=True)
class ImageMeasurements:
    luminance_histogram: NDArray[np.float64]
    palette: tuple[PaletteColour, ...]
    sampled_pixel_count: int


@dataclass(frozen=True)
class SharedPaletteColour:
    rgb: tuple[int, int, int]
    oklab: tuple[float, float, float]
    reference_proportion: float
    current_proportion: float

    @property
    def hex_colour(self) -> str:
        return "#{:02X}{:02X}{:02X}".format(*self.rgb)

    @property
    def proportion_difference(self) -> float:
        return self.current_proportion - self.reference_proportion


@dataclass(frozen=True)
class SharedPaletteResult:
    colours: tuple[SharedPaletteColour, ...]
    reference_sample_count: int
    current_sample_count: int


@dataclass(frozen=True)
class LuminanceComparison:
    low_threshold: float
    high_threshold: float
    reference_ratios: tuple[float, float, float]
    current_ratios: tuple[float, float, float]


@dataclass(frozen=True)
class RenderSettings:
    mode: str = "original"
    blur_sigma: float = 0.0
    three_thresholds: tuple[float, float] = (1.0 / 3.0, 2.0 / 3.0)
    five_thresholds: tuple[float, float, float, float] = (0.2, 0.4, 0.6, 0.8)
