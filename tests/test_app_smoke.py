from scenelens.app import create_application
from scenelens.ui.main_window import MainWindow
from scenelens.ui.settings_controller import GlobalSettingsController
from PySide6.QtWidgets import QToolBar


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
