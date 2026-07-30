import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from scenelens.modules.artwork_study.storage import ArtworkStudyStore
from scenelens.modules.artwork_study.ui.window import ArtworkStudyWindow
from scenelens.ui.workspace_hub import WorkspaceHubWindow


def test_workspace_hub_exposes_two_major_modules(qtbot):
    hub = WorkspaceHubWindow()
    qtbot.addWidget(hub)
    selected = []
    hub.workspace_selected.connect(selected.append)

    artwork_button = next(
        button
        for button in hub.findChildren(QPushButton)
        if button.text() == "进入作品研究"
    )
    qtbot.mouseClick(artwork_button, Qt.MouseButton.LeftButton)
    assert selected == ["artwork_study"]


def test_artwork_study_window_loads_analyzes_and_restores_project(
    qtbot, tmp_path
):
    source = tmp_path / "优秀 场景.png"
    rgb = np.zeros((80, 120, 3), dtype=np.uint8)
    rgb[:, :60] = (28, 54, 88)
    rgb[:, 60:] = (205, 142, 74)
    Image.fromarray(rgb).save(source)
    store = ArtworkStudyStore.create(
        tmp_path / "作品研究.scenelens-study",
        "作品研究",
    )
    store.import_image(source)

    window = ArtworkStudyWindow()
    qtbot.addWidget(window)
    window._set_store(ArtworkStudyStore.open(store.root))
    qtbot.waitUntil(
        lambda: window._local_analysis is not None,
        timeout=15_000,
    )

    assert window.canvas.has_image
    assert window.spatial_tree.topLevelItemCount() == 9
    assert "注意力代理" in window.local_summary.toPlainText()
    window.goal_edit.setPlainText("学习空间与色彩")
    window.notes_edit.setPlainText("个人判断")
    window._save_state(force=True)

    reopened = ArtworkStudyStore.open(store.root)
    assert reopened.state.study_goal == "学习空间与色彩"
    assert reopened.state.personal_notes == "个人判断"
    assert reopened.state.local_analysis["analyzer_id"]
