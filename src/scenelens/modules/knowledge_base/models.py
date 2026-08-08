from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class KnowledgeItem:
    item_id: str
    domain_id: str
    item_type: str
    title: str
    source_kind: str
    source_type: str = "other"
    source_value: str = ""
    local_relative_path: str | None = None
    sha256: str | None = None
    original_filename: str | None = None
    creator: str = ""
    project_name: str = ""
    description: str = ""
    notes: str = ""
    original_text: str = ""
    translation_text: str = ""
    translation_language: str = "zh-CN"
    translation_source: str = ""
    translation_provider_id: str = ""
    translation_model_id: str = ""
    translation_updated_at: str = ""
    parent_item_id: str | None = None
    normalized_rect: tuple[float, float, float, float] | None = None
    derived_kind: str = ""
    tags: tuple[str, ...] = ()
    provenance_status: str = "unverified"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> KnowledgeItem:
        return cls(
            item_id=str(value["item_id"]),
            domain_id=str(value.get("domain_id", "art_reference")),
            item_type=str(value.get("item_type", "image")),
            title=str(value.get("title", "未命名资料")),
            source_kind=str(value.get("source_kind", "manual")),
            source_type=str(value.get("source_type", "other")),
            source_value=str(value.get("source_value", "")),
            local_relative_path=_optional(value.get("local_relative_path")),
            sha256=_optional(value.get("sha256")),
            original_filename=_optional(value.get("original_filename")),
            creator=str(value.get("creator", "")),
            project_name=str(value.get("project_name", "")),
            description=str(value.get("description", "")),
            notes=str(value.get("notes", "")),
            original_text=str(value.get("original_text", "")),
            translation_text=str(value.get("translation_text", "")),
            translation_language=str(
                value.get("translation_language", "zh-CN")
            ),
            translation_source=str(value.get("translation_source", "")),
            translation_provider_id=str(
                value.get("translation_provider_id", "")
            ),
            translation_model_id=str(
                value.get("translation_model_id", "")
            ),
            translation_updated_at=str(
                value.get("translation_updated_at", "")
            ),
            parent_item_id=_optional(value.get("parent_item_id")),
            normalized_rect=_optional_rect(value.get("normalized_rect")),
            derived_kind=str(value.get("derived_kind", "")),
            tags=tuple(str(item) for item in value.get("tags", ())),
            provenance_status=str(value.get("provenance_status", "unverified")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


@dataclass(frozen=True)
class KnowledgeCollection:
    collection_id: str
    domain_id: str
    name: str
    parent_id: str | None = None
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> KnowledgeCollection:
        return cls(
            collection_id=str(value["collection_id"]),
            domain_id=str(value.get("domain_id", "art_reference")),
            name=str(value.get("name", "未命名集合")),
            parent_id=_optional(value.get("parent_id")),
            description=str(value.get("description", "")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


@dataclass(frozen=True)
class KnowledgeProjectReference:
    reference_id: str
    item_id: str
    project_type: str
    project_id: str
    project_title: str
    project_path: str
    module_id: str = ""
    entity_type: str = "project"
    entity_id: str = ""
    note: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> KnowledgeProjectReference:
        return cls(
            reference_id=str(value["reference_id"]),
            item_id=str(value["item_id"]),
            project_type=str(value.get("project_type", "unknown")),
            project_id=str(value.get("project_id", "")),
            project_title=str(value.get("project_title", "")),
            project_path=str(value.get("project_path", "")),
            module_id=str(value.get("module_id", "")),
            entity_type=str(value.get("entity_type", "project")),
            entity_id=str(value.get("entity_id", "")),
            note=str(value.get("note", "")),
            created_at=str(value.get("created_at", "")),
        )


@dataclass(frozen=True)
class VisualBoardCard:
    card_id: str
    card_type: str
    title: str
    knowledge_item_id: str | None = None
    note: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 260.0
    height: float = 190.0
    colour: str = "#2F7D8C"
    z_index: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.card_type not in {"knowledge_item", "note", "group"}:
            object.__setattr__(self, "card_type", "note")
        object.__setattr__(self, "width", max(120.0, min(1200.0, self.width)))
        object.__setattr__(self, "height", max(80.0, min(900.0, self.height)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> VisualBoardCard:
        return cls(
            card_id=str(value["card_id"]),
            card_type=str(value.get("card_type", "note")),
            title=str(value.get("title", "未命名卡片")),
            knowledge_item_id=_optional(value.get("knowledge_item_id")),
            note=str(value.get("note", "")),
            x=float(value.get("x", 0.0)),
            y=float(value.get("y", 0.0)),
            width=float(value.get("width", 260.0)),
            height=float(value.get("height", 190.0)),
            colour=str(value.get("colour", "#2F7D8C")),
            z_index=int(value.get("z_index", 0)),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


@dataclass(frozen=True)
class VisualBoardLink:
    link_id: str
    source_card_id: str
    target_card_id: str
    label: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> VisualBoardLink:
        return cls(
            link_id=str(value["link_id"]),
            source_card_id=str(value["source_card_id"]),
            target_card_id=str(value["target_card_id"]),
            label=str(value.get("label", "")),
            created_at=str(value.get("created_at", "")),
        )


@dataclass(frozen=True)
class VisualBoardSnapshot:
    snapshot_id: str
    title: str
    cards: tuple[VisualBoardCard, ...]
    links: tuple[VisualBoardLink, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "title": self.title,
            "cards": [item.to_dict() for item in self.cards],
            "links": [item.to_dict() for item in self.links],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> VisualBoardSnapshot:
        return cls(
            snapshot_id=str(value["snapshot_id"]),
            title=str(value.get("title", "未命名快照")),
            cards=tuple(
                VisualBoardCard.from_dict(item)
                for item in value.get("cards", ())
            ),
            links=tuple(
                VisualBoardLink.from_dict(item)
                for item in value.get("links", ())
            ),
            created_at=str(value.get("created_at", "")),
        )


@dataclass(frozen=True)
class VisualReferenceBoard:
    board_id: str
    title: str
    purpose: str = ""
    cards: tuple[VisualBoardCard, ...] = ()
    links: tuple[VisualBoardLink, ...] = ()
    snapshots: tuple[VisualBoardSnapshot, ...] = ()
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "board_id": self.board_id,
            "title": self.title,
            "purpose": self.purpose,
            "cards": [item.to_dict() for item in self.cards],
            "links": [item.to_dict() for item in self.links],
            "snapshots": [item.to_dict() for item in self.snapshots],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> VisualReferenceBoard:
        return cls(
            board_id=str(value["board_id"]),
            title=str(value.get("title", "未命名资料板")),
            purpose=str(value.get("purpose", "")),
            cards=tuple(
                VisualBoardCard.from_dict(item)
                for item in value.get("cards", ())
            ),
            links=tuple(
                VisualBoardLink.from_dict(item)
                for item in value.get("links", ())
            ),
            snapshots=tuple(
                VisualBoardSnapshot.from_dict(item)
                for item in value.get("snapshots", ())
            ),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


@dataclass(frozen=True)
class KnowledgeLibraryState:
    library_id: str
    title: str
    active_domain_id: str = "art_reference"
    items: tuple[KnowledgeItem, ...] = ()
    collections: tuple[KnowledgeCollection, ...] = ()
    memberships: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    project_references: tuple[KnowledgeProjectReference, ...] = ()
    visual_boards: tuple[VisualReferenceBoard, ...] = ()
    selected_collection_id: str | None = None
    selected_board_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "library_id": self.library_id,
            "title": self.title,
            "active_domain_id": self.active_domain_id,
            "items": [item.to_dict() for item in self.items],
            "collections": [item.to_dict() for item in self.collections],
            "memberships": {
                key: list(value) for key, value in self.memberships.items()
            },
            "project_references": [
                item.to_dict() for item in self.project_references
            ],
            "visual_boards": [
                item.to_dict() for item in self.visual_boards
            ],
            "selected_collection_id": self.selected_collection_id,
            "selected_board_id": self.selected_board_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> KnowledgeLibraryState:
        return cls(
            library_id=str(value["library_id"]),
            title=str(value.get("title", "参考资料库")),
            active_domain_id=str(value.get("active_domain_id", "art_reference")),
            items=tuple(
                KnowledgeItem.from_dict(item)
                for item in value.get("items", ())
            ),
            collections=tuple(
                KnowledgeCollection.from_dict(item)
                for item in value.get("collections", ())
            ),
            memberships={
                str(key): tuple(str(item) for item in values)
                for key, values in dict(value.get("memberships", {})).items()
            },
            project_references=tuple(
                KnowledgeProjectReference.from_dict(item)
                for item in value.get("project_references", ())
            ),
            visual_boards=tuple(
                VisualReferenceBoard.from_dict(item)
                for item in value.get("visual_boards", ())
            ),
            selected_collection_id=_optional(
                value.get("selected_collection_id")
            ),
            selected_board_id=_optional(value.get("selected_board_id")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


def _optional(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_rect(
    value: Any,
) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("局部截图坐标格式无效。")
    rect = tuple(float(item) for item in value)
    return rect[0], rect[1], rect[2], rect[3]
