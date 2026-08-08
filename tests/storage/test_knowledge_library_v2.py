from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from scenelens.modules.knowledge_base.models import (
    KnowledgeItem,
    VisualBoardCard,
    VisualBoardLink,
)
from scenelens.modules.knowledge_base.project_refs import detect_gatalk_project
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.modules.knowledge_base.translation import (
    create_translation_request,
    validate_translation_output,
)
from scenelens.storage.project_store import ProjectStore


def test_image_excerpt_is_derived_without_rewriting_original(tmp_path: Path):
    rgb = np.zeros((20, 40, 3), dtype=np.uint8)
    rgb[:, :20] = (220, 40, 30)
    rgb[:, 20:] = (20, 80, 210)
    source = tmp_path / "原画.png"
    Image.fromarray(rgb).save(source)
    original_bytes = source.read_bytes()
    library = KnowledgeLibraryStore.create(tmp_path / "资料库", "美术资料")
    parent = library.import_file(source)

    excerpt = library.create_image_excerpt(
        parent.item_id,
        (0.5, 0.0, 0.5, 1.0),
        title="蓝色区域",
    )

    assert source.read_bytes() == original_bytes
    assert library.resolve_item_path(parent).read_bytes() == original_bytes
    with Image.open(library.resolve_item_path(excerpt)) as cropped:
        assert cropped.size == (20, 20)
        assert np.asarray(cropped.convert("RGB"))[:, :, 2].mean() > 200
    assert excerpt.parent_item_id == parent.item_id
    assert excerpt.normalized_rect == (0.5, 0.0, 0.5, 1.0)
    assert excerpt.source_type == "image_excerpt"


def test_translation_and_project_reference_survive_reopen(tmp_path: Path):
    library = KnowledgeLibraryStore.create(tmp_path / "资料库", "研究资料")
    item = library.add_link(
        "https://www.artstation.com/artwork/example",
        "建筑模块化案例",
        source_type="artstation",
    )
    library.update_item(
        replace(
            item,
            original_text="A modular environment art breakdown.",
            translation_text="一份模块化环境美术拆解。",
            translation_source="ai_confirmed",
            translation_provider_id="mock",
            translation_model_id="mock-vision-v1",
        )
    )
    scene = ProjectStore.create(tmp_path / "中文 项目.scenelens", "中世纪村庄")
    scene.close()
    detected = detect_gatalk_project(scene.root)
    library.add_project_reference(
        item.item_id,
        project_type=detected.project_type,
        project_id=detected.project_id,
        project_title=detected.title,
        project_path=detected.path,
        module_id=detected.module_id,
        note="用于屋顶模块研究",
    )

    reopened = KnowledgeLibraryStore.open(library.root)
    restored = reopened.state.items[0]

    assert restored.source_type == "artstation"
    assert restored.translation_text == "一份模块化环境美术拆解。"
    assert reopened.state.project_references[0].project_title == "中世纪村庄"
    assert reopened.items_for(search="模块化")[0].item_id == item.item_id


def test_v1_library_is_backed_up_before_v3_migration(tmp_path: Path):
    library = KnowledgeLibraryStore.create(tmp_path / "资料库", "迁移测试")
    entry = library.root / "library.json"
    payload = json.loads(entry.read_text(encoding="utf-8"))
    payload["format_version"] = 1
    for item in payload["state"]["items"]:
        item.pop("source_type", None)
    entry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    reopened = KnowledgeLibraryStore.open(library.root)

    assert reopened.state.title == "迁移测试"
    assert (library.root / "backups" / "pre-migration-v1-library.json").is_file()
    migrated = json.loads(entry.read_text(encoding="utf-8"))
    assert migrated["format_version"] == 3


def test_translation_contract_requires_explicit_network_confirmation():
    request = create_translation_request(
        "Key light and volumetric fog",
        model_id="mock-vision-v1",
        user_initiated=True,
        disclosure_confirmed=True,
    )
    result = validate_translation_output(
        {
            "translation": "主光与体积雾",
            "terminology_notes": ["Key light 译为主光"],
            "uncertainties": [],
        }
    )

    assert request.payload["source_text"] == "Key light and volumetric fog"
    assert request.user_initiated is True
    assert request.disclosure_confirmed is True
    assert result.translation == "主光与体积雾"


def test_invalid_persisted_excerpt_rect_is_rejected():
    payload = {
        "item_id": "excerpt",
        "domain_id": "art_reference",
        "item_type": "image",
        "title": "局部",
        "source_kind": "derived_crop",
        "normalized_rect": [0.0, 0.0, 1.0],
    }

    try:
        KnowledgeItem.from_dict(payload)
    except ValueError as exc:
        assert "坐标格式" in str(exc)
    else:
        raise AssertionError("invalid rect must not be accepted")


def test_visual_board_persists_snapshot_and_cleans_deleted_item(tmp_path: Path):
    library = KnowledgeLibraryStore.create(tmp_path / "资料库", "方向研究")
    first = library.add_note("主殿剪影", body="高塔形成第一读取点。")
    second = library.add_note("屋顶节奏", body="重复屋檐建立横向秩序。")
    board = library.add_visual_board("神庙建筑语言", purpose="归纳体块与屋顶节奏")
    cards = (
        VisualBoardCard("card-a", "knowledge_item", first.title, first.item_id),
        VisualBoardCard("card-b", "knowledge_item", second.title, second.item_id),
    )
    board = library.update_visual_board(
        replace(
            board,
            cards=cards,
            links=(VisualBoardLink("link-a", "card-a", "card-b", "从属"),),
        )
    )
    library.snapshot_visual_board(board.board_id, "初版")

    reopened = KnowledgeLibraryStore.open(library.root)
    restored = reopened.state.visual_boards[0]
    assert restored.snapshots[0].title == "初版"
    assert len(restored.links) == 1

    reopened.delete_items((first.item_id,))
    cleaned = reopened.state.visual_boards[0]
    assert [item.card_id for item in cleaned.cards] == ["card-b"]
    assert cleaned.links == ()
