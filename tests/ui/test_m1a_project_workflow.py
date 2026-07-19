from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from scenelens.storage.models import ArtBrief
from scenelens.storage.errors import ProjectSaveError
from scenelens.storage.recent_projects import RecentProjects
from scenelens.ui.main_window import MainWindow


def _save_image(path: Path, colour: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (480, 270), colour).save(path)


@pytest.mark.slow
def test_m1a_create_save_reopen_add_and_switch_version(qtbot, tmp_path: Path):
    recent = RecentProjects(tmp_path / "local" / "recent-projects.json")
    project_root = tmp_path / "中文 项目" / "中世纪村庄.scenelens"
    reference_path = tmp_path / "真实 图片" / "概念参考.png"
    current_v1_path = tmp_path / "真实 图片" / "UE 清晨 v1.png"
    current_v2_path = tmp_path / "真实 图片" / "UE 清晨 v2.png"
    _save_image(reference_path, (65, 95, 120))
    _save_image(current_v1_path, (90, 105, 115))
    _save_image(current_v2_path, (105, 115, 120))

    first = MainWindow(recent)
    qtbot.addWidget(first)
    first.show()
    assert first.create_project(project_root, "中世纪村庄")
    brief = ArtBrief(
        scene_type="中世纪村庄",
        production_stage="灯光初版",
        target_style="写实风格化",
        time_weather="清晨薄雾",
        target_mood="宁静、神秘",
        primary_focus="村口钟楼",
        secondary_focus="远山",
        preserve_content="建筑剪影",
        main_issues="视觉焦点不集中",
        excluded_review="材质微细节",
        constraints="仅使用现有资产",
    )
    assert first.save_art_brief(brief)
    assert first.create_shot("村口固定机位")
    shot_id = first._active_shot_id
    assert shot_id is not None

    first._import_or_load("reference", str(reference_path))
    qtbot.waitUntil(
        lambda: first._asset_ids["reference"] is not None
        and first._active_jobs == 0,
        timeout=15_000,
    )
    first._import_or_load("current", str(current_v1_path))
    qtbot.waitUntil(
        lambda: first._active_version_id is not None
        and first._asset_ids["current"] is not None
        and first._active_jobs == 0,
        timeout=15_000,
    )
    first_version_id = first._active_version_id
    assert first_version_id is not None

    first.mode_combo.setCurrentIndex(first.mode_combo.findData("grayscale"))
    first.comparison_combo.setCurrentIndex(
        first.comparison_combo.findData("ab")
    )
    first.blur_slider.setValue(25)
    first.reference_pane.canvas.apply_external_view_state(1.7, 0.3, 0.65)
    first.current_pane.canvas.apply_external_view_state(1.7, 0.3, 0.65)
    first._mark_workspace_dirty()
    assert first._flush_autosave(show_error=True)
    assert first.close()

    reopened = MainWindow(recent)
    qtbot.addWidget(reopened)
    reopened.show()
    assert reopened.open_project(project_root)
    qtbot.waitUntil(
        lambda: set(reopened._images) == {"reference", "current"}
        and reopened._active_jobs == 0,
        timeout=15_000,
    )

    assert reopened._project_store is not None
    assert reopened._project_store.get_art_brief() == brief
    assert reopened._active_shot_id == shot_id
    assert reopened._active_version_id == first_version_id
    assert reopened.mode_combo.currentData() == "grayscale"
    assert reopened.comparison_combo.currentData() == "ab"
    assert reopened.blur_slider.value() == 25
    assert "色板采样" in reopened.analysis_widgets[
        "current"
    ].sample_label.text()
    assert current_v1_path.name in reopened.analysis_widgets[
        "current"
    ].info_label.text()
    assert reopened.analysis_tabs.count() == 5
    assert reopened.project_dock.isVisible()

    reopened._import_or_load("current", str(current_v2_path))
    qtbot.waitUntil(
        lambda: reopened._active_version_id not in {None, first_version_id}
        and reopened._active_jobs == 0,
        timeout=15_000,
    )
    assert len(reopened._project_store.list_versions(shot_id)) == 2

    reopened._activate_version(shot_id, first_version_id)
    qtbot.waitUntil(
        lambda: reopened._active_version_id == first_version_id
        and reopened._active_jobs == 0,
        timeout=15_000,
    )
    assert "色板采样" in reopened.analysis_widgets[
        "current"
    ].sample_label.text()

    recent_items = recent.load()
    assert recent_items[0].name == "中世纪村庄"
    assert recent_items[0].is_available


def test_autosave_failure_keeps_workspace_dirty(qtbot, tmp_path: Path, monkeypatch):
    recent = RecentProjects(tmp_path / "local" / "recent-projects.json")
    window = MainWindow(recent)
    qtbot.addWidget(window)
    assert window.create_project(
        tmp_path / "保存保护.scenelens",
        "保存保护",
    )
    assert window.create_shot("镜头")
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("grayscale"))
    assert window._workspace_dirty
    assert window._project_store is not None

    def fail_save(_state):
        raise ProjectSaveError("simulated save failure")

    monkeypatch.setattr(
        window._project_store,
        "save_workspace_state",
        fail_save,
    )
    assert not window._save_workspace(show_error=False)
    assert window._workspace_dirty
    assert "修改仍保留" in window.statusBar().currentMessage()
    # Avoid opening the intentional close-protection dialog during qtbot cleanup.
    window._autosave_timer.stop()
    window._workspace_dirty = False
