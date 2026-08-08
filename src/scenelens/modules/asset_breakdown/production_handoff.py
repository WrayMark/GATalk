from __future__ import annotations

import csv
from dataclasses import replace
import json
import os
from pathlib import Path
from typing import Iterable
import uuid

from scenelens.modules.asset_breakdown.models import (
    AssetItem,
    AssetProductionSpec,
    BreakdownPlan,
)
from scenelens.storage.atomic import atomic_write_json
from scenelens.storage.project_store import utc_now


STATUS_LABELS = {
    "planned": "待规划",
    "ready": "可开工",
    "in_production": "制作中",
    "review": "待审阅",
    "approved": "已通过",
    "deferred": "已推迟",
}


def synchronize_production_specs(
    assets: Iterable[AssetItem],
    existing: Iterable[AssetProductionSpec],
) -> tuple[AssetProductionSpec, ...]:
    asset_values = tuple(assets)
    asset_ids = {item.asset_id for item in asset_values}
    by_asset = {
        item.asset_id: item
        for item in existing
        if item.asset_id in asset_ids
    }
    counters: dict[str, int] = {}
    output: list[AssetProductionSpec] = []
    for asset in asset_values:
        current = by_asset.get(asset.asset_id)
        if current is not None:
            output.append(current)
            continue
        prefix = _category_prefix(asset.category)
        counters[prefix] = counters.get(prefix, 0) + 1
        output.append(
            _default_spec(
                asset,
                f"{prefix}_{counters[prefix]:03d}",
            )
        )
    validate_production_specs(asset_values, output)
    return tuple(output)


def validate_production_specs(
    assets: Iterable[AssetItem],
    specs: Iterable[AssetProductionSpec],
) -> None:
    asset_ids = {item.asset_id for item in assets}
    values = tuple(specs)
    if len({item.asset_id for item in values}) != len(values):
        raise ValueError("同一资产存在多条生产规格。")
    codes = [item.asset_code.casefold() for item in values if item.asset_code]
    if len(set(codes)) != len(codes):
        raise ValueError("资产编码必须唯一。")
    graph: dict[str, tuple[str, ...]] = {}
    for item in values:
        if item.asset_id not in asset_ids:
            raise ValueError("生产规格引用了不存在的资产。")
        if item.asset_id in item.dependency_asset_ids:
            raise ValueError("资产不能依赖自身。")
        if set(item.dependency_asset_ids) - asset_ids:
            raise ValueError("生产依赖引用了不存在的资产。")
        graph[item.asset_id] = item.dependency_asset_ids

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(asset_id: str) -> None:
        if asset_id in visiting:
            raise ValueError("资产生产依赖形成循环。")
        if asset_id in visited:
            return
        visiting.add(asset_id)
        for dependency in graph.get(asset_id, ()):
            visit(dependency)
        visiting.remove(asset_id)
        visited.add(asset_id)

    for asset_id in graph:
        visit(asset_id)


def production_order(
    specs: Iterable[AssetProductionSpec],
) -> tuple[str, ...]:
    graph = {item.asset_id: item.dependency_asset_ids for item in specs}
    order: list[str] = []
    visited: set[str] = set()

    def visit(asset_id: str) -> None:
        if asset_id in visited:
            return
        for dependency in graph.get(asset_id, ()):
            visit(dependency)
        visited.add(asset_id)
        order.append(asset_id)

    for asset_id in graph:
        visit(asset_id)
    return tuple(order)


def build_handoff_payload(
    *,
    project_id: str,
    project_title: str,
    plan: BreakdownPlan | None,
    assets: Iterable[AssetItem],
    specs: Iterable[AssetProductionSpec],
) -> dict[str, object]:
    asset_values = tuple(assets)
    spec_values = tuple(specs)
    validate_production_specs(asset_values, spec_values)
    by_asset = {item.asset_id: item for item in asset_values}
    order = production_order(spec_values)
    by_spec = {item.asset_id: item for item in spec_values}
    rows: list[dict[str, object]] = []
    for asset_id in order:
        asset = by_asset.get(asset_id)
        spec = by_spec.get(asset_id)
        if asset is None or spec is None:
            continue
        rows.append(
            {
                "asset_id": asset.asset_id,
                "asset_code": spec.asset_code,
                "name": asset.name,
                "category": asset.category,
                "semantic_type": asset.semantic_type,
                "parent_asset_id": asset.parent_asset_id,
                "reuse_group": asset.reuse_group,
                "instance_count": asset.instance_count,
                "production_priority": asset.production_priority,
                "production_status": spec.status,
                "target_dimensions_cm": spec.target_dimensions_cm,
                "pivot_policy": spec.pivot_policy,
                "geometry_strategy": spec.geometry_strategy,
                "material_slots": list(spec.material_slots),
                "texture_sets": list(spec.texture_sets),
                "lod_policy": spec.lod_policy,
                "collision_policy": spec.collision_policy,
                "nanite_policy": spec.nanite_policy,
                "ue_destination": spec.ue_destination,
                "dependency_asset_ids": list(spec.dependency_asset_ids),
                "deliverables": list(spec.deliverables),
                "notes": spec.notes,
                "evidence_kind": asset.evidence_kind,
                "uncertainty": asset.uncertainty,
            }
        )
    return {
        "format": "gatalk.asset_production_handoff",
        "format_version": 1,
        "project_id": project_id,
        "project_title": project_title,
        "plan": None
        if plan is None
        else {
            "plan_id": plan.plan_id,
            "name": plan.name,
            "purpose": plan.purpose,
            "status": plan.status,
        },
        "created_at": utc_now(),
        "production_order": list(order),
        "assets": rows,
        "boundary": (
            "该文件是制作规划与交接清单，不代表原画中不可见结构已经确认，"
            "也不自动修改 Unreal Engine 项目。"
        ),
    }


def export_handoff_json(destination: str | Path, payload: dict[str, object]) -> Path:
    path = Path(destination)
    atomic_write_json(path, payload)
    return path


def export_handoff_csv(destination: str | Path, payload: dict[str, object]) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fields = (
        "asset_code",
        "name",
        "category",
        "semantic_type",
        "reuse_group",
        "instance_count",
        "production_priority",
        "production_status",
        "target_dimensions_cm",
        "pivot_policy",
        "geometry_strategy",
        "material_slots",
        "texture_sets",
        "lod_policy",
        "collision_policy",
        "nanite_policy",
        "ue_destination",
        "dependency_asset_ids",
        "deliverables",
        "notes",
        "evidence_kind",
        "uncertainty",
    )
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for raw in payload.get("assets", ()):
                row = dict(raw)
                for key in (
                    "material_slots",
                    "texture_sets",
                    "dependency_asset_ids",
                    "deliverables",
                ):
                    row[key] = " | ".join(str(item) for item in row.get(key, ()))
                writer.writerow(row)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def _default_spec(asset: AssetItem, asset_code: str) -> AssetProductionSpec:
    category = asset.category
    modular = category in {"building", "modular_piece"}
    material_slots = (
        tuple(asset.module_pieces)
        if category == "material"
        else (("主体", "可替换细节") if modular else ("主体",))
    )
    return AssetProductionSpec(
        spec_id=str(uuid.uuid4()),
        asset_id=asset.asset_id,
        asset_code=asset_code,
        status="planned",
        pivot_policy=("模块网格基准点" if modular else "接地中心或装配基准"),
        geometry_strategy=(
            "模块套件与实例变体" if modular else asset.production_strategy
        ),
        material_slots=tuple(material_slots),
        texture_sets=("BaseColor", "Normal", "ORM"),
        lod_policy=("评估 Nanite；如禁用则建立 LOD0–LOD2"),
        collision_policy=(
            "按玩家通行与阻挡需求建立简化碰撞"
            if category not in {"material", "decal", "background", "lighting_vfx"}
            else "不适用或随承载资产处理"
        ),
        nanite_policy=(
            "not_applicable"
            if category in {"material", "decal", "lighting_vfx"}
            else "evaluate"
        ),
        ue_destination=f"/Game/Environment/{asset_code}",
        dependency_asset_ids=(
            (asset.parent_asset_id,) if asset.parent_asset_id else ()
        ),
        deliverables=("模型", "材质实例", "碰撞检查")
        if category not in {"material", "decal", "lighting_vfx"}
        else ("材质或效果资源",),
        notes=asset.uncertainty,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def _category_prefix(category: str) -> str:
    return {
        "building": "ENV_BLD",
        "modular_piece": "ENV_MOD",
        "prop": "ENV_PRP",
        "vegetation": "ENV_VEG",
        "terrain": "ENV_TRN",
        "material": "MAT",
        "decal": "DEC",
        "background": "ENV_BG",
        "lighting_vfx": "VFX",
        "character_vehicle": "CHR",
    }.get(category, "ENV_AST")
