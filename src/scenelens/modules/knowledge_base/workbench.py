from scenelens.core.workspaces import WorkbenchRegistry, WorkspaceDescriptor
from scenelens.modules.knowledge_base import MODULE_ID, WORKSPACE_ID
from scenelens.modules.knowledge_base.domains import built_in_knowledge_domains


def register_knowledge_base_workbench(registry: WorkbenchRegistry) -> None:
    registry.register_workspace(
        WorkspaceDescriptor(
            module_id=MODULE_ID,
            workspace_id=WORKSPACE_ID,
            display_name="参考资料与知识库",
            version="0.14.0",
            level="platform",
            category="knowledge",
        )
    )
    for domain in built_in_knowledge_domains():
        registry.register_knowledge_domain(domain)
