from scenelens.app import create_application
from scenelens.ui.main_window import MainWindow


def test_main_window_can_be_created(qtbot):
    app = create_application([])
    assert app.applicationName() == "SceneLens"

    window = MainWindow()
    qtbot.addWidget(window)

    assert "SceneLens" in window.windowTitle()

