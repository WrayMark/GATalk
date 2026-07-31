from scenelens.app import create_application
from scenelens.ui.main_window import MainWindow


def test_main_window_can_be_created(qtbot):
    app = create_application([])
    assert app.applicationName() == "GATalk"

    window = MainWindow()
    qtbot.addWidget(window)

    assert "GATalk" in window.windowTitle()

