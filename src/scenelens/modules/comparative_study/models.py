from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


STUDY_AXES = (
    "构图组织",
    "视觉层级",
    "明度结构",
    "色彩关系",
    "灯光组织",
    "空间层次",
    "形状语言",
    "边缘与细节",
    "材质表现",
    "叙事信息",
    "风格与技法",
    "情绪作用",
)


@dataclass(frozen=True)
class ComparativeStudyItem:
    item_id: str
    title: str
    relative_path: str
    sha256: str
    original_filename: str
    source_kind: str = "local_file"
    source_reference: str = ""
    role: str = "comparison"
    local_analysis: Mapping[str, Any] = field(default_factory=dict)
    user_observation: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ComparativeStudyItem:
        return cls(
            item_id=str(value["item_id"]),
            title=str(value.get("title", "未命名作品")),
            relative_path=str(value["relative_path"]),
            sha256=str(value["sha256"]),
            original_filename=str(value.get("original_filename", "")),
            source_kind=str(value.get("source_kind", "local_file")),
            source_reference=str(value.get("source_reference", "")),
            role=str(value.get("role", "comparison")),
            local_analysis=dict(value.get("local_analysis", {})),
            user_observation=str(value.get("user_observation", "")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


@dataclass(frozen=True)
class ComparativeStudyState:
    study_id: str
    title: str
    research_question: str = ""
    known_context: str = ""
    selected_axes: tuple[str, ...] = STUDY_AXES
    items: tuple[ComparativeStudyItem, ...] = ()
    active_item_ids: tuple[str, ...] = ()
    local_comparison: Mapping[str, Any] = field(default_factory=dict)
    ai_comparison: Mapping[str, Any] = field(default_factory=dict)
    ai_run: Mapping[str, Any] = field(default_factory=dict)
    ai_history: tuple[Mapping[str, Any], ...] = ()
    synthesis_notes: str = ""
    transferable_principles: str = ""
    limitations: str = ""
    knowledge_library_path: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "title": self.title,
            "research_question": self.research_question,
            "known_context": self.known_context,
            "selected_axes": list(self.selected_axes),
            "items": [item.to_dict() for item in self.items],
            "active_item_ids": list(self.active_item_ids),
            "local_comparison": dict(self.local_comparison),
            "ai_comparison": dict(self.ai_comparison),
            "ai_run": dict(self.ai_run),
            "ai_history": [dict(item) for item in self.ai_history],
            "synthesis_notes": self.synthesis_notes,
            "transferable_principles": self.transferable_principles,
            "limitations": self.limitations,
            "knowledge_library_path": self.knowledge_library_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ComparativeStudyState:
        return cls(
            study_id=str(value["study_id"]),
            title=str(value.get("title", "未命名对照研究")),
            research_question=str(value.get("research_question", "")),
            known_context=str(value.get("known_context", "")),
            selected_axes=tuple(
                str(item) for item in value.get("selected_axes", STUDY_AXES)
            ),
            items=tuple(
                ComparativeStudyItem.from_dict(item)
                for item in value.get("items", ())
            ),
            active_item_ids=tuple(
                str(item) for item in value.get("active_item_ids", ())
            ),
            local_comparison=dict(value.get("local_comparison", {})),
            ai_comparison=dict(value.get("ai_comparison", {})),
            ai_run=dict(value.get("ai_run", {})),
            ai_history=tuple(
                dict(item) for item in value.get("ai_history", ())
                if isinstance(item, Mapping)
            ),
            synthesis_notes=str(value.get("synthesis_notes", "")),
            transferable_principles=str(
                value.get("transferable_principles", "")
            ),
            limitations=str(value.get("limitations", "")),
            knowledge_library_path=str(value.get("knowledge_library_path", "")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )
