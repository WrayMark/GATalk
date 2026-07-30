from __future__ import annotations

from pathlib import Path
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from scenelens.modules.asset_breakdown.service import create_manual_asset
from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.asset_breakdown.ui.window import (
    AssetBreakdownWindow,
    _combo_model_id,
)
from scenelens.providers.contracts import ImageEditResponse
from scenelens.ui.workspace_hub import WorkspaceHubWindow


def _complex_scene(path: Path, kind: str) -> None:
    image = Image.new("RGB", (640, 360), (40, 55, 75))
    draw = ImageDraw.Draw(image)
    if kind == "village":
        draw.rectangle((0, 250, 640, 360), fill=(74, 62, 42))
        for x in (60, 220, 390):
            draw.rectangle((x, 110, x + 150, 270), fill=(120, 92, 58))
            draw.polygon(
                ((x - 15, 120), (x + 75, 45), (x + 165, 120)),
                fill=(75, 45, 38),
            )
            draw.rectangle((x + 22, 160, x + 65, 220), fill=(45, 35, 28))
    else:
        draw.rectangle((0, 290, 640, 360), fill=(42, 45, 48))
        for x in range(30, 620, 115):
            draw.rectangle((x, 70, x + 88, 300), fill=(64, 76, 88))
            draw.rectangle((x + 12, 90, x + 30, 275), fill=(22, 145, 175))
        draw.line((0, 160, 640, 210), fill=(210, 112, 45), width=14)
    image.save(path)


def test_hub_exposes_three_large_workspaces(qtbot) -> None:
    hub = WorkspaceHubWindow()
    qtbot.addWidget(hub)
    labels = [label.text() for label in hub.findChildren(QLabel)]
    assert any("资产拆分工作台" in value for value in labels)


def test_two_distinct_scene_projects_restore_manual_corrections(
    qtbot,
    tmp_path: Path,
) -> None:
    for index, kind in enumerate(("village", "industrial")):
        image_path = tmp_path / f"{kind}.png"
        _complex_scene(image_path, kind)
        store = AssetBreakdownStore.create(
            tmp_path / f"{kind}.scenelens-assets",
            f"{kind} 场景",
        )
        main = store.import_image(image_path, "main")
        asset = create_manual_asset(
            name="木屋模块" if kind == "village" else "管线模块",
            category="building" if kind == "village" else "modular_piece",
            rect=(0.08, 0.12, 0.42, 0.68),
            source_image_id=main.image_id,
        )
        store.add_or_replace_asset(asset)
        store.close()
        reopened = AssetBreakdownStore.open(
            tmp_path / f"{kind}.scenelens-assets"
        )
        assert reopened.state.assets[0].name == asset.name
        assert reopened.state.assets[0].user_modified
        reopened.close()


def test_asset_window_loads_and_edits_region(qtbot, tmp_path: Path) -> None:
    image_path = tmp_path / "场景 图片.png"
    _complex_scene(image_path, "village")
    store = AssetBreakdownStore.create(
        tmp_path / "项目 空格.scenelens-assets",
        "真实项目",
    )
    main = store.import_image(image_path, "main")
    asset = create_manual_asset(
        name="旧名称",
        category="prop",
        rect=(0.1, 0.1, 0.4, 0.4),
        source_image_id=main.image_id,
    )
    store.add_or_replace_asset(asset)
    window = AssetBreakdownWindow()
    qtbot.addWidget(window)
    window._attach_store(store)
    qtbot.waitUntil(lambda: window._loaded is not None, timeout=5000)
    window._refresh_asset_tree(select_id=asset.asset_id)
    assert window.asset_tree.topLevelItemCount() == 1
    window.detail_name.setText("用户修订名称")
    qtbot.mouseClick(
        window.apply_detail_button,
        Qt.MouseButton.LeftButton,
    )
    assert window._store.state.assets[0].name == "用户修订名称"
    assert window._store.state.assets[0].evidence_kind == "user_added"
    window._undo_stack.undo()
    assert window._store.state.assets[0].name == "旧名称"
    window._undo_stack.redo()
    assert window._store.state.assets[0].name == "用户修订名称"
    window.close()


def test_asset_generation_keeps_partial_success(
    qtbot,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "scene.png"
    _complex_scene(image_path, "industrial")
    store = AssetBreakdownStore.create(
        tmp_path / "partial.scenelens-assets",
        "部分成功",
    )
    main = store.import_image(image_path, "main")
    asset = create_manual_asset(
        name="工业管线",
        category="modular_piece",
        rect=(0.1, 0.1, 0.4, 0.5),
        source_image_id=main.image_id,
    )
    store.add_or_replace_asset(asset)
    window = AssetBreakdownWindow()
    qtbot.addWidget(window)
    window._attach_store(store)
    qtbot.waitUntil(lambda: window._loaded is not None, timeout=5000)
    image_buffer = BytesIO()
    Image.new("RGBA", (32, 32), (40, 120, 170, 255)).save(
        image_buffer,
        format="PNG",
    )
    response = ImageEditResponse(
        provider_id="mock",
        model_id="mock-image-v1",
        media_type="image/png",
        image_bytes=image_buffer.getvalue(),
    )
    mask = np.full((360, 640), 255, dtype=np.uint8)
    window._generation_finished(
        (
            [
                (
                    asset.asset_id,
                    response,
                    b"crop",
                    mask,
                    "rectangle_proxy_v1",
                    {"mode": "isolated_concept"},
                )
            ],
            [(asset.asset_id, "模拟的第二次生成失败")],
            "isolated_concept",
            main.sha256,
            False,
        )
    )
    records = window._store.state.generations
    assert [record.status for record in records] == [
        "completed",
        "failed",
    ]
    assert window._store.artifact_path(records[0].relative_path).is_file()
    window.close()


def test_gemini_image_choice_sends_model_id_not_display_label(qtbot) -> None:
    window = AssetBreakdownWindow()
    qtbot.addWidget(window)
    index = window.image_provider_combo.findData("google_gemini_image")
    window.image_provider_combo.setCurrentIndex(index)
    model_index = window.image_model_combo.findData(
        "gemini-3-pro-image"
    )
    window.image_model_combo.setCurrentIndex(model_index)
    assert window.image_model_combo.currentText().startswith(
        "Nano Banana Pro"
    )
    assert _combo_model_id(window.image_model_combo) == "gemini-3-pro-image"
    window.close()
