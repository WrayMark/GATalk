from scenelens.core.workspaces import WorkbenchRegistry, WorkspaceDescriptor
from scenelens.modules.artwork_study import MODULE_ID, WORKSPACE_ID
from scenelens.modules.artwork_study.reviews import ArtworkMasterStudyReview


def register_artwork_study_workbench(registry: WorkbenchRegistry) -> None:
    registry.register_workspace(
        WorkspaceDescriptor(
            module_id=MODULE_ID,
            workspace_id=WORKSPACE_ID,
            display_name="作品研究",
            version="0.7.0",
        )
    )
    registry.register_reviewer(ArtworkMasterStudyReview())
