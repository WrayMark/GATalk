from pathlib import Path

from scenelens.storage.recent_projects import RecentProjects
from scenelens.ui.main_window import MainWindow


def test_silhouette_mode_and_threshold_restore(qtbot, tmp_path: Path) -> None:
    recent = RecentProjects(tmp_path / "recent.json")
    root = tmp_path / "灯光 观察.scenelens"
    window = MainWindow(recent)
    qtbot.addWidget(window)
    assert window.create_project(root, "灯光观察")
    window.mode_combo.setCurrentIndex(
        window.mode_combo.findData("silhouette")
    )
    window.silhouette_slider.setValue(62)
    assert window.silhouette_slider.isEnabled()
    assert window._flush_autosave(show_error=True)
    assert window.close()

    reopened = MainWindow(recent)
    qtbot.addWidget(reopened)
    assert reopened.open_project(root)
    assert reopened.mode_combo.currentData() == "silhouette"
    assert reopened.silhouette_slider.value() == 62
    assert reopened.silhouette_label.text() == "0.62"
