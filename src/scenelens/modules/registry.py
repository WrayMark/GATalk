from __future__ import annotations

from scenelens.core.workspaces import WorkbenchRegistry
from scenelens.modules.artwork_study.workbench import (
    register_artwork_study_workbench,
)
from scenelens.modules.asset_breakdown.workbench import (
    register_asset_breakdown_workbench,
)
from scenelens.modules.comparative_study.workbench import (
    register_comparative_study_workbench,
)
from scenelens.modules.knowledge_base.workbench import (
    register_knowledge_base_workbench,
)
from scenelens.modules.review_control.workbench import (
    register_review_control_workbench,
)
from scenelens.modules.visual_review.workbench import (
    register_visual_review_workbench,
)


def create_builtin_workbench_registry() -> WorkbenchRegistry:
    registry = WorkbenchRegistry()
    register_knowledge_base_workbench(registry)
    register_review_control_workbench(registry)
    register_visual_review_workbench(registry)
    register_artwork_study_workbench(registry)
    register_asset_breakdown_workbench(registry)
    register_comparative_study_workbench(registry)
    return registry
