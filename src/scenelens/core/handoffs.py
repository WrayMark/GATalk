from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class WorkspaceHandoff:
    """Trusted in-process handoff between registered GATalk workspaces."""

    source_module_id: str
    source_workspace_id: str
    source_project_id: str
    source_project_title: str
    content_type: str
    primary_image_path: str
    primary_image_sha256: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.source_module_id or not self.source_project_id:
            raise ValueError("工作台交接缺少来源模块或项目 ID。")
        if not self.primary_image_path or not self.primary_image_sha256:
            raise ValueError("工作台交接缺少主图片。")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
