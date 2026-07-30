from __future__ import annotations

from scenelens.core.workspaces import (
    WorkbenchRegistry,
    WorkspaceDescriptor,
)
from scenelens.modules.visual_review.reviews import (
    ArtDirectorReview,
    DeepArtDirectorReview,
    LightingReview,
)


def register_visual_review_workbench(
    registry: WorkbenchRegistry,
) -> None:
    registry.register_workspace(
        WorkspaceDescriptor(
            module_id="scenelens.visual_review",
            workspace_id="scene_art_control",
            display_name="游戏场景美术控制工作台",
            version="0.7.1",
        )
    )
    registry.register_reviewer(DeepArtDirectorReview())
    registry.register_reviewer(ArtDirectorReview())
    registry.register_reviewer(LightingReview())
