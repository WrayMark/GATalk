from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


TASK_STATUSES = ("open", "in_progress", "done", "dismissed")
TASK_PRIORITIES = ("critical", "high", "medium", "low")
VERIFICATION_STATES = (
    "improved",
    "unchanged",
    "worse",
    "resolved",
    "insufficient_evidence",
)
GATE_STATES = ("not_evaluated", "pass", "warning", "fail", "insufficient_evidence")


@dataclass(frozen=True)
class ReviewTaskRecord:
    task_id: str
    title: str
    description: str
    acceptance_criteria: str
    priority: str
    status: str
    source_module_id: str
    source_project_id: str
    source_project_title: str
    source_project_path: str
    source_entity_type: str
    source_entity_id: str
    source_version_id: str = ""
    production_stage: str = ""
    blocked_by_task_ids: tuple[str, ...] = ()
    due_date: str = ""
    labels: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReviewTaskRecord:
        return cls(
            task_id=str(value["task_id"]),
            title=str(value.get("title", "未命名任务")),
            description=str(value.get("description", "")),
            acceptance_criteria=str(value.get("acceptance_criteria", "")),
            priority=_choice(value.get("priority"), TASK_PRIORITIES, "medium"),
            status=_choice(value.get("status"), TASK_STATUSES, "open"),
            source_module_id=str(value.get("source_module_id", "")),
            source_project_id=str(value.get("source_project_id", "")),
            source_project_title=str(value.get("source_project_title", "")),
            source_project_path=str(value.get("source_project_path", "")),
            source_entity_type=str(value.get("source_entity_type", "finding")),
            source_entity_id=str(value.get("source_entity_id", "")),
            source_version_id=str(value.get("source_version_id", "")),
            production_stage=str(value.get("production_stage", "")),
            blocked_by_task_ids=tuple(
                str(item)
                for item in value.get("blocked_by_task_ids", ())
            ),
            due_date=str(value.get("due_date", "")),
            labels=tuple(str(item) for item in value.get("labels", ())),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


@dataclass(frozen=True)
class TaskVerificationRecord:
    verification_id: str
    task_id: str
    version_label: str
    version_id: str
    state: str
    evidence_summary: str
    notes: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TaskVerificationRecord:
        return cls(
            verification_id=str(value["verification_id"]),
            task_id=str(value["task_id"]),
            version_label=str(value.get("version_label", "未命名版本")),
            version_id=str(value.get("version_id", "")),
            state=_choice(
                value.get("state"),
                VERIFICATION_STATES,
                "insufficient_evidence",
            ),
            evidence_summary=str(value.get("evidence_summary", "")),
            notes=str(value.get("notes", "")),
            created_at=str(value.get("created_at", "")),
        )


@dataclass(frozen=True)
class QualityGateRecord:
    gate_id: str
    name: str
    dimension: str
    acceptance_criteria: str
    required: bool
    source_project_id: str
    source_project_title: str
    source_project_path: str
    state: str = "not_evaluated"
    production_stage: str = ""
    template_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> QualityGateRecord:
        return cls(
            gate_id=str(value["gate_id"]),
            name=str(value.get("name", "未命名门禁")),
            dimension=str(value.get("dimension", "综合")),
            acceptance_criteria=str(value.get("acceptance_criteria", "")),
            required=bool(value.get("required", True)),
            source_project_id=str(value.get("source_project_id", "")),
            source_project_title=str(value.get("source_project_title", "")),
            source_project_path=str(value.get("source_project_path", "")),
            state=_choice(value.get("state"), GATE_STATES, "not_evaluated"),
            production_stage=str(value.get("production_stage", "")),
            template_id=str(value.get("template_id", "")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


@dataclass(frozen=True)
class GateEvaluationRecord:
    evaluation_id: str
    gate_id: str
    version_label: str
    version_id: str
    state: str
    evidence_summary: str
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GateEvaluationRecord:
        return cls(
            evaluation_id=str(value["evaluation_id"]),
            gate_id=str(value["gate_id"]),
            version_label=str(value.get("version_label", "未命名版本")),
            version_id=str(value.get("version_id", "")),
            state=_choice(value.get("state"), GATE_STATES, "insufficient_evidence"),
            evidence_summary=str(value.get("evidence_summary", "")),
            created_at=str(value.get("created_at", "")),
        )


@dataclass(frozen=True)
class ReviewCenterState:
    tasks: tuple[ReviewTaskRecord, ...] = ()
    verifications: tuple[TaskVerificationRecord, ...] = ()
    gates: tuple[QualityGateRecord, ...] = ()
    gate_evaluations: tuple[GateEvaluationRecord, ...] = ()
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [item.to_dict() for item in self.tasks],
            "verifications": [item.to_dict() for item in self.verifications],
            "gates": [item.to_dict() for item in self.gates],
            "gate_evaluations": [
                item.to_dict() for item in self.gate_evaluations
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReviewCenterState:
        return cls(
            tasks=tuple(
                ReviewTaskRecord.from_dict(item)
                for item in value.get("tasks", ())
            ),
            verifications=tuple(
                TaskVerificationRecord.from_dict(item)
                for item in value.get("verifications", ())
            ),
            gates=tuple(
                QualityGateRecord.from_dict(item)
                for item in value.get("gates", ())
            ),
            gate_evaluations=tuple(
                GateEvaluationRecord.from_dict(item)
                for item in value.get("gate_evaluations", ())
            ),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


def _choice(value: Any, choices: tuple[str, ...], fallback: str) -> str:
    text = str(value or "")
    return text if text in choices else fallback
