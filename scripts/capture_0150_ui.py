from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import shutil

import numpy as np
from PIL import Image

from scenelens.app import create_application
from scenelens.modules.asset_breakdown.production_handoff import (
    synchronize_production_specs,
)
from scenelens.modules.asset_breakdown.service import create_manual_asset
from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.asset_breakdown.ui.window import AssetBreakdownWindow
from scenelens.modules.knowledge_base.models import (
    VisualBoardCard,
    VisualBoardLink,
)
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.modules.knowledge_base.ui.board_window import VisualBoardWindow
from scenelens.modules.review_control.storage import ReviewCenterStore
from scenelens.modules.review_control.ui.window import ReviewControlWindow
from scenelens.storage.diagnostics import create_recovery_point, inspect_project
from scenelens.storage.recent_projects import RecentProjects
from scenelens.storage.workspace_catalog import (
    GlobalWorkspaceSearch,
    WorkspaceCatalogStore,
)
from scenelens.ui.diagnostics_dialog import DiagnosticsDialog
from scenelens.ui.global_search import GlobalSearchDialog
from scenelens.ui.workspace_hub import WorkspaceHubWindow


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".artifacts" / "screenshots-0150"
FIXTURE = ROOT / ".artifacts" / "ui-fixture-0150"


def capture(window, filename: str, width: int = 1480, height: int = 900) -> None:
    window.resize(width, height)
    window.show()
    app.processEvents()
    window.grab().save(str(OUTPUT / filename), "PNG")
    window.close()
    app.processEvents()


resolved = FIXTURE.resolve()
artifacts = (ROOT / ".artifacts").resolve()
if artifacts not in resolved.parents:
    raise RuntimeError("Refusing fixture cleanup outside .artifacts")
if FIXTURE.exists():
    shutil.rmtree(FIXTURE)
FIXTURE.mkdir(parents=True)
OUTPUT.mkdir(parents=True, exist_ok=True)
os.environ["LOCALAPPDATA"] = str(FIXTURE / "local-app-data")

rgb = np.zeros((540, 960, 3), dtype=np.uint8)
rgb[:, :320] = (24, 56, 82)
rgb[:, 320:690] = (78, 118, 96)
rgb[:, 690:] = (181, 131, 68)
source = FIXTURE / "云海神庙概念图.png"
Image.fromarray(rgb).save(source)

app = create_application([])

capture(WorkspaceHubWindow(), "01-workspace-hub.png")

library = KnowledgeLibraryStore.create(FIXTURE / "美术资料库", "环境美术资料库")
image_item = library.import_file(source, title="云海神庙概念图")
note_item = library.add_note(
    "建筑语言观察",
    body="塔楼形成垂直节奏；连廊负责横向组织与尺度过渡。",
)
board = library.add_visual_board("云海神庙方向板", purpose="梳理塔楼、连廊与屋顶节奏")
board = library.update_visual_board(
    replace(
        board,
        cards=(
            VisualBoardCard(
                "image-card",
                "knowledge_item",
                image_item.title,
                image_item.item_id,
                x=-430,
                y=-160,
                width=520,
                height=330,
            ),
            VisualBoardCard(
                "note-card",
                "knowledge_item",
                note_item.title,
                note_item.item_id,
                x=180,
                y=-80,
                width=330,
                height=210,
            ),
        ),
        links=(
            VisualBoardLink(
                "board-link",
                "image-card",
                "note-card",
                "形式归纳",
            ),
        ),
    )
)
library.snapshot_visual_board(board.board_id, "初版方向")
capture(VisualBoardWindow(library), "02-visual-reference-board.png")

asset_store = AssetBreakdownStore.create(FIXTURE / "神庙资产", "云海神庙资产规划")
main_image = asset_store.import_image(source, "main")
building = create_manual_asset(
    name="中央主殿",
    category="building",
    rect=(0.25, 0.18, 0.5, 0.55),
    source_image_id=main_image.image_id,
)
roof = replace(
    create_manual_asset(
        name="塔楼屋顶套件",
        category="modular_piece",
        rect=(0.36, 0.18, 0.28, 0.2),
        source_image_id=main_image.image_id,
    ),
    parent_asset_id=building.asset_id,
    production_priority="high",
    reuse_group="pagoda-roof-kit",
)
asset_store.add_or_replace_asset(building)
asset_store.add_or_replace_asset(roof)
asset_store.replace_production_specs(
    synchronize_production_specs((building, roof), ())
)
asset_window = AssetBreakdownWindow()
asset_window._attach_store(asset_store)
asset_window.manual_tabs.setCurrentIndex(3)
capture(asset_window, "03-asset-production-handoff.png")

review_store = ReviewCenterStore.open_or_create(FIXTURE / "review-center")
first = review_store.add_task_from_handoff(
    {
        "title": "稳定主殿与天空的剪影分离",
        "description": "主塔顶部与亮云层接近，缩略图下轮廓不连续。",
        "acceptance_criteria": "25% 缩略图下主塔轮廓仍连续可辨。",
        "priority": "high",
        "production_stage": "blockout",
        "source_module_id": "scenelens.visual_review",
        "source_project_id": "temple",
        "source_project_title": "云海神庙",
        "source_entity_type": "review_finding",
        "source_entity_id": "silhouette",
    }
)
review_store.add_task_from_handoff(
    {
        "title": "统一连廊模块尺度",
        "description": "先完成主殿尺度，再校准连廊柱距。",
        "acceptance_criteria": "柱距与人物尺度关系稳定。",
        "priority": "medium",
        "production_stage": "asset_fill",
        "blocked_by_task_ids": (first.task_id,),
        "source_module_id": "scenelens.asset_breakdown",
        "source_project_id": "temple",
        "source_project_title": "云海神庙",
        "source_entity_type": "asset",
        "source_entity_id": "corridor-kit",
    }
)
review_store.apply_gate_template(
    "blockout",
    source_project_id="temple",
    source_project_title="云海神庙",
)
capture(ReviewControlWindow(review_store), "04-review-production-control.png")

catalog = WorkspaceCatalogStore(FIXTURE / "catalog.json")
catalog.remember(library.root)
catalog.remember(asset_store.root)
search = GlobalWorkspaceSearch(
    catalog,
    RecentProjects(FIXTURE / "recent.json"),
    review_store.root,
)
search_dialog = GlobalSearchDialog(search)
search_dialog.search_edit.setText("神庙")
capture(search_dialog, "05-global-search.png", 1120, 720)

create_recovery_point(asset_store.root, label="release_candidate")
diagnostics = DiagnosticsDialog()
diagnostics._add_result(inspect_project(asset_store.root))
diagnostics.list.setCurrentRow(0)
capture(diagnostics, "06-project-recovery.png", 980, 620)

app.quit()
