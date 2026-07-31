from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping


ASSET_CATEGORIES = (
    "building",
    "modular_piece",
    "prop",
    "vegetation",
    "terrain",
    "material",
    "decal",
    "background",
    "lighting_vfx",
    "character_vehicle",
    "unknown",
)

EVIDENCE_KINDS = (
    "visible_evidence",
    "ai_inference",
    "user_added",
    "ai_generated_completion",
)


def validate_normalized_rect(
    value: tuple[float, float, float, float] | list[float],
) -> tuple[float, float, float, float]:
    if len(value) != 4:
        raise ValueError("区域坐标必须包含 x、y、width、height。")
    x, y, width, height = (float(item) for item in value)
    if (
        x < 0.0
        or y < 0.0
        or width <= 0.0
        or height <= 0.0
        or x + width > 1.000001
        or y + height > 1.000001
    ):
        raise ValueError("区域必须位于图片内，宽度和高度必须大于零。")
    return (
        max(0.0, min(1.0, x)),
        max(0.0, min(1.0, y)),
        max(0.0, min(1.0 - x, width)),
        max(0.0, min(1.0 - y, height)),
    )


@dataclass(frozen=True)
class SourceImage:
    image_id: str
    role: str
    relative_path: str
    sha256: str
    original_filename: str
    width: int
    height: int
    imported_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SourceImage:
        return cls(
            image_id=str(value["image_id"]),
            role=str(value["role"]),
            relative_path=str(value["relative_path"]),
            sha256=str(value["sha256"]),
            original_filename=str(value["original_filename"]),
            width=int(value.get("width", 0)),
            height=int(value.get("height", 0)),
            imported_at=str(value["imported_at"]),
        )


@dataclass(frozen=True)
class AssetItem:
    asset_id: str
    name: str
    category: str
    semantic_type: str
    parent_asset_id: str = ""
    level: int = 0
    normalized_rect: tuple[float, float, float, float] = (
        0.25,
        0.25,
        0.5,
        0.5,
    )
    evidence_kind: str = "visible_evidence"
    visible_evidence: str = ""
    inferred_details: str = ""
    uncertainty: str = ""
    confidence: float = 0.5
    occlusion_status: str = "none"
    reuse_group: str = ""
    instance_count: int = 1
    production_priority: str = "medium"
    production_strategy: str = ""
    module_pieces: tuple[str, ...] = ()
    variants: tuple[str, ...] = ()
    material_notes: str = ""
    selected_for_generation: bool = False
    user_modified: bool = False
    source_image_id: str = ""
    mask_relative_path: str = ""
    mask_method: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "normalized_rect",
            validate_normalized_rect(self.normalized_rect),
        )
        if self.category not in ASSET_CATEGORIES:
            object.__setattr__(self, "category", "unknown")
        if self.evidence_kind not in EVIDENCE_KINDS:
            raise ValueError("未知的资产信息来源。")
        object.__setattr__(
            self,
            "confidence",
            max(0.0, min(1.0, float(self.confidence))),
        )
        object.__setattr__(self, "instance_count", max(1, int(self.instance_count)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AssetItem:
        return cls(
            asset_id=str(value["asset_id"]),
            name=str(value["name"]),
            category=str(value.get("category", "unknown")),
            semantic_type=str(value.get("semantic_type", "")),
            parent_asset_id=str(value.get("parent_asset_id", "")),
            level=int(value.get("level", 0)),
            normalized_rect=tuple(
                float(item)
                for item in value.get(
                    "normalized_rect", (0.25, 0.25, 0.5, 0.5)
                )
            ),
            evidence_kind=str(value.get("evidence_kind", "visible_evidence")),
            visible_evidence=str(value.get("visible_evidence", "")),
            inferred_details=str(value.get("inferred_details", "")),
            uncertainty=str(value.get("uncertainty", "")),
            confidence=float(value.get("confidence", 0.5)),
            occlusion_status=str(value.get("occlusion_status", "none")),
            reuse_group=str(value.get("reuse_group", "")),
            instance_count=int(value.get("instance_count", 1)),
            production_priority=str(
                value.get("production_priority", "medium")
            ),
            production_strategy=str(value.get("production_strategy", "")),
            module_pieces=tuple(
                str(item) for item in value.get("module_pieces", ())
            ),
            variants=tuple(str(item) for item in value.get("variants", ())),
            material_notes=str(value.get("material_notes", "")),
            selected_for_generation=bool(
                value.get("selected_for_generation", False)
            ),
            user_modified=bool(value.get("user_modified", False)),
            source_image_id=str(value.get("source_image_id", "")),
            mask_relative_path=str(value.get("mask_relative_path", "")),
            mask_method=str(value.get("mask_method", "")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )

    def user_edit(self, *, updated_at: str, **changes: Any) -> AssetItem:
        return replace(
            self,
            **changes,
            user_modified=True,
            updated_at=updated_at,
        )


@dataclass(frozen=True)
class GenerationRecord:
    generation_id: str
    asset_id: str
    output_kind: str
    source_image_sha256: str
    source_rect: tuple[float, float, float, float]
    provider_id: str
    model_id: str
    parameters: Mapping[str, Any]
    relative_path: str
    status: str
    error_message: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GenerationRecord:
        return cls(
            generation_id=str(value["generation_id"]),
            asset_id=str(value["asset_id"]),
            output_kind=str(value["output_kind"]),
            source_image_sha256=str(value["source_image_sha256"]),
            source_rect=tuple(float(item) for item in value["source_rect"]),
            provider_id=str(value["provider_id"]),
            model_id=str(value["model_id"]),
            parameters=dict(value.get("parameters", {})),
            relative_path=str(value.get("relative_path", "")),
            status=str(value["status"]),
            error_message=str(value.get("error_message", "")),
            created_at=str(value["created_at"]),
        )


@dataclass(frozen=True)
class AutomaticAssetRun:
    """A self-contained one-click result, independent from the editable list."""

    run_id: str
    status: str
    source_image_sha256: str
    vision_provider_id: str
    vision_model_id: str
    image_provider_id: str
    image_model_id: str
    output_kind: str
    asset_limit: int
    assets: tuple[AssetItem, ...] = ()
    generations: tuple[GenerationRecord, ...] = ()
    board_relative_path: str = ""
    manifest_relative_path: str = ""
    repair_notes: tuple[str, ...] = ()
    error_summary: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AutomaticAssetRun:
        return cls(
            run_id=str(value["run_id"]),
            status=str(value.get("status", "completed")),
            source_image_sha256=str(value["source_image_sha256"]),
            vision_provider_id=str(value["vision_provider_id"]),
            vision_model_id=str(value["vision_model_id"]),
            image_provider_id=str(value["image_provider_id"]),
            image_model_id=str(value["image_model_id"]),
            output_kind=str(value.get("output_kind", "isolated_concept")),
            asset_limit=max(1, int(value.get("asset_limit", 16))),
            assets=tuple(
                AssetItem.from_dict(item)
                for item in value.get("assets", ())
            ),
            generations=tuple(
                GenerationRecord.from_dict(item)
                for item in value.get("generations", ())
            ),
            board_relative_path=str(value.get("board_relative_path", "")),
            manifest_relative_path=str(
                value.get("manifest_relative_path", "")
            ),
            repair_notes=tuple(
                str(item) for item in value.get("repair_notes", ())
            ),
            error_summary=str(value.get("error_summary", "")),
            created_at=str(value.get("created_at", "")),
        )


@dataclass(frozen=True)
class PromptMessage:
    message_id: str
    role: str
    content: str
    created_at: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant"}:
            raise ValueError("提示语会话消息角色无效。")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PromptMessage:
        return cls(
            message_id=str(value["message_id"]),
            role=str(value["role"]),
            content=str(value.get("content", "")),
            created_at=str(value["created_at"]),
        )


@dataclass(frozen=True)
class PromptRevision:
    revision_id: str
    origin: str
    title: str
    target_tool: str
    analysis_summary: str
    prompt_zh: str
    prompt_en: str
    negative_prompt: str
    constraints: tuple[str, ...] = ()
    asset_groups: tuple[Mapping[str, Any], ...] = ()
    change_summary: str = ""
    provider_id: str = ""
    model_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.origin not in {"ai", "user_edit"}:
            raise ValueError("提示语修订来源无效。")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PromptRevision:
        return cls(
            revision_id=str(value["revision_id"]),
            origin=str(value.get("origin", "ai")),
            title=str(value.get("title", "未命名提示语")),
            target_tool=str(value.get("target_tool", "generic")),
            analysis_summary=str(value.get("analysis_summary", "")),
            prompt_zh=str(value.get("prompt_zh", "")),
            prompt_en=str(value.get("prompt_en", "")),
            negative_prompt=str(value.get("negative_prompt", "")),
            constraints=tuple(
                str(item) for item in value.get("constraints", ())
            ),
            asset_groups=tuple(
                dict(item) for item in value.get("asset_groups", ())
            ),
            change_summary=str(value.get("change_summary", "")),
            provider_id=str(value.get("provider_id", "")),
            model_id=str(value.get("model_id", "")),
            created_at=str(value.get("created_at", "")),
        )


@dataclass(frozen=True)
class AssetPromptSession:
    session_id: str
    title: str
    source_image_sha256: str
    target_tool: str
    revisions: tuple[PromptRevision, ...] = ()
    messages: tuple[PromptMessage, ...] = ()
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AssetPromptSession:
        return cls(
            session_id=str(value["session_id"]),
            title=str(value.get("title", "未命名提示语")),
            source_image_sha256=str(value["source_image_sha256"]),
            target_tool=str(value.get("target_tool", "generic")),
            revisions=tuple(
                PromptRevision.from_dict(item)
                for item in value.get("revisions", ())
            ),
            messages=tuple(
                PromptMessage.from_dict(item)
                for item in value.get("messages", ())
            ),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )

    @property
    def current_revision(self) -> PromptRevision | None:
        return self.revisions[-1] if self.revisions else None


@dataclass(frozen=True)
class AssetBreakdownState:
    project_id: str
    title: str
    scene_type: str = "general_environment"
    production_goal: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    source_images: tuple[SourceImage, ...] = ()
    assets: tuple[AssetItem, ...] = ()
    generations: tuple[GenerationRecord, ...] = ()
    automatic_runs: tuple[AutomaticAssetRun, ...] = ()
    prompt_sessions: tuple[AssetPromptSession, ...] = ()
    ai_runs: tuple[Mapping[str, Any], ...] = ()
    exports: tuple[Mapping[str, Any], ...] = ()
    selected_asset_id: str = ""
    zoom_factor: float = 1.0
    center_x: float = 0.5
    center_y: float = 0.5
    regions_visible: bool = True
    selected_prompt_session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AssetBreakdownState:
        required = {"project_id", "title", "created_at", "updated_at"}
        missing = required - set(value)
        if missing:
            raise ValueError(f"资产拆分项目缺少字段：{sorted(missing)}")
        return cls(
            project_id=str(value["project_id"]),
            title=str(value["title"]),
            scene_type=str(value.get("scene_type", "general_environment")),
            production_goal=str(value.get("production_goal", "")),
            notes=str(value.get("notes", "")),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            source_images=tuple(
                SourceImage.from_dict(item)
                for item in value.get("source_images", ())
            ),
            assets=tuple(
                AssetItem.from_dict(item) for item in value.get("assets", ())
            ),
            generations=tuple(
                GenerationRecord.from_dict(item)
                for item in value.get("generations", ())
            ),
            automatic_runs=tuple(
                AutomaticAssetRun.from_dict(item)
                for item in value.get("automatic_runs", ())
            ),
            prompt_sessions=tuple(
                AssetPromptSession.from_dict(item)
                for item in value.get("prompt_sessions", ())
            ),
            ai_runs=tuple(dict(item) for item in value.get("ai_runs", ())),
            exports=tuple(dict(item) for item in value.get("exports", ())),
            selected_asset_id=str(value.get("selected_asset_id", "")),
            zoom_factor=float(value.get("zoom_factor", 1.0)),
            center_x=float(value.get("center_x", 0.5)),
            center_y=float(value.get("center_y", 0.5)),
            regions_visible=bool(value.get("regions_visible", True)),
            selected_prompt_session_id=str(
                value.get("selected_prompt_session_id", "")
            ),
        )

    @property
    def main_image(self) -> SourceImage | None:
        return next(
            (image for image in self.source_images if image.role == "main"),
            None,
        )
