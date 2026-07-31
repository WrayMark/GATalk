from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import os
from pathlib import Path
from typing import Any, Mapping

from scenelens.storage.atomic import atomic_write_json, load_json


SETTINGS_FORMAT_VERSION = 1
THEME_MODES = {"system", "light", "dark"}
ACCENT_IDS = {"violet", "blue", "teal", "orange"}
DENSITY_MODES = {"compact", "comfortable", "spacious"}


@dataclass(frozen=True)
class AppSettings:
    theme_mode: str = "system"
    accent: str = "violet"
    font_size: int = 10
    density: str = "comfortable"
    remember_window_layout: bool = True
    window_layouts: Mapping[str, Mapping[str, str]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.theme_mode not in THEME_MODES:
            raise ValueError("全局设置中的主题模式无效。")
        if self.accent not in ACCENT_IDS:
            raise ValueError("全局设置中的强调色无效。")
        if not 9 <= int(self.font_size) <= 12:
            raise ValueError("全局设置中的界面字号无效。")
        if self.density not in DENSITY_MODES:
            raise ValueError("全局设置中的界面密度无效。")

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": SETTINGS_FORMAT_VERSION,
            **asdict(self),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AppSettings:
        layouts = value.get("window_layouts", {})
        if not isinstance(layouts, Mapping):
            layouts = {}
        normalized_layouts: dict[str, dict[str, str]] = {}
        for key, item in layouts.items():
            if not isinstance(item, Mapping):
                continue
            normalized_layouts[str(key)] = {
                "geometry": str(item.get("geometry", "")),
                "state": str(item.get("state", "")),
            }
        return cls(
            theme_mode=str(value.get("theme_mode", "system")),
            accent=str(value.get("accent", "violet")),
            font_size=int(value.get("font_size", 10)),
            density=str(value.get("density", "comfortable")),
            remember_window_layout=bool(
                value.get("remember_window_layout", True)
            ),
            window_layouts=normalized_layouts,
        )

    def with_window_layout(
        self,
        key: str,
        *,
        geometry: str,
        state: str,
    ) -> AppSettings:
        layouts = {
            str(name): dict(item)
            for name, item in self.window_layouts.items()
        }
        layouts[str(key)] = {
            "geometry": geometry,
            "state": state,
        }
        return replace(self, window_layouts=layouts)

    def without_window_layouts(self) -> AppSettings:
        return replace(self, window_layouts={})


def default_settings_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return base / "GATalk" / "settings.json"


class AppSettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_settings_path()

    def load(self) -> AppSettings:
        if not self.path.is_file():
            return AppSettings()
        try:
            value = load_json(self.path)
            version = int(value.get("format_version", 0))
            if version > SETTINGS_FORMAT_VERSION:
                return AppSettings()
            return AppSettings.from_dict(value)
        except (OSError, TypeError, ValueError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, settings.to_dict())

