from scenelens.core.workspaces import WorkspaceDescriptor, WorkbenchRegistry
from scenelens.modules.review_control import MODULE_ID


def register_review_control_workbench(registry: WorkbenchRegistry) -> None:
    registry.register_workspace(
        WorkspaceDescriptor(
            module_id=MODULE_ID,
            workspace_id="review_control",
            display_name="审阅任务与质量门禁中心",
            version="0.14.0",
            level="platform",
            category="review-governance",
        )
    )
