from __future__ import annotations

from dataclasses import dataclass

from scenelens.modules.visual_review import MODULE_ID


MIN_REGION_NORMALIZED_SIZE = 0.002


@dataclass(frozen=True)
class NormalizedRect:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(float(value) == value for value in values):
            raise ValueError("normalized rectangle values must be numeric")
        if self.x < 0.0 or self.y < 0.0:
            raise ValueError("normalized rectangle origin must be inside 0..1")
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("normalized rectangle size must be positive")
        if self.x + self.width > 1.0 + 1e-9:
            raise ValueError("normalized rectangle exceeds image width")
        if self.y + self.height > 1.0 + 1e-9:
            raise ValueError("normalized rectangle exceeds image height")

    def to_dict(self) -> dict[str, float]:
        return {
            "x": float(self.x),
            "y": float(self.y),
            "width": float(self.width),
            "height": float(self.height),
        }

    def to_pixel_rect(
        self,
        image_width: int,
        image_height: int,
    ) -> tuple[float, float, float, float]:
        if image_width <= 0 or image_height <= 0:
            raise ValueError("image dimensions must be positive")
        return (
            self.x * image_width,
            self.y * image_height,
            self.width * image_width,
            self.height * image_height,
        )

    @classmethod
    def from_pixel_points(
        cls,
        first_x: float,
        first_y: float,
        second_x: float,
        second_y: float,
        image_width: int,
        image_height: int,
    ) -> NormalizedRect:
        if image_width <= 0 or image_height <= 0:
            raise ValueError("image dimensions must be positive")
        left = max(0.0, min(float(image_width), min(first_x, second_x)))
        top = max(0.0, min(float(image_height), min(first_y, second_y)))
        right = max(0.0, min(float(image_width), max(first_x, second_x)))
        bottom = max(0.0, min(float(image_height), max(first_y, second_y)))
        return cls(
            left / image_width,
            top / image_height,
            (right - left) / image_width,
            (bottom - top) / image_height,
        )


@dataclass(frozen=True)
class RegionRecord:
    id: str
    module_id: str
    shot_id: str
    image_role: str
    version_id: str | None
    name: str
    semantic_type: str
    normalized_rect: NormalizedRect
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RegionPairRecord:
    id: str
    shot_id: str
    reference_region_id: str
    current_region_id: str
    name: str
    semantic_type: str
    notes: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RegionPairView:
    pair: RegionPairRecord
    reference_region: RegionRecord
    current_region: RegionRecord
    analysis_status: str


def validate_region_size(rect: NormalizedRect) -> None:
    if (
        rect.width < MIN_REGION_NORMALIZED_SIZE
        or rect.height < MIN_REGION_NORMALIZED_SIZE
    ):
        raise ValueError("区域过小，请拖出更大的矩形。")


def module_id() -> str:
    return MODULE_ID
