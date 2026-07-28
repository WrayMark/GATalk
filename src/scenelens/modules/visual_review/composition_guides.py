from __future__ import annotations

from dataclasses import dataclass


NormalizedPoint = tuple[float, float]
NormalizedLine = tuple[NormalizedPoint, NormalizedPoint]


@dataclass(frozen=True)
class CompositionGuide:
    guide_id: str
    display_name: str
    lines: tuple[NormalizedLine, ...]

    def __post_init__(self) -> None:
        if not self.guide_id or not self.display_name:
            raise ValueError("composition guide identity must not be empty")
        if not self.lines:
            raise ValueError("composition guide must contain at least one line")
        for line in self.lines:
            for x, y in line:
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise ValueError(
                        "composition guide points must stay inside 0..1"
                    )


_GOLDEN_NEAR = 0.381966
_GOLDEN_FAR = 0.618034


COMPOSITION_GUIDES: dict[str, CompositionGuide] = {
    "thirds": CompositionGuide(
        "thirds",
        "三分法（九宫格）",
        (
            ((1.0 / 3.0, 0.0), (1.0 / 3.0, 1.0)),
            ((2.0 / 3.0, 0.0), (2.0 / 3.0, 1.0)),
            ((0.0, 1.0 / 3.0), (1.0, 1.0 / 3.0)),
            ((0.0, 2.0 / 3.0), (1.0, 2.0 / 3.0)),
        ),
    ),
    "golden_ratio": CompositionGuide(
        "golden_ratio",
        "黄金分割",
        (
            ((_GOLDEN_NEAR, 0.0), (_GOLDEN_NEAR, 1.0)),
            ((_GOLDEN_FAR, 0.0), (_GOLDEN_FAR, 1.0)),
            ((0.0, _GOLDEN_NEAR), (1.0, _GOLDEN_NEAR)),
            ((0.0, _GOLDEN_FAR), (1.0, _GOLDEN_FAR)),
        ),
    ),
    "diagonals": CompositionGuide(
        "diagonals",
        "对角线",
        (
            ((0.0, 0.0), (1.0, 1.0)),
            ((1.0, 0.0), (0.0, 1.0)),
        ),
    ),
    "center": CompositionGuide(
        "center",
        "中心构图",
        (
            ((0.5, 0.0), (0.5, 1.0)),
            ((0.0, 0.5), (1.0, 0.5)),
        ),
    ),
    "triangle": CompositionGuide(
        "triangle",
        "三角形构图",
        (
            ((0.0, 1.0), (0.5, 0.08)),
            ((0.5, 0.08), (1.0, 1.0)),
            ((0.0, 1.0), (1.0, 1.0)),
        ),
    ),
    "one_point_perspective": CompositionGuide(
        "one_point_perspective",
        "单点透视",
        (
            ((0.0, 0.5), (1.0, 0.5)),
            ((0.0, 0.0), (0.5, 0.5)),
            ((1.0, 0.0), (0.5, 0.5)),
            ((0.0, 1.0), (0.5, 0.5)),
            ((1.0, 1.0), (0.5, 0.5)),
        ),
    ),
    "two_point_perspective": CompositionGuide(
        "two_point_perspective",
        "两点透视",
        (
            ((0.0, 0.45), (1.0, 0.45)),
            ((0.0, 0.45), (0.5, 0.05)),
            ((0.0, 0.45), (0.5, 0.95)),
            ((1.0, 0.45), (0.5, 0.05)),
            ((1.0, 0.45), (0.5, 0.95)),
        ),
    ),
}


def composition_guide(guide_id: str) -> CompositionGuide | None:
    if guide_id in {"", "none"}:
        return None
    try:
        return COMPOSITION_GUIDES[guide_id]
    except KeyError as exc:
        raise ValueError(f"unknown composition guide: {guide_id}") from exc
