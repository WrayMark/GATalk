from PySide6.QtWidgets import QPushButton

from scenelens.modules.comparative_study.ui.window import ComparativeStudyWindow
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.modules.knowledge_base.ui.board_window import VisualBoardWindow
from scenelens.modules.knowledge_base.ui.window import KnowledgeBaseWindow
from scenelens.modules.review_control.ui.window import ReviewControlWindow
from scenelens.storage.recent_projects import RecentProjects
from scenelens.storage.workspace_catalog import (
    GlobalWorkspaceSearch,
    WorkspaceCatalogStore,
)
from scenelens.ui.global_search import GlobalSearchDialog
from scenelens.ui.workspace_hub import WorkspaceHubWindow


def test_hub_presents_knowledge_as_platform_before_professional_workbenches(qtbot):
    hub = WorkspaceHubWindow()
    qtbot.addWidget(hub)
    labels = [button.text() for button in hub.findChildren(QPushButton)]

    assert "进入参考资料与知识库" in labels
    assert "进入制作任务与验收中心" in labels
    assert "进入作品研究集合与对照研究" in labels
    assert "进入作品研究" in labels


def test_new_workspaces_can_be_constructed_offline(qtbot, tmp_path):
    knowledge = KnowledgeBaseWindow()
    comparison = ComparativeStudyWindow()
    from scenelens.modules.review_control.storage import ReviewCenterStore

    review = ReviewControlWindow(
        ReviewCenterStore.open_or_create(tmp_path / "review-center")
    )
    qtbot.addWidget(knowledge)
    qtbot.addWidget(comparison)
    qtbot.addWidget(review)

    assert "参考资料与知识库" in knowledge.windowTitle()
    assert "作品研究集合与对照研究" in comparison.windowTitle()
    assert comparison.provider_combo.count() > 0
    assert "制作任务与验收中心" in review.windowTitle()


def test_review_control_accepts_cross_module_handoff(qtbot, tmp_path):
    from scenelens.modules.review_control.storage import ReviewCenterStore

    store = ReviewCenterStore.open_or_create(tmp_path / "review-center")
    window = ReviewControlWindow(store)
    qtbot.addWidget(window)

    task = window.receive_handoff(
        {
            "title": "复查天空与主体的明度分离",
            "source_module_id": "scenelens.visual_review",
            "source_project_id": "project-1",
            "source_entity_type": "review_finding",
            "source_entity_id": "finding-1",
        }
    )

    assert task.title == "复查天空与主体的明度分离"
    assert window.task_tree.topLevelItemCount() == 1


def test_visual_board_window_opens_saved_board(qtbot, tmp_path):
    store = KnowledgeLibraryStore.create(tmp_path / "资料库", "环境资料")
    board = store.add_visual_board("山谷灯光方向板", purpose="检查明暗层级")

    window = VisualBoardWindow(store)
    qtbot.addWidget(window)

    assert window.board_combo.currentData() == board.board_id
    assert window.purpose_edit.text() == "检查明暗层级"


def test_global_search_dialog_lists_registered_content(qtbot, tmp_path):
    store = KnowledgeLibraryStore.create(tmp_path / "资料库", "环境资料")
    store.add_note("云海塔楼剪影", body="检查主塔与天空分离。")
    catalog = WorkspaceCatalogStore(tmp_path / "catalog.json")
    catalog.remember(store.root)
    service = GlobalWorkspaceSearch(
        catalog,
        RecentProjects(tmp_path / "recent.json"),
        tmp_path / "review-center",
    )

    dialog = GlobalSearchDialog(service)
    qtbot.addWidget(dialog)
    dialog.search_edit.setText("塔楼剪影")

    assert dialog.results.topLevelItemCount() == 1
    assert dialog.results.topLevelItem(0).text(1) == "资料"
