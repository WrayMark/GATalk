from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


MANIFEST_FORMAT = "scenelens.project"
MANIFEST_FORMAT_VERSION = 1
DATABASE_SCHEMA_VERSION = 6


class BriefDocumentType(StrEnum):
    CREATIVE_INTENT = "creative_intent"
    REFERENCE_VISUAL = "reference_visual"


class FieldSource(StrEnum):
    AUTOMATIC_MEASUREMENT = "automatic_measurement"
    ALGORITHM_INFERENCE = "algorithm_inference"
    AI_ANALYSIS = "ai_analysis"
    USER_INPUT = "user_input"
    USER_REVISION = "user_revision"


@dataclass(frozen=True)
class ProjectManifest:
    format: str
    format_version: int
    project_id: str
    name: str
    created_at: str
    updated_at: str
    app_version: str
    database_path: str = "project.db"
    database_schema_version: int = DATABASE_SCHEMA_VERSION
    assets_path: str = "assets"
    artifacts_path: str = "artifacts"
    exports_path: str = "exports"
    backups_path: str = "backups"

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "format_version": self.format_version,
            "project_id": self.project_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "app_version": self.app_version,
            "database": {
                "path": self.database_path,
                "schema_version": self.database_schema_version,
            },
            "directories": {
                "assets": self.assets_path,
                "artifacts": self.artifacts_path,
                "exports": self.exports_path,
                "backups": self.backups_path,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectManifest:
        try:
            database = data["database"]
            directories = data["directories"]
            return cls(
                format=str(data["format"]),
                format_version=int(data["format_version"]),
                project_id=str(data["project_id"]),
                name=str(data["name"]),
                created_at=str(data["created_at"]),
                updated_at=str(data["updated_at"]),
                app_version=str(data["app_version"]),
                database_path=str(database["path"]),
                database_schema_version=int(database["schema_version"]),
                assets_path=str(directories["assets"]),
                artifacts_path=str(directories["artifacts"]),
                exports_path=str(directories["exports"]),
                backups_path=str(directories["backups"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("project.json 缺少必需字段或字段类型不正确。") from exc


@dataclass(frozen=True)
class ArtBrief:
    scene_type: str = ""
    production_stage: str = ""
    target_style: str = ""
    time_weather: str = ""
    target_mood: str = ""
    primary_focus: str = ""
    secondary_focus: str = ""
    preserve_content: str = ""
    main_issues: str = ""
    excluded_review: str = ""
    constraints: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class BriefFieldValue:
    value: Any
    source: FieldSource
    confidence: float | None = None
    evidence: Any = None
    user_confirmed: bool = False
    updated_at: str = ""


@dataclass(frozen=True)
class BriefDocumentRecord:
    id: str
    document_type: BriefDocumentType
    project_id: str
    shot_id: str | None
    asset_id: str | None
    asset_sha256: str | None
    analyzer_id: str | None
    analyzer_version: str | None
    analyzed_at: str | None
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ComparisonAnalysisRecord:
    id: str
    shot_id: str
    version_id: str
    module_id: str
    analyzer_id: str
    analyzer_version: str
    reference_asset_id: str
    current_asset_id: str
    reference_sha256: str
    current_sha256: str
    parameters: dict[str, Any]
    cache_key: str
    result: dict[str, Any]
    evidence_type: str
    status: str
    created_at: str


@dataclass(frozen=True)
class ImageAssetRecord:
    id: str
    sha256: str
    original_filename: str
    stored_relpath: str
    byte_size: int
    media_type: str
    source_format: str
    width: int
    height: int
    exif_orientation: int | None
    icc_status: str
    imported_at: str

    def absolute_path(self, project_root: Path) -> Path:
        return project_root / Path(self.stored_relpath)


@dataclass(frozen=True)
class ShotRecord:
    id: str
    name: str
    reference_asset_id: str | None
    sort_order: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class VersionRecord:
    id: str
    shot_id: str
    asset_id: str
    ordinal: int
    name: str
    notes: str
    created_at: str


@dataclass(frozen=True)
class WorkspaceState:
    current_shot_id: str | None = None
    current_version_id: str | None = None
    display_mode: str = "original"
    comparison_mode: str = "split"
    ab_role: str = "reference"
    sync_views: bool = True
    blur_sigma: float = 0.0
    silhouette_threshold: float = 0.45
    three_threshold_low: float = 1.0 / 3.0
    three_threshold_high: float = 2.0 / 3.0
    five_thresholds: tuple[float, float, float, float] = (0.2, 0.4, 0.6, 0.8)
    palette_colours: int = 8
    palette_seed: int = 13_579
    palette_max_samples: int = 60_000
    active_analysis_tab: str = "reference"
    updated_at: str = ""


@dataclass(frozen=True)
class CanvasState:
    role: str
    shot_id: str
    version_id: str | None
    zoom_factor: float = 1.0
    center_x: float = 0.5
    center_y: float = 0.5
    updated_at: str = ""
