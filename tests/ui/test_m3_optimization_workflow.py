from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QDialog, QMessageBox

from scenelens.modules.visual_review import MODULE_ID
from scenelens.storage.project_store import ProjectStore
from scenelens.storage.recent_projects import RecentProjects
from scenelens.storage.workbench_store import WorkbenchStore
from scenelens.ui.main_window import MainWindow


def _save_image(path: Path, left: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = np.zeros((96, 144, 3), dtype=np.uint8)
    rgb[:, :72] = left
    rgb[:, 72:] = (180, 125, 65)
    Image.fromarray(rgb, mode="RGB").save(path)


@pytest.mark.slow
def test_mock_concept_preview_is_saved_without_creating_version(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    recent = RecentProjects(tmp_path / "local" / "recent.json")
    root = tmp_path / "中文 项目" / "M3 预演.scenelens"
    reference_path = tmp_path / "图片" / "参考.png"
    current_path = tmp_path / "图片" / "当前.png"
    _save_image(reference_path, (35, 75, 115))
    _save_image(current_path, (55, 90, 125))

    window = MainWindow(recent)
    qtbot.addWidget(window)
    window.show()
    assert window.create_project(root, "M3 预演")
    assert window.create_shot("固定机位")
    window._import_or_load("reference", str(reference_path))
    qtbot.waitUntil(
        lambda: window._asset_ids["reference"] is not None
        and window._active_jobs == 0,
        timeout=15_000,
    )
    window._import_or_load("current", str(current_path))
    qtbot.waitUntil(
        lambda: window._asset_ids["current"] is not None
        and window._active_jobs == 0,
        timeout=15_000,
    )
    assert window._project_store is not None
    assert window._active_shot_id is not None
    assert window._active_version_id is not None
    versions_before = window._project_store.list_versions(
        window._active_shot_id
    )

    monkeypatch.setattr(
        "scenelens.ui.main_window.DataDisclosureDialog.exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    window._start_concept_preview(
        window.optimization_panel.concept_options()
    )
    qtbot.waitUntil(
        lambda: window._last_concept_preview is not None
        and window._active_jobs == 0,
        timeout=20_000,
    )

    previews = WorkbenchStore(
        window._project_store
    ).list_ai_concept_previews(
        MODULE_ID,
        shot_id=window._active_shot_id,
        source_version_id=window._active_version_id,
    )
    assert len(previews) == 1
    assert previews[0].relative_path.startswith(
        "artifacts/ai_previews/"
    )
    assert previews[0].source_version_id == window._active_version_id
    assert (
        window._project_store.list_versions(window._active_shot_id)
        == versions_before
    )
    assert window._last_concept_preview is not None
    assert window._last_concept_preview.id == previews[0].id

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window._confirm_concept_preview_tasks()
    tasks = WorkbenchStore(window._project_store).list_tasks(
        MODULE_ID,
        shot_id=window._active_shot_id,
        version_id=window._active_version_id,
    )
    assert len(tasks) == 1
    assert tasks[0].verification["requires_real_ue_version"] is True
    assert window.close()

    reopened = ProjectStore.open(root)
    try:
        restored = WorkbenchStore(
            reopened
        ).list_ai_concept_previews(
            MODULE_ID,
            shot_id=previews[0].shot_id,
            source_version_id=previews[0].source_version_id,
        )
        assert restored == previews
        assert len(
            reopened.list_versions(previews[0].shot_id)
        ) == len(versions_before)
    finally:
        reopened.close()
