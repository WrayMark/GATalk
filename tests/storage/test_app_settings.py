from pathlib import Path

from scenelens.storage.app_settings import AppSettings, AppSettingsStore


def test_global_settings_round_trip_with_chinese_path(tmp_path: Path) -> None:
    store = AppSettingsStore(tmp_path / "中文 设置" / "settings.json")
    settings = AppSettings(
        theme_mode="dark",
        accent="teal",
        font_size=11,
        density="compact",
        remember_window_layout=False,
    ).with_window_layout(
        "asset_breakdown",
        geometry="Z2VvbWV0cnk=",
        state="c3RhdGU=",
    )

    store.save(settings)

    assert store.load() == settings


def test_invalid_or_newer_settings_fall_back_safely(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        '{"format_version": 1, "theme_mode": "unknown"}',
        encoding="utf-8",
    )
    assert AppSettingsStore(path).load() == AppSettings()

    path.write_text(
        '{"format_version": 999, "theme_mode": "dark"}',
        encoding="utf-8",
    )
    assert AppSettingsStore(path).load() == AppSettings()


def test_clearing_layouts_keeps_appearance_settings() -> None:
    settings = AppSettings(
        theme_mode="light",
        accent="orange",
        font_size=12,
        density="spacious",
    ).with_window_layout("hub", geometry="one", state="two")

    cleared = settings.without_window_layouts()

    assert cleared.window_layouts == {}
    assert cleared.theme_mode == "light"
    assert cleared.accent == "orange"
    assert cleared.font_size == 12
    assert cleared.density == "spacious"
