from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtTest import QTest

from scenelens.app import create_application
from scenelens.modules.artwork_study.storage import ArtworkStudyStore
from scenelens.modules.artwork_study.ui.window import ArtworkStudyWindow
from scenelens.modules.asset_breakdown.service import create_manual_asset
from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.asset_breakdown.ui.window import AssetBreakdownWindow
from scenelens.modules.comparative_study.storage import ComparativeStudyStore
from scenelens.modules.comparative_study.ui.window import ComparativeStudyWindow
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.modules.knowledge_base.ui.window import KnowledgeBaseWindow
from scenelens.modules.review_control.storage import ReviewCenterStore
from scenelens.modules.review_control.ui.window import ReviewControlWindow
from scenelens.storage.app_settings import AppSettings, AppSettingsStore
from scenelens.storage.models import ArtBrief
from scenelens.storage.project_store import ProjectStore
from scenelens.storage.recent_projects import RecentProjects
from scenelens.ui.main_window import MainWindow
from scenelens.ui.settings_controller import GlobalSettingsController
from scenelens.ui.settings_dialog import GlobalSettingsDialog
from scenelens.ui.theme import apply_appearance
from scenelens.ui.workspace_hub import WorkspaceHubWindow


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "images" / "user-guide-0.18.0"
FIXTURE = ROOT / ".artifacts" / "user-guide-fixture-0.18.0"


def _safe_reset(path: Path) -> None:
    resolved = path.resolve()
    allowed = (ROOT / ".artifacts").resolve()
    if allowed not in resolved.parents:
        raise RuntimeError("Refusing fixture cleanup outside .artifacts")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _scene(path: Path, *, variant: int = 0) -> None:
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), (33, 51, 68))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 420, width, height), fill=(54, 72, 65))
    draw.ellipse((-160, -210, 720, 480), fill=(70, 106, 126))
    draw.ellipse((560, -160, 1450, 430), fill=(123, 144, 150))
    offset = 30 * variant
    for x, building_width, building_height in (
        (90, 250, 280),
        (420, 390, 370),
        (890, 250, 250),
    ):
        top = 500 - building_height + offset
        draw.rectangle(
            (x, top, x + building_width, 520),
            fill=(118 + 8 * variant, 87, 56),
        )
        draw.polygon(
            (
                (x - 20, top + 35),
                (x + building_width // 2, top - 90),
                (x + building_width + 20, top + 35),
            ),
            fill=(55, 82 + 6 * variant, 70),
        )
        for window_x in range(x + 32, x + building_width - 25, 74):
            draw.rectangle(
                (window_x, top + 85, window_x + 30, top + 130),
                fill=(202, 157 - 10 * variant, 72),
            )
    image.save(path)


def _capture(
    widget,
    filename: str,
    width: int,
    height: int,
    *,
    close_after: bool = True,
) -> None:
    widget.resize(width, height)
    widget.show()
    for _ in range(10):
        app.processEvents()
        QTest.qWait(20)
    target = OUTPUT / filename
    if not widget.grab().save(str(target), "PNG"):
        raise OSError(f"无法保存使用手册截图：{target}")
    if close_after:
        widget.close()
        app.processEvents()


def _workspace_hub() -> None:
    _capture(WorkspaceHubWindow(), "01-workspace-hub.png", 1480, 900)


def _global_settings() -> None:
    dialog = GlobalSettingsDialog(settings)
    _capture(dialog, "02-global-settings.png", 680, 650)


def _knowledge_base(source: Path) -> None:
    store = KnowledgeLibraryStore.create(FIXTURE / "环境美术资料库", "环境美术资料库")
    item = store.import_file(source, title="山地聚落概念图")
    collection = store.add_collection("建筑语言")
    store.set_memberships(item.item_id, (collection.collection_id,))
    store.add_note("研究笔记", body="屋顶轮廓建立节奏，连廊负责尺度过渡。")
    window = KnowledgeBaseWindow()
    window.open_path(store.root)
    window.library_label.setText("环境美术资料库")
    _capture(window, "03-knowledge-base.png", 1520, 900)


def _comparative_study(first: Path, second: Path) -> None:
    store = ComparativeStudyStore.create(FIXTURE / "聚落对照研究", "聚落空间层级对照")
    left = store.import_image(first, title="清晨方案")
    right = store.import_image(second, title="阴天方案")
    store.save(
        replace(
            store.state,
            research_question="比较两种明度与空间组织对建筑层级的影响。",
            known_context="教学用合成场景。",
            active_item_ids=(left.item_id, right.item_id),
            selected_axes=("构图与层级", "明度结构", "色彩组织"),
        )
    )
    window = ComparativeStudyWindow()
    window._store = store
    window._load_state()
    _capture(window, "04-comparative-study.png", 1580, 920)


def _artwork_study(source: Path) -> None:
    store = ArtworkStudyStore.create(FIXTURE / "山地聚落作品研究", "山地聚落作品研究")
    store.import_image(source)
    window = ArtworkStudyWindow()
    window._set_store(store)
    window.goal_edit.setPlainText("研究建筑剪影、雾与明度层级。")
    window.context_edit.setPlainText("教学用合成图片。")
    window.show()
    for _ in range(600):
        app.processEvents()
        if window._local_analysis is not None:
            break
        QTest.qWait(50)
    if window._local_analysis is None:
        raise TimeoutError("作品研究截图未能在 30 秒内完成本地分析")
    _capture(window, "05-artwork-study.png", 1540, 920)


def _asset_breakdown(source: Path) -> None:
    store = AssetBreakdownStore.create(FIXTURE / "山地聚落资产", "山地聚落资产规划")
    main = store.import_image(source, "main")
    hall = create_manual_asset(
        name="中央主殿",
        category="building",
        rect=(0.32, 0.18, 0.35, 0.58),
        source_image_id=main.image_id,
    )
    roof = replace(
        create_manual_asset(
            name="屋顶模块套件",
            category="modular_piece",
            rect=(0.36, 0.18, 0.28, 0.22),
            source_image_id=main.image_id,
        ),
        parent_asset_id=hall.asset_id,
        reuse_group="roof-kit",
    )
    store.add_or_replace_asset(hall)
    store.add_or_replace_asset(roof)
    window = AssetBreakdownWindow()
    window._attach_store(store)
    window.workflow_tabs.setCurrentIndex(0)
    window.manual_tabs.setCurrentIndex(1)
    _capture(window, "06-asset-breakdown.png", 1600, 920)


def _visual_review(reference: Path, current: Path) -> None:
    store = ProjectStore.create(FIXTURE / "中世纪村庄.scenelens", "中世纪村庄")
    store.save_art_brief(
        ArtBrief(
            scene_type="山地聚落",
            production_stage="灯光初版",
            target_style="写实风格化",
            time_weather="清晨薄雾",
            target_mood="宁静、神秘",
            primary_focus="中央主殿",
            secondary_focus="远山",
            preserve_content="建筑剪影",
            main_issues="焦点不够集中",
            excluded_review="材质微细节",
            constraints="使用现有资产",
        )
    )
    shot = store.create_shot("村口固定机位")
    store.import_reference(shot.id, reference)
    store.add_version(shot.id, current, "灯光 v1")
    store.close()
    window = MainWindow(RecentProjects(FIXTURE / "recent-projects.json"))
    controller = GlobalSettingsController(app)
    controller.register_window(window, "user_guide_visual_review")
    window.open_project(store.root)
    for _ in range(160):
        app.processEvents()
        if window._shared_palette_result is not None:
            break
        QTest.qWait(40)
    window.analysis_tabs.setCurrentIndex(2)
    _capture(
        window,
        "07-visual-review.png",
        1580,
        920,
        close_after=False,
    )
    window._comparison_generation += 1
    window._project_store = None
    window.close()
    app.processEvents()


def _review_control() -> None:
    store = ReviewCenterStore.open_or_create(FIXTURE / "review-center")
    store.add_task_from_handoff(
        {
            "title": "加强主殿与天空的剪影分离",
            "description": "缩略图下主塔轮廓不连续。",
            "acceptance_criteria": "25% 缩略图下轮廓保持连续可辨。",
            "priority": "high",
            "production_stage": "lighting_first",
            "source_module_id": "scenelens.visual_review",
            "source_project_id": "village",
            "source_project_title": "中世纪村庄",
            "source_entity_type": "review_finding",
            "source_entity_id": "silhouette",
        }
    )
    store.apply_gate_template(
        "lighting_first",
        source_project_id="village",
        source_project_title="中世纪村庄",
    )
    _capture(ReviewControlWindow(store), "08-review-control.png", 1500, 900)


if __name__ == "__main__":
    _safe_reset(FIXTURE)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT.glob("*.png"):
        old.unlink()
    os.environ["LOCALAPPDATA"] = str(FIXTURE / "local-app-data")
    settings = AppSettings(
        ui_language="zh-CN",
        theme_mode="dark",
        accent="teal",
        font_size=10,
        density="comfortable",
    )
    AppSettingsStore().save(settings)
    app = create_application([], settings)
    apply_appearance(app, settings)
    reference = FIXTURE / "山地聚落参考.png"
    current = FIXTURE / "山地聚落当前.png"
    _scene(reference)
    _scene(current, variant=1)
    _workspace_hub()
    _global_settings()
    _knowledge_base(reference)
    _comparative_study(reference, current)
    _artwork_study(reference)
    _asset_breakdown(reference)
    _visual_review(reference, current)
    _review_control()
    print(OUTPUT)
    app.quit()
