from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from scenelens.analysis.asset_masks import (
    apply_transparent_mask,
    normalized_rect_to_pixels,
)
from scenelens.modules.asset_breakdown.models import AssetItem
from scenelens.storage.atomic import atomic_write_json


@dataclass(frozen=True)
class RenderedAssetBoardPage:
    title: str
    group_key: str
    asset_ids: tuple[str, ...]
    png_bytes: bytes


def png_bytes_from_rgba(rgba: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(np.ascontiguousarray(rgba), mode="RGBA").save(
        buffer,
        format="PNG",
    )
    return buffer.getvalue()


def asset_crop_png(
    rgb: np.ndarray,
    asset: AssetItem,
    mask: np.ndarray,
    *,
    padding_ratio: float = 0.08,
) -> bytes:
    left, top, width, height = normalized_rect_to_pixels(
        asset.normalized_rect,
        rgb.shape,
    )
    pad_x = int(round(width * padding_ratio))
    pad_y = int(round(height * padding_ratio))
    x0 = max(0, left - pad_x)
    y0 = max(0, top - pad_y)
    x1 = min(rgb.shape[1], left + width + pad_x)
    y1 = min(rgb.shape[0], top + height + pad_y)
    rgba = apply_transparent_mask(rgb, mask)[y0:y1, x0:x1]
    return png_bytes_from_rgba(rgba)


def make_asset_board(
    entries: Iterable[tuple[AssetItem, Path]],
    *,
    title: str,
    cell_size: tuple[int, int] = (420, 360),
) -> bytes:
    values = list(entries)
    if not values:
        raise ValueError("没有可加入资产展示板的图片。")
    columns = 3 if len(values) >= 3 else len(values)
    rows = (len(values) + columns - 1) // columns
    cell_width, cell_height = cell_size
    header_height = 70
    board = Image.new(
        "RGB",
        (cell_width * columns, header_height + cell_height * rows),
        (32, 33, 36),
    )
    draw = ImageDraw.Draw(board)
    font = _font(22)
    small = _font(16)
    draw.text((24, 20), title, fill=(235, 238, 242), font=font)
    for index, (asset, path) in enumerate(values):
        column = index % columns
        row = index // columns
        x = column * cell_width
        y = header_height + row * cell_height
        with Image.open(path) as source:
            image = source.convert("RGBA")
            image.thumbnail(
                (cell_width - 36, cell_height - 92),
                Image.Resampling.LANCZOS,
            )
            background = Image.new(
                "RGBA",
                (cell_width - 24, cell_height - 72),
                (46, 48, 52, 255),
            )
            position = (
                (background.width - image.width) // 2,
                (background.height - image.height) // 2,
            )
            background.alpha_composite(image, position)
            board.paste(background.convert("RGB"), (x + 12, y + 12))
        source_label = {
            "visible_evidence": "原画可见证据",
            "ai_inference": "AI 推断",
            "user_added": "用户补充",
            "ai_generated_completion": "AI 生成补全",
        }.get(asset.evidence_kind, asset.evidence_kind)
        draw.text(
            (x + 18, y + cell_height - 52),
            f"{index + 1:02d}  {asset.name}",
            fill=(242, 243, 245),
            font=small,
        )
        draw.text(
            (x + 18, y + cell_height - 28),
            f"{asset.category} · {source_label}",
            fill=(151, 192, 244),
            font=_font(13),
        )
    buffer = BytesIO()
    board.save(buffer, format="PNG")
    return buffer.getvalue()


def make_asset_board_pages(
    entries: Iterable[tuple[AssetItem, Path]],
    *,
    title: str,
    grouping_strategy: str = "asset_family",
    max_items_per_page: int = 9,
) -> tuple[RenderedAssetBoardPage, ...]:
    """Render deterministic, production-oriented board pages.

    Assets are grouped before pagination so a large scene is not forced into
    one unreadable sheet. The images remain concept artifacts, not 3D assets.
    """

    values = list(entries)
    if not values:
        raise ValueError("没有可加入资产展示板的图片。")
    limit = max(1, min(24, int(max_items_per_page)))
    groups: dict[str, list[tuple[AssetItem, Path]]] = {}
    order: list[str] = []
    for asset, path in values:
        key = _board_group_key(asset, grouping_strategy)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((asset, path))
    rendered = []
    for key in order:
        items = groups[key]
        chunks = [items[index : index + limit] for index in range(0, len(items), limit)]
        for chunk_index, chunk in enumerate(chunks, start=1):
            suffix = f" · {key}"
            if len(chunks) > 1:
                suffix += f" {chunk_index}/{len(chunks)}"
            page_title = f"{title}{suffix}"
            rendered.append(
                RenderedAssetBoardPage(
                    title=page_title,
                    group_key=key,
                    asset_ids=tuple(asset.asset_id for asset, _path in chunk),
                    png_bytes=make_asset_board(chunk, title=page_title),
                )
            )
    return tuple(rendered)


def _board_group_key(asset: AssetItem, strategy: str) -> str:
    if strategy == "hierarchy":
        return asset.parent_asset_id or asset.asset_id
    if strategy == "spatial_system":
        return asset.semantic_type or asset.category
    if strategy == "category":
        return asset.category
    return asset.reuse_group or asset.category


def write_asset_manifest(
    destination: Path,
    *,
    project: dict,
    assets: Iterable[AssetItem],
    generations: Iterable[dict],
) -> Path:
    atomic_write_json(
        destination,
        {
            "format": "scenelens.asset_manifest",
            "format_version": 1,
            "project": dict(project),
            "source_semantics": {
                "visible_evidence": "原画中直接可见",
                "ai_inference": "AI 对类别、关系或结构的推断",
                "user_added": "用户创建或校正",
                "ai_generated_completion": "AI 生成的不可见补全，不是事实",
            },
            "assets": [asset.to_dict() for asset in assets],
            "generations": [dict(item) for item in generations],
        },
    )
    return destination


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    )
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                pass
    return ImageFont.load_default()
