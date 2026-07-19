from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from scenelens.modules.visual_review import MODULE_ID


@dataclass(frozen=True)
class PresetOption:
    id: str
    label: str


@dataclass(frozen=True)
class FieldPreset:
    key: str
    input_mode: str
    allow_custom: bool
    options: tuple[PresetOption, ...]


class PresetCatalog:
    def __init__(self, fields_by_key: dict[str, FieldPreset]) -> None:
        self._fields_by_key = dict(fields_by_key)

    def field(self, key: str) -> FieldPreset:
        try:
            return self._fields_by_key[key]
        except KeyError as exc:
            raise KeyError(f"Unknown preset field: {key}") from exc

    def fields(self) -> tuple[FieldPreset, ...]:
        return tuple(self._fields_by_key.values())


def load_visual_review_presets() -> PresetCatalog:
    resource = files(
        "scenelens.modules.visual_review.config"
    ).joinpath("presets.json")
    data = json.loads(resource.read_text(encoding="utf-8"))
    _validate_catalog(data)
    fields_by_key: dict[str, FieldPreset] = {}
    for key, raw in data["fields"].items():
        fields_by_key[key] = FieldPreset(
            key=key,
            input_mode=str(raw["input_mode"]),
            allow_custom=bool(raw.get("allow_custom", True)),
            options=tuple(
                PresetOption(id=str(item["id"]), label=str(item["label"]))
                for item in raw.get("options", [])
            ),
        )
    return PresetCatalog(fields_by_key)


def _validate_catalog(data: dict[str, Any]) -> None:
    if data.get("format_version") != 1:
        raise ValueError("Unsupported preset configuration version.")
    if data.get("module_id") != MODULE_ID:
        raise ValueError("Preset configuration module_id does not match.")
    if not isinstance(data.get("fields"), dict):
        raise ValueError("Preset configuration requires a fields object.")
    for key, field in data["fields"].items():
        if not isinstance(key, str) or not isinstance(field, dict):
            raise ValueError("Invalid preset field entry.")
        if field.get("input_mode") not in {
            "editable_single",
            "editable_multi",
            "free_text",
        }:
            raise ValueError(f"Invalid input_mode for preset field: {key}")
        options = field.get("options", [])
        if not isinstance(options, list):
            raise ValueError(f"Options must be a list: {key}")
        ids = [str(item.get("id", "")) for item in options]
        if any(not option_id for option_id in ids) or len(ids) != len(set(ids)):
            raise ValueError(f"Preset IDs must be non-empty and unique: {key}")
