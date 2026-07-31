from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow

from scenelens.storage.app_settings import AppSettings, AppSettingsStore
from scenelens.ui.settings_controller import GlobalSettingsController
from scenelens.ui.settings_dialog import GlobalSettingsDialog
from scenelens.ui.theme import apply_appearance, build_stylesheet, theme_tokens


def test_theme_tokens_produce_distinct_light_and_dark_styles(
    qapp: QApplication,
) -> None:
    settings = AppSettings(theme_mode="dark", accent="blue")
    dark = build_stylesheet(theme_tokens("dark", "blue"), settings)
    light = build_stylesheet(
        theme_tokens("light", "blue"),
        AppSettings(theme_mode="light", accent="blue"),
    )

    assert "#111318" in dark
    assert "#F4F5F8" in light
    assert dark != light
    assert apply_appearance(qapp, settings) == "dark"
    assert qapp.property("gatalkAccent") == "blue"


def test_settings_dialog_preserves_custom_values_and_clears_layouts(
    qtbot,
) -> None:
    source = AppSettings(
        theme_mode="light",
        accent="orange",
        font_size=12,
        density="spacious",
    ).with_window_layout("hub", geometry="one", state="two")
    dialog = GlobalSettingsDialog(source)
    qtbot.addWidget(dialog)

    assert dialog.current_settings() == source
    with qtbot.waitSignal(dialog.clear_layouts_requested):
        dialog._clear_layouts()
    assert dialog.current_settings().window_layouts == {}


def test_controller_registers_settings_action_and_persists_layout(
    qtbot,
    tmp_path: Path,
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    store = AppSettingsStore(tmp_path / "GATalk" / "settings.json")
    controller = GlobalSettingsController(app, store)
    window = QMainWindow()
    qtbot.addWidget(window)

    controller.register_window(window, "test_window")
    action = window.findChild(object, "globalSettingsAction")
    assert action is not None
    assert action.text() == "全局设置…"
    assert action.shortcut().toString() == "Ctrl+,"

    controller._save_window(window, "test_window")
    saved = store.load()
    assert saved.window_layouts["test_window"]["geometry"]
    assert saved.window_layouts["test_window"]["state"]
