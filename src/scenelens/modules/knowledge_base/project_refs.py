from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scenelens.storage.atomic import load_json


@dataclass(frozen=True)
class DetectedProject:
    project_type: str
    project_id: str
    title: str
    path: str
    module_id: str


def detect_gatalk_project(folder: str | Path) -> DetectedProject:
    root = Path(folder).resolve()
    candidates = (
        (
            "project.json",
            "scene_review",
            "scenelens.visual_review",
            "project_id",
            "name",
        ),
        (
            "study.json",
            "artwork_study",
            "scenelens.artwork_study",
            "study_id",
            "title",
        ),
        (
            "asset_project.json",
            "asset_breakdown",
            "scenelens.asset_breakdown",
            "project_id",
            "title",
        ),
        (
            "comparison.json",
            "comparative_study",
            "scenelens.comparative_study",
            "study_id",
            "title",
        ),
    )
    for filename, project_type, module_id, id_key, title_key in candidates:
        entry = root / filename
        if not entry.is_file():
            continue
        data = load_json(entry)
        state: dict[str, Any]
        if filename == "project.json":
            state = data
        else:
            state = dict(data.get("state", {}))
        return DetectedProject(
            project_type=project_type,
            project_id=str(state.get(id_key, "")),
            title=str(state.get(title_key, root.name)),
            path=str(root),
            module_id=module_id,
        )
    raise ValueError("所选目录不是可识别的 GATalk 项目。")
