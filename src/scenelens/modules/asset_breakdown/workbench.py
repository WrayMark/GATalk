from scenelens.core.workspaces import WorkbenchRegistry, WorkspaceDescriptor
from scenelens.modules.asset_breakdown import MODULE_ID, WORKSPACE_ID
from scenelens.modules.asset_breakdown.prompt_workshop import (
    AssetPromptWorkshopReview,
)
from scenelens.modules.asset_breakdown.reviews import AssetBreakdownReview


def register_asset_breakdown_workbench(
    registry: WorkbenchRegistry,
) -> None:
    registry.register_workspace(
        WorkspaceDescriptor(
            module_id=MODULE_ID,
            workspace_id=WORKSPACE_ID,
            display_name="资产拆分工作台",
            version="0.9.0",
        )
    )
    registry.register_reviewer(AssetBreakdownReview())
    registry.register_reviewer(AssetPromptWorkshopReview())
