from __future__ import annotations

from importlib.resources import files
import json
from typing import Any, Mapping


def load_scene_profiles() -> Mapping[str, Any]:
    resource = files(
        "scenelens.modules.asset_breakdown.config"
    ).joinpath("scene_profiles.json")
    return json.loads(resource.read_text(encoding="utf-8"))

