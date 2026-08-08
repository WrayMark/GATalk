from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

import numpy as np
from PIL import Image

from scenelens.analysis.artwork_study import analyze_artwork
from scenelens.analysis.pipeline import measure_image
from scenelens.app import create_application
from scenelens.modules.comparative_study.analysis import build_local_comparison
from scenelens.modules.comparative_study.storage import ComparativeStudyStore
from scenelens.modules.comparative_study.ui.window import ComparativeStudyWindow
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.modules.knowledge_base.ui.window import KnowledgeBaseWindow
from scenelens.ui.workspace_hub import WorkspaceHubWindow


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".artifacts" / "screenshots-0130"
FIXTURE = ROOT / ".artifacts" / "ui-fixture-0130"


def _image(path: Path, left: tuple[int, int, int], right: tuple[int, int, int]) -> np.ndarray:
    rgb = np.empty((540, 960, 3), dtype=np.uint8)
    rgb[:, :480] = left
    rgb[:, 480:] = right
    Image.fromarray(rgb).save(path)
    return rgb


def _capture(window, filename: str) -> None:
    window.resize(1480, 900)
    window.show()
    app.processEvents()
    window.grab().save(str(OUTPUT / filename), "PNG")
    window.close()
    app.processEvents()


if FIXTURE.exists():
    shutil.rmtree(FIXTURE)
FIXTURE.mkdir(parents=True)
OUTPUT.mkdir(parents=True, exist_ok=True)
first_path = FIXTURE / "清晨薄雾.png"
second_path = FIXTURE / "夜景灯光.png"
first_rgb = _image(first_path, (35, 55, 70), (150, 165, 155))
second_rgb = _image(second_path, (8, 14, 26), (230, 110, 35))

app = create_application([])

hub = WorkspaceHubWindow()
_capture(hub, "01-workspace-hub.png")

library_store = KnowledgeLibraryStore.create(FIXTURE / "资料库", "环境美术资料库")
fog = library_store.add_collection("雾景与空气透视")
light = library_store.add_collection("夜景灯光")
library_store.import_file(first_path, collection_ids=(fog.collection_id,))
library_store.import_file(second_path, collection_ids=(light.collection_id,))
knowledge = KnowledgeBaseWindow()
knowledge._store = library_store
knowledge._load_state()
_capture(knowledge, "02-knowledge-library.png")

comparison_store = ComparativeStudyStore.create(FIXTURE / "对照研究", "气氛与焦点对照")
first = comparison_store.import_image(first_path, title="清晨薄雾")
second = comparison_store.import_image(second_path, title="夜景暖光")
first_analysis = analyze_artwork(
    first_rgb,
    measure_image(first_rgb, palette_colours=8),
).to_dict()
second_analysis = analyze_artwork(
    second_rgb,
    measure_image(second_rgb, palette_colours=8),
).to_dict()
local = build_local_comparison(
    ((first.title, first_analysis), (second.title, second_analysis))
)
comparison_store.save(
    replace(
        comparison_store.state,
        research_question="两种时段如何用明度与色温建立焦点和空间层次？",
        items=(
            replace(first, local_analysis=first_analysis),
            replace(second, local_analysis=second_analysis),
        ),
        local_comparison=local,
    )
)
comparison = ComparativeStudyWindow()
comparison._store = comparison_store
comparison._load_state()
_capture(comparison, "03-comparative-study.png")

app.quit()
