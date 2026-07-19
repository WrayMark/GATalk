from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class EvidenceType(StrEnum):
    MEASUREMENT = "measurement"
    ALGORITHM_INFERENCE = "algorithm_inference"
    ART_JUDGMENT = "art_judgment"


class EvidenceSource(StrEnum):
    LOCAL_ANALYZER = "local_analyzer"
    AI_PROVIDER = "ai_provider"
    USER = "user"
    IMPORT = "import"


class TaskPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    DISMISSED = "dismissed"


class AIRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    DELETED = "deleted"


class QualityGateState(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AIConceptPreviewStatus(StrEnum):
    CANDIDATE = "candidate"
    CONCEPT_ONLY = "concept_only"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Project:
    id: str
    name: str


@dataclass(frozen=True)
class Asset:
    id: str
    sha256: str
    media_type: str


@dataclass(frozen=True)
class Shot:
    id: str
    project_id: str
    name: str


@dataclass(frozen=True)
class Version:
    id: str
    shot_id: str
    asset_id: str
    ordinal: int


@dataclass(frozen=True)
class Region:
    id: str
    module_id: str
    shot_id: str
    version_id: str | None
    geometry: Mapping[str, Any]
    semantic_type: str


@dataclass(frozen=True)
class Evidence:
    id: str
    module_id: str
    evidence_type: EvidenceType
    source: EvidenceSource
    subject_type: str
    subject_id: str
    payload: Mapping[str, Any]
    created_at: str
    shot_id: str | None = None
    version_id: str | None = None
    status: ArtifactStatus = ArtifactStatus.CURRENT


@dataclass(frozen=True)
class Annotation:
    id: str
    module_id: str
    annotation_type: str
    geometry: Mapping[str, Any]
    label: str
    created_at: str
    updated_at: str
    shot_id: str | None = None
    version_id: str | None = None
    evidence_id: str | None = None
    style: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Task:
    id: str
    module_id: str
    title: str
    description: str
    priority: TaskPriority
    status: TaskStatus
    created_at: str
    updated_at: str
    shot_id: str | None = None
    version_id: str | None = None
    source_evidence_id: str | None = None
    source_annotation_id: str | None = None
    verification: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DerivedArtifact:
    id: str
    module_id: str
    artifact_type: str
    relative_path: str
    input_hashes: Mapping[str, str]
    parameters: Mapping[str, Any]
    created_at: str
    shot_id: str | None = None
    version_id: str | None = None
    status: ArtifactStatus = ArtifactStatus.CURRENT


@dataclass(frozen=True)
class AIConceptPreview:
    id: str
    module_id: str
    shot_id: str
    source_version_id: str
    provider_id: str
    model_id: str
    relative_path: str
    input_hashes: Mapping[str, str]
    instruction: Mapping[str, Any]
    protection_constraints: Mapping[str, Any]
    validation_metrics: Mapping[str, Any]
    preview_status: AIConceptPreviewStatus
    created_at: str


@dataclass(frozen=True)
class AIRun:
    id: str
    module_id: str
    reviewer_id: str
    provider_id: str
    model_id: str
    capability: str
    request_hash: str
    input_manifest: Mapping[str, Any]
    status: AIRunStatus
    created_at: str
    output: Mapping[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class SourceDocument:
    id: str
    module_id: str
    document_type: str
    title: str
    source_uri: str
    content_hash: str
    metadata: Mapping[str, Any]
    created_at: str


@dataclass(frozen=True)
class ReviewProfile:
    id: str
    module_id: str
    name: str
    reviewer_ids: tuple[str, ...]
    settings: Mapping[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class QualityGate:
    id: str
    profile_id: str
    dimension_id: str
    display_name: str
    metric_key: str
    operator: str
    threshold: Mapping[str, Any]
    weight: float
    state: QualityGateState
    updated_at: str
