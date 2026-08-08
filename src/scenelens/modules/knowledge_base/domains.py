from __future__ import annotations

from scenelens.core.workspaces import KnowledgeDomainDescriptor


def built_in_knowledge_domains() -> tuple[KnowledgeDomainDescriptor, ...]:
    return (
        KnowledgeDomainDescriptor(
            "art_reference",
            "美术参考资料",
            "原画、截图、材质、灯光、构图与制作案例。",
            "1",
            True,
        ),
        KnowledgeDomainDescriptor(
            "level_design",
            "关卡设计资料",
            "空间组织、动线、节奏、遭遇与可读性资料。",
            "1",
            False,
        ),
        KnowledgeDomainDescriptor(
            "game_design",
            "策划与系统资料",
            "机制、系统、数值与叙事设计资料。",
            "1",
            False,
        ),
    )
