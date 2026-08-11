from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from scenelens.analysis.models import SharedPaletteResult
from scenelens.storage.recent_projects import RecentProjects
from scenelens.ui.main_window import MainWindow


def _save_split_image(
    path: Path,
    left: tuple[int, int, int],
    right: tuple[int, int, int],
    split: float,
) -> None:
    width, height = 480, 270
    image = Image.new("RGB", (width, height), right)
    image.paste(left, (0, 0, int(width * split), height))
    image.save(path)


@pytest.mark.slow
def test_m1b1_briefs_shared_palette_mask_and_luminance_restore(
    qtbot,
    tmp_path: Path,
):
    recent = RecentProjects(tmp_path / "local" / "recent.json")
    root = tmp_path / "中文 项目" / "村庄 M1B.scenelens"
    reference_path = tmp_path / "参考 图.png"
    current_path = tmp_path / "UE 当前.png"
    _save_split_image(
        reference_path,
        (35, 75, 115),
        (190, 125, 55),
        0.75,
    )
    _save_split_image(
        current_path,
        (35, 75, 115),
        (190, 125, 55),
        0.5,
    )

    window = MainWindow(recent)
    qtbot.addWidget(window)
    window.show()
    assert window.create_project(root, "中世纪村庄 M1B")
    assert window.create_shot("村口机位")
    assert window._project_store is not None
    project_document = (
        window._project_store.ensure_creative_intent_document()
    )
    assert window._save_user_brief_values(
        project_document.id,
        {
            "production_stage": "灯光初版",
            "time": "清晨",
            "weather": "薄雾",
            "target_moods": ["宁静", "异星感"],
        },
        {},
        "制作意图",
    )

    window._import_or_load("reference", str(reference_path))
    qtbot.waitUntil(
        lambda: window._asset_ids["reference"] is not None
        and window._active_jobs == 0,
        timeout=15_000,
    )
    window._import_or_load("current", str(current_path))
    qtbot.waitUntil(
        lambda: window._shared_palette_result is not None
        and window._active_jobs == 0,
        timeout=20_000,
    )

    shared = window._shared_palette_result
    assert shared is not None
    assert shared.reference_sample_count == shared.current_sample_count
    assert window.comparison_panel.palette_table.rowCount() >= 2
    assert window.comparison_panel.independent_palette_table.rowCount() >= 2
    assert window.comparison_panel.distribution_chart._reference
    assert window.comparison_panel.distribution_chart._current
    assert window.comparison_panel.luminance_table.item(0, 1) is not None

    previous_shared = window._shared_palette_result
    stale_generation = window._comparison_generation
    window._comparison_generation += 1
    window._on_worker_result(
        "comparison",
        "comparison",
        stale_generation,
        {"shared": SharedPaletteResult((), 0, 0)},
    )
    assert window._shared_palette_result is previous_shared

    # Cancel immediately: the stale background result must not restore an
    # overlay after the active tool generation has advanced.
    window._shared_palette_selected(0)
    window._clear_palette_mask()
    qtbot.waitUntil(lambda: window._active_jobs == 0, timeout=20_000)
    assert not window.reference_pane.canvas.has_overlay
    assert not window.current_pane.canvas.has_overlay

    window._shared_palette_selected(0)
    qtbot.waitUntil(
        lambda: window.reference_pane.canvas.has_overlay
        and window.current_pane.canvas.has_overlay
        and window._active_jobs == 0,
        timeout=20_000,
    )
    window._clear_palette_mask()
    assert not window.reference_pane.canvas.has_overlay
    assert not window.current_pane.canvas.has_overlay

    window._independent_palette_selected("reference", 0)
    qtbot.waitUntil(
        lambda: window.reference_pane.canvas.has_overlay
        and window._active_jobs == 0,
        timeout=20_000,
    )
    assert not window.current_pane.canvas.has_overlay
    window._clear_palette_mask()

    window.comparison_panel.set_thresholds(0.25, 0.75)
    window._comparison_thresholds_changed(0.25, 0.75)
    window.analysis_tabs.setCurrentIndex(2)
    qtbot.waitUntil(
        lambda: window._active_jobs == 0
        and window.comparison_panel.luminance_table.item(0, 1) is not None,
        timeout=20_000,
    )
    assert window._flush_autosave(show_error=True)

    shot_id = window._active_shot_id
    version_id = window._active_version_id
    assert shot_id is not None and version_id is not None
    reference_document = window._project_store.get_reference_visual_brief(
        shot_id
    )
    assert reference_document is not None
    reference_fields = window._project_store.list_brief_fields(
        reference_document.id
    )
    assert "image_dimensions" in reference_fields
    assert "oklab_palette" in reference_fields
    assert reference_document.asset_sha256 is not None
    assert window.close()

    reopened = MainWindow(recent)
    qtbot.addWidget(reopened)
    reopened.show()
    assert reopened.open_project(root)
    qtbot.waitUntil(
        lambda: reopened._shared_palette_result is not None
        and reopened._active_jobs == 0,
        timeout=20_000,
    )

    assert reopened.analysis_tabs.currentIndex() == 2
    assert reopened.comparison_panel.thresholds() == pytest.approx(
        (0.25, 0.75),
        abs=0.001,
    )
    document = reopened._project_store.get_creative_intent_document()
    assert document is not None
    fields = reopened._project_store.list_brief_fields(document.id)
    assert fields["production_stage"].value == "灯光初版"
    assert fields["target_moods"].value == ["宁静", "异星感"]
    assert fields["target_moods"].user_confirmed is True
    assert reopened._active_shot_id == shot_id
    assert reopened._active_version_id == version_id
