from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scenelens.modules.asset_breakdown.production_handoff import (
    build_handoff_payload,
    export_handoff_csv,
    export_handoff_json,
    production_order,
    synchronize_production_specs,
    validate_production_specs,
)
from scenelens.modules.asset_breakdown.service import create_manual_asset


def _assets():
    parent = create_manual_asset(
        name="主殿整体",
        category="building",
        rect=(0.1, 0.1, 0.7, 0.7),
        source_image_id="source",
    )
    child = replace(
        create_manual_asset(
            name="屋顶模块",
            category="modular_piece",
            rect=(0.2, 0.1, 0.4, 0.2),
            source_image_id="source",
        ),
        parent_asset_id=parent.asset_id,
    )
    return parent, child


def test_production_specs_follow_dependencies_and_export(tmp_path: Path):
    assets = _assets()
    specs = synchronize_production_specs(assets, ())

    assert production_order(specs) == (assets[0].asset_id, assets[1].asset_id)
    payload = build_handoff_payload(
        project_id="project-1",
        project_title="云海神庙",
        plan=None,
        assets=assets,
        specs=specs,
    )
    json_path = export_handoff_json(tmp_path / "handoff.json", payload)
    csv_path = export_handoff_csv(tmp_path / "handoff.csv", payload)

    assert "gatalk.asset_production_handoff" in json_path.read_text("utf-8")
    assert "屋顶模块" in csv_path.read_text("utf-8-sig")
    assert payload["production_order"] == list(production_order(specs))


def test_production_dependency_cycle_is_rejected():
    assets = _assets()
    specs = synchronize_production_specs(assets, ())
    cyclic = (
        replace(specs[0], dependency_asset_ids=(assets[1].asset_id,)),
        replace(specs[1], dependency_asset_ids=(assets[0].asset_id,)),
    )

    with pytest.raises(ValueError, match="循环"):
        validate_production_specs(assets, cyclic)
