from scenelens.app import create_application
from scenelens.storage.app_settings import AppSettingsStore
from scenelens.ui.main_window import MainWindow
from scenelens.ui.settings_controller import GlobalSettingsController
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QToolBar
from pathlib import Path


def test_main_window_can_be_created(qtbot):
    app = create_application([])
    assert app.applicationName() == "GATalk"

    window = MainWindow()
    qtbot.addWidget(window)

    assert "GATalk" in window.windowTitle()

    controller = GlobalSettingsController(app)
    controller.register_window(window, "test_main")
    navigation = window.findChild(QToolBar, "gatalkGlobalNavigation")
    assert navigation is not None
    assert window.findChild(type(window.reference_button), "workspaceHomeButton").text().startswith("←")

    home_buttons = window.findChildren(QPushButton, "workspaceHomeButton")
    assert len(home_buttons) == 1
    assert all(
        action.text() != "工作台首页"
        for action in window.findChildren(QAction)
    )


def test_window_presentation_is_carried_between_workspaces(qtbot, tmp_path):
    app = QApplication.instance()
    controller = GlobalSettingsController(
        app,
        AppSettingsStore(tmp_path / "settings.json"),
    )
    source = QMainWindow()
    source.resize(1234, 777)
    target = QMainWindow()
    qtbot.addWidget(source)
    qtbot.addWidget(target)
    source.showMaximized()
    qtbot.waitUntil(source.isMaximized)

    presentation = controller.capture_window_presentation(source)
    controller.register_window(
        target,
        "presentation-target",
        presentation=presentation,
    )
    target.show()
    qtbot.waitUntil(target.isMaximized)

    assert presentation.maximized is True
    assert target.isMaximized()


def test_full_screen_presentation_is_carried_between_workspaces(qtbot, tmp_path):
    app = QApplication.instance()
    controller = GlobalSettingsController(
        app,
        AppSettingsStore(tmp_path / "settings.json"),
    )
    source = QMainWindow()
    target = QMainWindow()
    qtbot.addWidget(source)
    qtbot.addWidget(target)
    source.showFullScreen()
    qtbot.waitUntil(source.isFullScreen)

    presentation = controller.capture_window_presentation(source)
    controller.register_window(
        target,
        "full-screen-target",
        presentation=presentation,
    )
    target.show()
    qtbot.waitUntil(target.isFullScreen)

    assert presentation.full_screen is True
    assert target.isFullScreen()


def test_workspace_home_button_is_owned_by_global_navigation_only():
    source_root = Path(__file__).parents[1] / "src" / "scenelens"
    owners = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if 'QPushButton("←  工作台首页")' in text:
            owners.append(path.relative_to(source_root).as_posix())

    assert owners == ["ui/settings_controller.py"]
