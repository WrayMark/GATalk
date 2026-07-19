from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from scenelens.analysis.grading import SafeGradeRecipe, apply_safe_grade
from scenelens.storage.atomic import atomic_write_json


def write_grade_png(path: Path, rgb: np.ndarray) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(path, format="PNG")
    return path


def write_grade_recipe(path: Path, recipe: SafeGradeRecipe) -> Path:
    payload = {
        "format": "scenelens.safe_grade_recipe",
        "format_version": 1,
        "recipe": recipe.to_dict(),
    }
    atomic_write_json(Path(path), payload)
    return Path(path)


def cube_lut_text(
    recipe: SafeGradeRecipe,
    *,
    size: int = 17,
) -> str:
    if recipe.normalized_rect is not None:
        raise ValueError("区域调色不能导出为全局 .cube LUT")
    if recipe.reference_colour_transfer > 0.0:
        raise ValueError("参考色迁移依赖具体图片，不能导出通用 .cube LUT")
    if size < 2 or size > 65:
        raise ValueError("cube LUT size must be inside 2..65")
    levels = np.linspace(0, 255, size, dtype=np.uint8)
    samples = np.asarray(
        [
            (red, green, blue)
            for blue in levels
            for green in levels
            for red in levels
        ],
        dtype=np.uint8,
    ).reshape(-1, 1, 3)
    graded = apply_safe_grade(
        samples,
        replace(recipe, normalized_rect=None),
    ).reshape(-1, 3)
    lines = [
        'TITLE "SceneLens Safe Grade"',
        f"LUT_3D_SIZE {size}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ]
    lines.extend(
        f"{red / 255.0:.7f} {green / 255.0:.7f} {blue / 255.0:.7f}"
        for red, green, blue in graded
    )
    return "\n".join(lines) + "\n"


def write_cube_lut(
    path: Path,
    recipe: SafeGradeRecipe,
    *,
    size: int = 17,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cube_lut_text(recipe, size=size), encoding="ascii")
    return path
