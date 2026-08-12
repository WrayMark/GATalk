from scenelens.core.workspaces import WorkspaceDescriptor, WorkbenchRegistry
from scenelens.modules.review_control import MODULE_ID


def register_review_control_workbench(registry: WorkbenchRegistry) -> None:
    registry.register_workspace(
        WorkspaceDescriptor(
            module_id=MODULE_ID,
            workspace_id="review_control",
            display_name="制作任务与验收中心",
            version="0.18.0",
            level="platform",
            category="review-governance",
        )
    )
