from __future__ import annotations

from importlib.resources import files
import json
from typing import Any


def load_artwork_study_presets() -> dict[str, Any]:
    resource = files(
        "scenelens.modules.artwork_study.config"
    ).joinpath("presets.json")
    data = json.loads(resource.read_text(encoding="utf-8"))
    if int(data.get("schema_version", 0)) != 1:
        raise ValueError("不支持的作品研究预设版本。")
    return data
