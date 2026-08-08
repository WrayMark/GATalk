from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scenelens.modules.review_control import storage as review_storage
from scenelens.modules.review_control.storage import ReviewCenterStore


def _handoff() -> dict[str, object]:
    return {
        "title": "加强主体与背景的明度分离",
        "description": "主体轮廓在中间调背景中不够清楚。",
        "acceptance_criteria": "缩略图下主体轮廓仍可辨认。",
        "priority": "high",
        "source_module_id": "scenelens.artwork_study",
        "source_project_id": "study-1",
        "source_project_title": "村庄作品研究",
        "source_project_path": "C:/研究/村庄",
        "source_entity_type": "dimension_study",
        "source_entity_id": "value_structure",
        "source_version_id": "source-v1",
        "labels": ["明度", "主体"],
    }


def test_handoff_is_deduplicated_and_restored(tmp_path: Path):
    store = ReviewCenterStore.open_or_create(tmp_path / "review-center")
    first = store.add_task_from_handoff(_handoff())
    second = store.add_task_from_handoff(_handoff())
    store.add_verification(
        first.task_id,
        version_label="UE 截图 v2",
        version_id="version-2",
        state="improved",
        evidence_summary="主体与背景的明度差扩大。",
    )

    reopened = ReviewCenterStore.open_or_create(store.root)

    assert first.task_id == second.task_id
    assert len(reopened.state.tasks) == 1
    assert reopened.state.verifications[0].version_id == "version-2"
    assert reopened.state.verifications[0].state == "improved"


def test_task_status_and_quality_gate_keep_version_history(tmp_path: Path):
    store = ReviewCenterStore.open_or_create(tmp_path / "review-center")
    task = store.add_task_from_handoff(_handoff())
    store.update_task(replace(task, status="in_progress"))
    gate = store.add_gate(
        name="主体可读性",
        dimension="视觉层级",
        acceptance_criteria="第一视觉焦点在缩略图下清楚可辨。",
        required=True,
        source_project_id="study-1",
        source_project_title="村庄作品研究",
    )
    store.evaluate_gate(
        gate.gate_id,
        version_label="截图 v2",
        version_id="v2",
        state="warning",
        evidence_summary="焦点可辨，但局部高光仍有竞争。",
    )
    store.evaluate_gate(
        gate.gate_id,
        version_label="截图 v3",
        version_id="v3",
        state="pass",
        evidence_summary="次要高光已压低，主体保持第一读取顺序。",
    )

    reopened = ReviewCenterStore.open_or_create(store.root)

    assert reopened.state.tasks[0].status == "in_progress"
    assert reopened.state.gates[0].state == "pass"
    assert [item.version_id for item in reopened.state.gate_evaluations] == [
        "v2",
        "v3",
    ]


def test_review_center_export_contains_provenance_not_project_assets(tmp_path: Path):
    store = ReviewCenterStore.open_or_create(tmp_path / "review-center")
    store.add_task_from_handoff(_handoff())

    destination = store.export(tmp_path / "review-export.json")
    text = destination.read_text(encoding="utf-8")

    assert "gatalk.review_control_export" in text
    assert "scenelens.artwork_study" in text
    assert "加强主体与背景的明度分离" in text


def test_task_dependencies_block_and_reject_cycles(tmp_path: Path):
    store = ReviewCenterStore.open_or_create(tmp_path / "review-center")
    first = store.add_task_from_handoff(_handoff())
    second_payload = dict(_handoff())
    second_payload["source_entity_id"] = "fog-depth"
    second_payload["title"] = "调整空气透视"
    second = store.add_task_from_handoff(second_payload)
    second = store.update_task(
        replace(second, blocked_by_task_ids=(first.task_id,))
    )

    assert store.unresolved_blockers(second.task_id) == (first,)
    with pytest.raises(ValueError, match="循环"):
        store.update_task(
            replace(first, blocked_by_task_ids=(second.task_id,))
        )
    store.batch_update_tasks((first.task_id,), status="done")
    assert store.unresolved_blockers(second.task_id) == ()


def test_stage_gate_template_is_repeatable_without_duplicates(tmp_path: Path):
    store = ReviewCenterStore.open_or_create(tmp_path / "review-center")

    first = store.apply_gate_template(
        "blockout",
        source_project_id="village",
        source_project_title="中世纪村庄",
    )
    second = store.apply_gate_template(
        "blockout",
        source_project_id="village",
        source_project_title="中世纪村庄",
    )

    assert len(first) == 3
    assert second == ()
    assert {item.production_stage for item in first} == {"blockout"}


def test_second_review_center_instance_is_read_only(tmp_path: Path, monkeypatch):
    root = tmp_path / "review-center"
    monkeypatch.setattr(
        review_storage,
        "default_review_center_root",
        lambda: root,
    )
    writer = ReviewCenterStore.open_default()
    reader = ReviewCenterStore.open_default()

    assert writer.read_only is False
    assert reader.read_only is True
    with pytest.raises(ValueError, match="只读"):
        reader.add_task_from_handoff(_handoff())

    reader.close()
    writer.close()
