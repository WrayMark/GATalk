from __future__ import annotations

from pathlib import Path
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from scenelens.modules.asset_breakdown.service import create_manual_asset
from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.asset_breakdown.prompt_workshop import (
    AssetPromptContext,
)
from scenelens.modules.asset_breakdown.ui.window import (
    AssetBreakdownWindow,
    _combo_model_id,
)
from scenelens.core.handoffs import WorkspaceHandoff
from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditResponse,
    ProviderImage,
)
from scenelens.providers.execution import ReviewExecutionResult
from scenelens.providers.mock import MockProvider
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


def test_asset_window_accepts_artwork_study_handoff_and_keeps_plans_separate(
    qtbot,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "作品原画.png"
    _complex_scene(image_path, "village")
    import hashlib

    sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    handoff = WorkspaceHandoff(
        source_module_id="scenelens.artwork_study",
        source_workspace_id="artwork_study",
        source_project_id="study-1",
        source_project_title="村庄作品研究",
        content_type="artwork_study_to_asset_breakdown",
        primary_image_path=str(image_path),
        primary_image_sha256=sha256,
        payload={
            "work_type": "environment_concept",
            "study_goal": "理解建筑层级",
            "personal_notes": "中央建筑是地标",
        },
        created_at="now",
    )
    target = tmp_path / "交接项目.scenelens-assets"
    window = AssetBreakdownWindow()
    qtbot.addWidget(window)
    assert window.receive_workspace_handoff(handoff, target_root=target)
    qtbot.waitUntil(lambda: window._loaded is not None, timeout=5000)
    assert window._state.study_handoffs[0].personal_notes == "中央建筑是地标"
    assert window._state.main_image.sha256 == sha256
    first = window._state.breakdown_plans[0]
    window.plan_preset_combo.setCurrentIndex(
        window.plan_preset_combo.findData("detail_components")
    )
    window._new_plan_from_preset()
    assert len(window._state.breakdown_plans) == 2
    assert window._state.selected_plan_id != first.plan_id
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


def test_manual_and_automatic_ai_controls_stay_unified(qtbot) -> None:
    window = AssetBreakdownWindow()
    qtbot.addWidget(window)

    provider_index = window.image_provider_combo.findData(
        "google_gemini_image"
    )
    window.image_provider_combo.setCurrentIndex(provider_index)
    assert (
        window.auto_image_provider_combo.currentData()
        == "google_gemini_image"
    )

    pro_index = window.image_model_combo.findData("gemini-3-pro-image")
    window.image_model_combo.setCurrentIndex(pro_index)
    assert (
        _combo_model_id(window.auto_image_model_combo)
        == "gemini-3-pro-image"
    )

    lite_index = window.auto_image_model_combo.findData(
        "gemini-3.1-flash-lite-image"
    )
    window.auto_image_model_combo.setCurrentIndex(lite_index)
    assert (
        _combo_model_id(window.image_model_combo)
        == "gemini-3.1-flash-lite-image"
    )

    resolution_index = window.auto_resolution_combo.findData("2K")
    window.auto_resolution_combo.setCurrentIndex(resolution_index)
    assert window.image_resolution_combo.currentData() == "2K"

    window.auto_image_key_edit.setText("shared-secret")
    assert window.image_key_edit.text() == "shared-secret"

    vision_index = window.auto_vision_provider_combo.findData(
        "google_gemini"
    )
    window.auto_vision_provider_combo.setCurrentIndex(vision_index)
    assert window.vision_provider_combo.currentData() == "google_gemini"
    window.auto_vision_model_edit.setText("gemini-custom-vision")
    assert window.vision_model_edit.text() == "gemini-custom-vision"
    assert window.prompt_panel.model_edit.text() == "gemini-custom-vision"
    window.auto_image_key_edit.setText("shared-secret")
    assert window.vision_key_edit.text() == "shared-secret"
    assert window.auto_vision_key_edit.text() == "shared-secret"
    assert window.prompt_panel.key_edit.text() == "shared-secret"
    window.close()


def test_prompt_workshop_creates_edits_copies_and_restores(
    qtbot,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "提示语场景.png"
    _complex_scene(image_path, "industrial")
    root = tmp_path / "提示语项目.scenelens-assets"
    store = AssetBreakdownStore.create(root, "提示语项目")
    main = store.import_image(image_path, "main")
    window = AssetBreakdownWindow()
    qtbot.addWidget(window)
    window._attach_store(store)
    qtbot.waitUntil(lambda: window._loaded is not None, timeout=5000)
    assert window.workflow_tabs.tabText(2) == "资产拆分提示语"

    request = window._prompt_reviewer.create_request(
        AssetPromptContext(
            project_id=window._state.project_id,
            title=window._state.title,
            scene_type=window._state.scene_type,
            production_goal=window._state.production_goal,
            notes=window._state.notes,
            target_tool="generic",
            image_metadata={"width": 640, "height": 360},
        ),
        (ProviderImage("main_concept", "image/png", b"image"),),
        user_initiated=True,
        disclosure_confirmed=True,
    )
    response = MockProvider().review(
        request,
        "",
        CancellationToken(),
    )
    execution = ReviewExecutionResult(
        response=response,
        requested_model_id=response.model_id,
        attempted_model_ids=(response.model_id,),
    )
    window._prompt_request_finished(
        {
            "mode": "initial",
            "project_id": window._state.project_id,
            "source_hash": main.sha256,
            "session_id": "",
            "base_revision_id": "",
            "feedback": "",
            "images_sent": 1,
            "output": window._prompt_reviewer.validate_output(
                response.output
            ),
            "execution": execution,
        }
    )
    assert len(window._state.prompt_sessions) == 1
    assert "游戏环境资产拆分" in (
        window.prompt_panel.prompt_zh_edit.toPlainText()
    )

    session = window._state.prompt_sessions[0]
    window._prompt_request_finished(
        {
            "mode": "refine",
            "project_id": window._state.project_id,
            "source_hash": main.sha256,
            "session_id": session.session_id,
            "base_revision_id": session.current_revision.revision_id,
            "feedback": "减少次要道具，强化建筑模块。",
            "images_sent": 0,
            "output": window._prompt_reviewer.validate_output(
                response.output
            ),
            "execution": execution,
        }
    )
    assert len(window._state.prompt_sessions[0].revisions) == 2
    assert [item.role for item in window._state.prompt_sessions[0].messages[-2:]] == [
        "user",
        "assistant",
    ]
    assert (
        window._state.prompt_sessions[0].messages[-2].content
        == "减少次要道具，强化建筑模块。"
    )

    window.prompt_panel.prompt_zh_edit.appendPlainText(
        "\n用户补充：保留霓虹招牌。"
    )
    window._save_manual_prompt_revision()
    assert len(window._state.prompt_sessions[0].revisions) == 3
    assert window._state.prompt_sessions[0].revisions[-1].origin == (
        "user_edit"
    )
    window._copy_prompt_text(
        window.prompt_panel.prompt_zh_edit.toPlainText(),
        "已复制",
    )
    assert "保留霓虹招牌" in QApplication.clipboard().text()
    window.close()

    reopened = AssetBreakdownStore.open(root)
    assert len(reopened.state.prompt_sessions[0].revisions) == 3
    assert "保留霓虹招牌" in (
        reopened.state.prompt_sessions[0].revisions[-1].prompt_zh
    )
    reopened.close()
