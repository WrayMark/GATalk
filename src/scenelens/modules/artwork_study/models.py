from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ArtworkStudyState:
    study_id: str
    title: str
    work_type: str = "environment_concept"
    study_goal: str = ""
    known_context: str = ""
    personal_notes: str = ""
    image_relative_path: str | None = None
    image_sha256: str | None = None
    image_filename: str | None = None
    created_at: str = ""
    updated_at: str = ""
    display_mode: str = "original"
    blur_sigma: float = 0.0
    silhouette_threshold: float = 0.45
    composition_guide: str = "none"
    zoom_factor: float = 1.0
    center_x: float = 0.5
    center_y: float = 0.5
    local_analysis: Mapping[str, Any] = field(default_factory=dict)
    ai_review: Mapping[str, Any] = field(default_factory=dict)
    ai_run: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ArtworkStudyState:
        required = {"study_id", "title", "created_at", "updated_at"}
        missing = required - set(value)
        if missing:
            raise ValueError(f"作品研究文件缺少字段：{sorted(missing)}")
        return cls(
            study_id=str(value["study_id"]),
            title=str(value["title"]),
            work_type=str(value.get("work_type", "environment_concept")),
            study_goal=str(value.get("study_goal", "")),
            known_context=str(value.get("known_context", "")),
            personal_notes=str(value.get("personal_notes", "")),
            image_relative_path=_optional_str(value.get("image_relative_path")),
            image_sha256=_optional_str(value.get("image_sha256")),
            image_filename=_optional_str(value.get("image_filename")),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            display_mode=str(value.get("display_mode", "original")),
            blur_sigma=float(value.get("blur_sigma", 0.0)),
            silhouette_threshold=float(value.get("silhouette_threshold", 0.45)),
            composition_guide=str(value.get("composition_guide", "none")),
            zoom_factor=float(value.get("zoom_factor", 1.0)),
            center_x=float(value.get("center_x", 0.5)),
            center_y=float(value.get("center_y", 0.5)),
            local_analysis=dict(value.get("local_analysis", {})),
            ai_review=dict(value.get("ai_review", {})),
            ai_run=dict(value.get("ai_run", {})),
        )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
