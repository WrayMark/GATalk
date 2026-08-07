from __future__ import annotations

from dataclasses import replace
import hashlib
from importlib.resources import files
import json
import uuid
from typing import Any, Mapping

from scenelens.modules.asset_breakdown.models import (
    BreakdownPlan,
    SceneUnderstanding,
)
from scenelens.storage.project_store import utc_now


def plan_fingerprint(plan: BreakdownPlan | Mapping[str, Any] | None) -> str:
    """Return a stable identity for the exact production plan revision."""

    if plan is None:
        return ""
    value = plan.to_dict() if isinstance(plan, BreakdownPlan) else dict(plan)
    for key in ("created_at", "updated_at", "status"):
        value.pop(key, None)
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_breakdown_plan_presets() -> dict[str, Any]:
    resource = files(
        "scenelens.modules.asset_breakdown.config"
    ).joinpath("breakdown_plans.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def create_plan_from_preset(
    preset_id: str = "production_kit",
    *,
    name: str | None = None,
    understanding_id: str = "",
) -> BreakdownPlan:
    config = load_breakdown_plan_presets()
    preset = next(
        (item for item in config["presets"] if item["id"] == preset_id),
        None,
    )
    if preset is None:
        raise ValueError(f"未知的拆分方案预设：{preset_id}")
    now = utc_now()
    return BreakdownPlan(
        plan_id=str(uuid.uuid4()),
        name=name or str(preset["name"]),
        preset_id=str(preset["id"]),
        purpose=str(preset["purpose"]),
        scope=str(preset["scope"]),
        category_depths={
            str(key): int(value)
            for key, value in preset["category_depths"].items()
        },
        grouping_strategy=str(preset["grouping_strategy"]),
        max_items_per_page=int(preset["max_items_per_page"]),
        source_understanding_id=understanding_id,
        created_at=now,
        updated_at=now,
    )


def plan_from_ai(
    value: Mapping[str, Any],
    *,
    understanding_id: str,
) -> BreakdownPlan:
    now = utc_now()
    depths = {
        str(item["category"]): int(item["depth"])
        for item in value.get("category_depths", ())
    }
    return BreakdownPlan(
        plan_id=str(uuid.uuid4()),
        name=str(value.get("name", "AI 建议方案")),
        preset_id=str(value.get("preset_id", "custom_mixed")),
        purpose=str(value.get("purpose", "")),
        scope=str(value.get("scope", "whole_scene")),
        category_depths=depths,
        grouping_strategy=str(
            value.get("grouping_strategy", "asset_family")
        ),
        max_items_per_page=int(value.get("max_items_per_page", 9)),
        source_understanding_id=understanding_id,
        user_notes=str(value.get("rationale", "")),
        created_at=now,
        updated_at=now,
    )


def understanding_from_ai(
    value: Mapping[str, Any],
    *,
    source_image_sha256: str,
    provider_id: str,
    model_id: str,
    analyzer_version: str,
) -> SceneUnderstanding:
    now = utc_now()
    return SceneUnderstanding(
        understanding_id=str(uuid.uuid4()),
        source_image_sha256=source_image_sha256,
        scene_archetype=str(value.get("scene_archetype", "")),
        summary=str(value.get("summary", "")),
        spatial_structure=tuple(
            str(item) for item in value.get("spatial_structure", ())
        ),
        production_systems=tuple(
            str(item) for item in value.get("production_systems", ())
        ),
        asset_families=tuple(
            dict(item) for item in value.get("asset_families", ())
        ),
        visible_evidence=tuple(
            str(item) for item in value.get("visible_evidence", ())
        ),
        uncertainties=tuple(
            str(item) for item in value.get("uncertainties", ())
        ),
        provider_id=provider_id,
        model_id=model_id,
        analyzer_version=analyzer_version,
        created_at=now,
    )


def confirm_plan(plan: BreakdownPlan, *, notes: str = "") -> BreakdownPlan:
    return replace(
        plan,
        status="confirmed",
        user_notes=notes,
        updated_at=utc_now(),
    )
