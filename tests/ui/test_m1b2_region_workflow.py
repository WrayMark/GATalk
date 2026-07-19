from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from scenelens.storage.recent_projects import RecentProjects
from scenelens.ui.main_window import MainWindow


def _save_split_image(
    path: Path,
    left: tuple[int, int, int],
    right: tuple[int, int, int],
    split: float,
) -> None:
    image = Image.new("RGB", (640, 360), right)
    image.paste(left, (0, 0, int(640 * split), 360))
    image.save(path)


@pytest.mark.slow
def test_m1b2_region_pair_analysis_mask_version_copy_and_restore(
    qtbot,
    tmp_path: Path,
):
    recent = RecentProjects(tmp_path / "local" / "recent.json")
    root = tmp_path / "中文 项目" / "村庄 M1B2.scenelens"
    reference_path = tmp_path / "参考 构图.png"
    current_1_path = tmp_path / "UE 当前 v1.png"
    current_2_path = tmp_path / "UE 当前 v2.png"
    _save_split_image(
        reference_path,
        (30, 70, 115),
        (195, 130, 55),
        0.65,
    )
    _save_split_image(
        current_1_path,
        (45, 80, 120),
        (180, 115, 45),
        0.52,
    )
    _save_split_image(
        current_2_path,
        (55, 85, 125),
        (170, 105, 40),
        0.48,
    )

    window = MainWindow(recent)
    qtbot.addWidget(window)
    window.show()
    assert window.create_project(root, "中世纪村庄 M1B.2")
    assert window.create_shot("村口固定机位")
    window._import_or_load("reference", str(reference_path))
    qtbot.waitUntil(
        lambda: window._asset_ids["reference"] is not None
        and window._active_jobs == 0,
        timeout=15_000,
    )
    window._import_or_load("current", str(current_1_path))
    qtbot.waitUntil(
        lambda: window._shared_palette_result is not None
        and window._active_jobs == 0,
        timeout=20_000,
    )
    first_version_id = window._active_version_id
    assert first_version_id is not None

    reference = window.region_controller.create_region(
        "reference",
        (0.05, 0.1, 0.55, 0.75),
        "村庄主体参考",
        "主体",
    )
    current = window.region_controller.create_region(
        "current",
        (0.12, 0.12, 0.5, 0.72),
        "村庄主体当前",
        "主体",
    )
    pair = window.region_controller.pair_selected_regions(
        "村庄主体",
        "主体",
        "比较主体层级",
    )
    qtbot.waitUntil(
        lambda: window._active_region_analysis is not None
        and window._active_region_analysis[0] == pair.id
        and window._active_jobs == 0,
        timeout=20_000,
    )

    analysis = window._active_region_analysis[1]
    assert sum(
        analysis.reference.shared_palette_proportions
    ) == pytest.approx(1.0)
    assert sum(
        analysis.current.shared_palette_proportions
    ) == pytest.approx(1.0)
    assert window.region_panel.metrics_table.rowCount() >= 13
    assert window.region_panel.region_palette_table.rowCount() >= 2
    assert window.region_controller.store is not None
    assert (
        window.region_controller.store.latest_analysis(pair.id).status
        == "complete"
    )

    window.comparison_panel.set_thresholds(0.3, 0.7)
    window._comparison_thresholds_changed(0.3, 0.7)
    assert (
        window.region_controller.store.latest_analysis(pair.id).status
        == "stale"
    )
    qtbot.waitUntil(
        lambda: window._active_jobs == 0
        and window.region_controller.store.latest_analysis(pair.id).status
        == "complete",
        timeout=20_000,
    )
    assert window._active_region_analysis[1].low_threshold == pytest.approx(
        0.3
    )

    window._region_palette_selected(0)
    qtbot.waitUntil(
        lambda: window.reference_pane.canvas.has_overlay
        and window.current_pane.canvas.has_overlay
        and window._active_jobs == 0,
        timeout=20_000,
    )
    window._escape_current_tool()
    assert not window.reference_pane.canvas.has_overlay
    assert not window.current_pane.canvas.has_overlay

    stale_generation = window._region_analysis_generation
    window._region_analysis_generation += 1
    previous = window._active_region_analysis
    window._on_worker_result(
        "comparison",
        "region_analysis",
        stale_generation,
        {"result": analysis},
    )
    assert window._active_region_analysis is previous

    window._import_or_load("current", str(current_2_path))
    qtbot.waitUntil(
        lambda: window._active_version_id not in {None, first_version_id}
        and window._shared_palette_result is not None
        and window._active_jobs == 0,
        timeout=20_000,
    )
    second_version_id = window._active_version_id
    assert window.region_controller.store.list_pair_views(
        window._active_shot_id,
        second_version_id,
    ) == ()
    window.region_controller.copy_previous_version()
    copied_views = window.region_controller.store.list_pair_views(
        window._active_shot_id,
        second_version_id,
    )
    assert len(copied_views) == 1
    assert copied_views[0].reference_region.id == reference.id
    assert copied_views[0].current_region.id != current.id
    assert "检查" in window.statusBar().currentMessage()

    window.region_controller._list_selected("pair", copied_views[0].pair.id)
    qtbot.waitUntil(
        lambda: window._active_region_analysis is not None
        and window._active_region_analysis[0] == copied_views[0].pair.id
        and window._active_jobs == 0,
        timeout=20_000,
    )
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
    restored_views = reopened.region_controller.store.list_pair_views(
        reopened._active_shot_id,
        reopened._active_version_id,
    )
    assert len(restored_views) == 1
    assert reopened.region_panel.table.rowCount() == 1
    reopened.region_controller._list_selected(
        "pair",
        restored_views[0].pair.id,
    )
    qtbot.waitUntil(
        lambda: reopened._active_region_analysis is not None
        and reopened._active_jobs == 0,
        timeout=20_000,
    )
    assert "恢复" in reopened.statusBar().currentMessage()
