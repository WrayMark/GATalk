from __future__ import annotations

from pathlib import Path

from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.modules.review_control.storage import ReviewCenterStore
from scenelens.storage.recent_projects import RecentProjects
from scenelens.storage.workspace_catalog import (
    GlobalWorkspaceSearch,
    WorkspaceCatalogStore,
)


def test_global_search_finds_library_board_and_review_task(tmp_path: Path):
    library = KnowledgeLibraryStore.create(tmp_path / "资料库", "环境美术资料")
    library.add_link(
        "https://example.com/modular-kit",
        "山地神庙模块化套件",
        source_type="article",
    )
    library.add_visual_board("云海神庙方向板", purpose="屋顶层级与青绿色关系")
    catalog = WorkspaceCatalogStore(tmp_path / "catalog.json")
    catalog.remember(library.root)

    review = ReviewCenterStore.open_or_create(tmp_path / "review-center")
    review.add_task_from_handoff(
        {
            "title": "检查屋顶剪影层级",
            "description": "远景塔楼与主殿剪影粘连。",
            "source_module_id": "scenelens.artwork_study",
            "source_project_id": "study-1",
            "source_entity_type": "dimension_study",
            "source_entity_id": "silhouette",
        }
    )
    search = GlobalWorkspaceSearch(
        catalog,
        RecentProjects(tmp_path / "recent.json"),
        tmp_path / "review-center",
    )

    assert search.search("模块化套件")[0].entity_type == "knowledge_item"
    assert search.search("方向板")[0].entity_type == "visual_board"
    assert search.search("剪影层级")[0].entity_type == "review_task"


def test_workspace_catalog_relinks_moved_workspace(tmp_path: Path):
    old = KnowledgeLibraryStore.create(tmp_path / "old", "资料库")
    catalog = WorkspaceCatalogStore(tmp_path / "catalog.json")
    catalog.remember(old.root)
    new_root = tmp_path / "new"
    old.root.rename(new_root)

    replacement = catalog.relink(tmp_path / "old", new_root)

    assert Path(replacement.root) == new_root.resolve()
    assert len(catalog.load()) == 1
