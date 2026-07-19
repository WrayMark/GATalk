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
class RenderSettings:
    mode: str = "original"
    blur_sigma: float = 0.0

