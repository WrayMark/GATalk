from __future__ import annotations

from dataclasses import replace
import uuid
from typing import Any, Mapping

from scenelens.modules.asset_breakdown.models import (
    AssetItem,
    validate_normalized_rect,
)
from scenelens.storage.project_store import utc_now


def asset_from_ai(
    value: Mapping[str, Any],
    *,
    source_image_id: str,
) -> AssetItem:
    now = utc_now()
    return AssetItem(
        asset_id=str(value.get("asset_id") or uuid.uuid4()),
        name=str(value.get("name") or "未命名资产"),
        category=str(value.get("category", "unknown")),
        semantic_type=str(value.get("semantic_type", "")),
        parent_asset_id=str(value.get("parent_asset_id", "")),
        level=int(value.get("level", 0)),
        normalized_rect=validate_normalized_rect(
            value.get("normalized_rect", (0.25, 0.25, 0.5, 0.5))
        ),
        evidence_kind=str(value.get("evidence_kind", "ai_inference")),
        visible_evidence=str(value.get("visible_evidence", "")),
        inferred_details=str(value.get("inferred_details", "")),
        uncertainty=str(value.get("uncertainty", "")),
        confidence=float(value.get("confidence", 0.5)),
        occlusion_status=str(value.get("occlusion_status", "none")),
        reuse_group=str(value.get("reuse_group", "")),
        instance_count=int(value.get("instance_count", 1)),
        production_priority=str(
            value.get("production_priority", "medium")
        ),
        production_strategy=str(value.get("production_strategy", "")),
        module_pieces=tuple(
            str(item) for item in value.get("module_pieces", ())
        ),
        variants=tuple(str(item) for item in value.get("variants", ())),
        material_notes=str(value.get("material_notes", "")),
        source_image_id=source_image_id,
        created_at=now,
        updated_at=now,
    )


def merge_ai_assets(
    existing: tuple[AssetItem, ...],
    incoming: tuple[AssetItem, ...],
) -> tuple[AssetItem, ...]:
    """Preserve user-authored assets while replacing the previous AI layer."""

    retained = [
        asset
        for asset in existing
        if asset.user_modified or asset.evidence_kind == "user_added"
    ]
    existing_ids = {asset.asset_id for asset in retained}
    for asset in incoming:
        if asset.asset_id in existing_ids:
            asset = replace(asset, asset_id=str(uuid.uuid4()))
        retained.append(asset)
        existing_ids.add(asset.asset_id)
    return tuple(retained)


def create_manual_asset(
    *,
    name: str,
    category: str,
    rect: tuple[float, float, float, float],
    source_image_id: str,
) -> AssetItem:
    now = utc_now()
    return AssetItem(
        asset_id=str(uuid.uuid4()),
        name=name.strip() or "新资产",
        category=category,
        semantic_type="用户补充",
        normalized_rect=rect,
        evidence_kind="user_added",
        confidence=1.0,
        user_modified=True,
        source_image_id=source_image_id,
        created_at=now,
        updated_at=now,
    )


def split_asset(
    asset: AssetItem,
    *,
    axis: str = "horizontal",
) -> tuple[AssetItem, AssetItem]:
    x, y, width, height = asset.normalized_rect
    if axis == "vertical":
        rects = (
            (x, y, width, height / 2.0),
            (x, y + height / 2.0, width, height / 2.0),
        )
    else:
        rects = (
            (x, y, width / 2.0, height),
            (x + width / 2.0, y, width / 2.0, height),
        )
    now = utc_now()
    children = []
    for index, rect in enumerate(rects, start=1):
        children.append(
            replace(
                asset,
                asset_id=str(uuid.uuid4()),
                name=f"{asset.name} {index}",
                parent_asset_id=asset.asset_id,
                level=asset.level + 1,
                normalized_rect=rect,
                evidence_kind="user_added",
                user_modified=True,
                created_at=now,
                updated_at=now,
            )
        )
    return children[0], children[1]


def merge_assets(
    assets: tuple[AssetItem, ...],
    *,
    name: str,
    category: str,
) -> AssetItem:
    if len(assets) < 2:
        raise ValueError("至少选择两个资产才能合并。")
    left = min(item.normalized_rect[0] for item in assets)
    top = min(item.normalized_rect[1] for item in assets)
    right = max(
        item.normalized_rect[0] + item.normalized_rect[2]
        for item in assets
    )
    bottom = max(
        item.normalized_rect[1] + item.normalized_rect[3]
        for item in assets
    )
    now = utc_now()
    return AssetItem(
        asset_id=str(uuid.uuid4()),
        name=name.strip() or "合并资产",
        category=category,
        semantic_type="用户合并",
        normalized_rect=(left, top, right - left, bottom - top),
        evidence_kind="user_added",
        visible_evidence="由用户合并多个可见区域。",
        confidence=1.0,
        instance_count=sum(item.instance_count for item in assets),
        user_modified=True,
        source_image_id=assets[0].source_image_id,
        created_at=now,
        updated_at=now,
    )

