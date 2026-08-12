from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateTemplateItem:
    template_id: str
    name: str
    dimension: str
    acceptance_criteria: str
    required: bool = True


@dataclass(frozen=True)
class ProductionStagePreset:
    stage_id: str
    label: str
    gates: tuple[GateTemplateItem, ...]


PRODUCTION_STAGES = (
    ("concept_planning", "概念与规划"),
    ("blockout", "白盒"),
    ("asset_fill", "资产填充"),
    ("material", "材质制作"),
    ("lighting_first", "灯光初版"),
    ("atmosphere", "氛围调整"),
    ("final_polish", "最终展示"),
    ("custom", "自定义阶段"),
)


BUILTIN_GATE_PRESETS = (
    ProductionStagePreset(
        "concept_planning",
        "概念与规划",
        (
            GateTemplateItem(
                "concept.intent",
                "制作目标清楚",
                "制作意图",
                "目标风格、时间天气、情绪、焦点和暂不审阅内容已经确认。",
            ),
            GateTemplateItem(
                "concept.composition",
                "构图骨架可执行",
                "构图",
                "主体、动线和前中后景关系足以支持白盒搭建。",
            ),
            GateTemplateItem(
                "concept.scope",
                "制作范围可控",
                "范围",
                "核心资产、可复用套件和可简化内容已经界定。",
            ),
        ),
    ),
    ProductionStagePreset(
        "blockout",
        "白盒",
        (
            GateTemplateItem(
                "blockout.camera",
                "镜头和尺度稳定",
                "空间与镜头",
                "主要观察机位、尺度和主体占比已经稳定，可用于版本对照。",
            ),
            GateTemplateItem(
                "blockout.readability",
                "视觉层级成立",
                "视觉层级",
                "缩略图和灰度观察下，第一焦点与主要动线仍然清楚。",
            ),
            GateTemplateItem(
                "blockout.depth",
                "空间层次可读",
                "空间层次",
                "前景、中景和远景具有明确职能，没有关键遮挡冲突。",
            ),
        ),
    ),
    ProductionStagePreset(
        "asset_fill",
        "资产填充",
        (
            GateTemplateItem(
                "asset.coverage",
                "关键资产覆盖完整",
                "资产",
                "支撑主体、尺度、动线和叙事的关键资产均已进入场景。",
            ),
            GateTemplateItem(
                "asset.reuse",
                "复用和变体合理",
                "资产规划",
                "重复构件已使用套件或实例，显眼重复处具有必要变体。",
            ),
            GateTemplateItem(
                "asset.density",
                "细节密度受控",
                "细节密度",
                "细节集中服务焦点和叙事，非重点区域没有无目的堆叠。",
            ),
        ),
    ),
    ProductionStagePreset(
        "material",
        "材质制作",
        (
            GateTemplateItem(
                "material.separation",
                "材质分组可读",
                "材质",
                "主要材质类别通过明度、粗糙度或色彩响应清楚区分。",
            ),
            GateTemplateItem(
                "material.scale",
                "纹理尺度一致",
                "材质",
                "关键物体的纹理密度和尺度符合空间尺寸，不产生明显跳变。",
            ),
        ),
    ),
    ProductionStagePreset(
        "lighting_first",
        "灯光初版",
        (
            GateTemplateItem(
                "lighting.focus",
                "光照支持焦点",
                "灯光",
                "主光、局部对比和亮度分配支持第一视觉焦点。",
            ),
            GateTemplateItem(
                "lighting.exposure",
                "曝光保留信息",
                "曝光",
                "关键亮部和暗部没有影响阅读的溢出，曝光方向已确认。",
            ),
            GateTemplateItem(
                "lighting.depth",
                "灯光建立空间层次",
                "空间层次",
                "前中后景通过照明、雾或色温获得可读分离。",
            ),
        ),
    ),
    ProductionStagePreset(
        "atmosphere",
        "氛围调整",
        (
            GateTemplateItem(
                "atmosphere.intent",
                "氛围符合目标",
                "情绪与氛围",
                "时间、天气、空气状态和目标情绪与制作意图一致。",
            ),
            GateTemplateItem(
                "atmosphere.fog",
                "雾效不损害阅读",
                "雾与空气透视",
                "空气透视建立深度，同时保留主体轮廓和玩家路径信息。",
            ),
        ),
    ),
    ProductionStagePreset(
        "final_polish",
        "最终展示",
        (
            GateTemplateItem(
                "final.intent",
                "制作意图达成",
                "总体方向",
                "当前版本与已确认制作意图和参考目标没有关键偏离。",
            ),
            GateTemplateItem(
                "final.readability",
                "核心阅读稳定",
                "视觉层级",
                "原图、缩略图、灰度和模糊观察下，核心阅读顺序均保持稳定。",
            ),
            GateTemplateItem(
                "final.blockers",
                "阻塞问题清零",
                "交付",
                "阻塞级制作任务全部关闭，必需验收标准均有当前版本证据。",
            ),
        ),
    ),
)


def stage_label(stage_id: str) -> str:
    return dict(PRODUCTION_STAGES).get(stage_id, stage_id or "未指定")


def gate_preset(stage_id: str) -> ProductionStagePreset | None:
    return next(
        (item for item in BUILTIN_GATE_PRESETS if item.stage_id == stage_id),
        None,
    )
