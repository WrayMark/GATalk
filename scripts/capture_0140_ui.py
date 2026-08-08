from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

import numpy as np
from PIL import Image

from scenelens.app import create_application
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.modules.knowledge_base.ui.window import KnowledgeBaseWindow
from scenelens.modules.review_control.storage import ReviewCenterStore
from scenelens.modules.review_control.ui.window import ReviewControlWindow
from scenelens.storage.project_store import ProjectStore
from scenelens.ui.workspace_hub import WorkspaceHubWindow


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".artifacts" / "screenshots-0140"
FIXTURE = ROOT / ".artifacts" / "ui-fixture-0140"


def _capture(window, filename: str) -> None:
    window.resize(1480, 900)
    window.show()
    app.processEvents()
    window.grab().save(str(OUTPUT / filename), "PNG")
    window.close()
    app.processEvents()


resolved_fixture = FIXTURE.resolve()
resolved_artifacts = (ROOT / ".artifacts").resolve()
if resolved_artifacts not in resolved_fixture.parents:
    raise RuntimeError("Refusing fixture cleanup outside .artifacts")
if FIXTURE.exists():
    shutil.rmtree(FIXTURE)
FIXTURE.mkdir(parents=True)
OUTPUT.mkdir(parents=True, exist_ok=True)

rgb = np.zeros((540, 960, 3), dtype=np.uint8)
rgb[:, :480] = (24, 52, 75)
rgb[:, 480:] = (176, 132, 72)
source = FIXTURE / "中世纪村庄清晨.png"
Image.fromarray(rgb).save(source)

app = create_application([])

hub = WorkspaceHubWindow()
_capture(hub, "01-workspace-hub.png")

scene_store = ProjectStore.create(
    FIXTURE / "中世纪村庄.scenelens",
    "中世纪村庄",
)
scene_store.close()
library_store = KnowledgeLibraryStore.create(
    FIXTURE / "环境美术资料库",
    "环境美术资料库",
)
collection = library_store.add_collection("建筑与清晨气氛")
item = library_store.import_file(
    source,
    collection_ids=(collection.collection_id,),
    title="中世纪村庄清晨概念图",
)
library_store.update_item(
    replace(
        item,
        creator="示例作者",
        project_name="中世纪村庄研究",
        tags=("建筑语言", "空气透视", "清晨"),
        description="用于研究主体建筑、空间层次和清晨雾气的关系。",
        original_text="Environment design study: modular architecture and morning fog.",
        translation_text="环境设计研究：模块化建筑与清晨雾气。",
        translation_source="AI 翻译（已核对）",
        translation_provider_id="mock",
        translation_model_id="mock-json-v1",
    )
)
library_store.create_image_excerpt(
    item.item_id,
    (0.5, 0.15, 0.35, 0.55),
    title="主体建筑与雾层局部",
)
library_store.add_project_reference(
    item.item_id,
    project_type="scene_review",
    project_id=scene_store.manifest.project_id,
    project_title=scene_store.manifest.name,
    project_path=str(scene_store.root),
    module_id="scenelens.visual_review",
    note="作为清晨薄雾与主体层级参考",
)
knowledge = KnowledgeBaseWindow()
knowledge._store = library_store
knowledge._load_state()
knowledge._select_item(item.item_id)
_capture(knowledge, "02-knowledge-library.png")

review_store = ReviewCenterStore.open_or_create(FIXTURE / "review-control")
task = review_store.add_task_from_handoff(
    {
        "title": "加强主体建筑与天空的明度分离",
        "description": "主体上缘与亮天空接近，缩略图下轮廓不稳定。",
        "acceptance_criteria": "缩略图下主体轮廓连续，次要高光不抢第一焦点。",
        "priority": "high",
        "source_module_id": "scenelens.visual_review",
        "source_project_id": scene_store.manifest.project_id,
        "source_project_title": scene_store.manifest.name,
        "source_project_path": str(scene_store.root),
        "source_entity_type": "review_finding",
        "source_entity_id": "finding-value-separation",
        "source_version_id": "v1",
        "labels": ["明度", "主体层级"],
    }
)
review_store.add_verification(
    task.task_id,
    version_label="UE 截图 v2",
    version_id="v2",
    state="improved",
    evidence_summary="主体上缘明度差扩大，轮廓更连续；右侧高光仍需复核。",
)
gate = review_store.add_gate(
    name="主体第一读取顺序",
    dimension="视觉层级",
    acceptance_criteria="25% 缩略图下主体仍为第一视觉焦点。",
    required=True,
    source_project_id=scene_store.manifest.project_id,
    source_project_title=scene_store.manifest.name,
    source_project_path=str(scene_store.root),
)
review_store.evaluate_gate(
    gate.gate_id,
    version_label="UE 截图 v2",
    version_id="v2",
    state="warning",
    evidence_summary="主体可辨，但右侧高光仍有竞争。",
)
review = ReviewControlWindow(review_store)
_capture(review, "03-review-control.png")

app.quit()
