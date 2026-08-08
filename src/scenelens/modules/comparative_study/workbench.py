from scenelens.core.workspaces import (
    HandoffDescriptor,
    WorkbenchRegistry,
    WorkspaceDescriptor,
)
from scenelens.modules.comparative_study import MODULE_ID, WORKSPACE_ID
from scenelens.modules.comparative_study.reviews import ComparativeArtworkReview


def register_comparative_study_workbench(registry: WorkbenchRegistry) -> None:
    registry.register_workspace(
        WorkspaceDescriptor(
            module_id=MODULE_ID,
            workspace_id=WORKSPACE_ID,
            display_name="作品研究集合与对照研究",
            version="0.14.0",
            level="professional",
            parent_workspace_id="reference_knowledge",
            category="study",
        )
    )
    registry.register_handoff(
        HandoffDescriptor(
            source_workspace_id="reference_knowledge",
            target_workspace_id=WORKSPACE_ID,
            payload_type="knowledge_items",
            display_name="从资料库建立对照研究",
        )
    )
    registry.register_reviewer(ComparativeArtworkReview())
    registry.register_handoff(
        HandoffDescriptor(
            source_workspace_id="artwork_study",
            target_workspace_id=WORKSPACE_ID,
            payload_type="artwork_study",
            display_name="加入对照研究",
        )
    )
