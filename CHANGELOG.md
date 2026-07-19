# Changelog

## Unreleased

### Added

- 增加 AI 主美 Pro 与游戏场景灯光分析竞品审查，明确许可证和独立实现边界。
- 增加 schema v5 的 Evidence、Annotation、Task、DerivedArtifact、AIRun、
  SourceDocument、ReviewProfile 和 QualityGate 共享持久化。
- 增加受信任内置 Workspace、Reviewer 和 Provider 的显式注册机制及示例模块
  契约测试。
- 增加百炼、SiliconFlow、OpenAI、Gemini 和 xAI 的视觉审阅适配器，以及
  万相、Nano Banana、GPT Image 和 Grok Imagine 的 M3 编辑能力位置。
- 增加 Windows Credential Manager 凭据存储、发送清单、后台取消/超时/重试
  和错误脱敏。
- 增加完全离线的 Mock Provider 与各供应商录制传输契约测试。
- 增加同项目跨进程单写者锁、只读打开和异常退出陈旧锁恢复。
- 增加模块化分析器契约、注册表和 `scenelens.visual_review` 模块边界。
- 增加制作意图与参考图视觉简报的字段来源、可信度、依据和用户确认数据模型。
- 增加 SQLite schema v2 迁移及模块级预设配置加载。
- 增加制作意图与参考图视觉简报编辑界面，支持预设、自定义值、来源和用户确认。
- 增加参考图尺寸、宽高比、ICC、Oklab 色板、明度、三阶/五阶、色相和饱和度
  自动关联。
- 增加双方等量采样的共享 Oklab 色板、占比差和可恢复分析记录。
- 增加独立/共享色板来源遮罩、Esc 退出和过期后台结果保护。
- 增加可调阈值的三阶明度比例、百分点差和双方缩略图。
- 增加 Reference Visual Brief v1 JSON Schema 作为未来 AI 交换边界。
- 增加 schema v4 的归一化矩形区域、成对区域和区域分析记录。
- 增加区域模式、矩形创建/移动/缩放/删除、配对列表和叠层显隐。
- 增加按 Version 保存区域及复制上一 Version 区域。
- 增加成对区域的线性明度、P10/P50/P90、Oklab、彩度、中性色与色相统计。
- 增加全图共享色板在区域内的组成差异和双方区域限定颜色遮罩。
- 增加区域分析缓存、明确过期状态和快速切换 Version 的旧任务保护。

### Changed

- M1B.2 已通过用户真实项目人工试用并冻结。
- 项目版本进入 `0.3.0a0`；模块连接改由数据库模块注册记录校验。
- 分析记录开始保存 `module_id`、`analyzer_id` 和分析器版本。
- M1A 的 Art Brief 在 M1B 中文产品语义中更名为“制作意图”。
- 项目数据库升级为 schema v3，模块数据版本升级为 2。
- 工作区开始恢复右侧活动页签和三阶明度阈值。
- M1B.1 已通过用户真实项目人工试用并冻结。
- 项目数据库升级为 schema v4，模块数据版本升级为 3。
- 区域工作流从应用外壳拆入 `scenelens.visual_review` 模块控制器。

### Validation

- M1B.0 开发回归当前 40 项测试通过，包含真实子进程锁、schema v1 → v2
  迁移、字段覆盖保护、参考图哈希变化过期和预设加载。
- Windows `onedir` 构建与内部烟测通过，模块预设配置已随包收集。
- M1B.1 完整回归 47 项通过，包含共享色板等量采样、固定中心遮罩、
  schema v2 → v3、Brief 自动关联、保存重开和过期任务隔离。
- M1B.1 Windows `onedir` 构建与内部烟测通过，预设和 JSON Schema 均已随包收集。
- M1B.2A 完整回归 62 项通过，覆盖 EXIF 纠正归一化坐标、区域画布交互、
  配对恢复、Version 复制独立性、过期标记和 schema v3 → v4 迁移备份。
- M1B.2 候选版完整回归 70 项通过；4K 双区域基准约 0.98 秒。
- Windows `onedir` 约 253.9 MiB，打包烟测退出码为 0，并实际覆盖区域
  创建、配对、分析保存和恢复。
- M2 schema v5 基础切片完整回归 75 项通过，包含 v2/v3/v4 迁移备份和共享
  实体离线往返。

## 0.1.0 — 2026-07-19

### Added

- 完成 `project.json` + SQLite schema v1 的混合项目存储。
- 完成 Project → Shot → Version、项目级 Art Brief 和最近项目列表。
- 导入图片时保留原始字节并记录 SHA-256、EXIF、ICC 与工作尺寸。
- 完成自动保存、原子清单更新、迁移前备份和高版本只拒绝写入保护。
- 完成当前 Shot/Version、显示模式、模糊、A/B、同步视图与缩放平移恢复。
- 完成分析记录缓存、证据类型标记及可删除 artifact 重建。
- 增加左侧项目导航和右侧参考/截图/对比/任务四类面板。

### Changed

- M1A 通过真实项目人工验收并冻结为 `0.1.0`。
- 打包内部烟测现在同时覆盖图片分析、SQLite 项目创建、资产导入与重开。

### Validation

- M0.5 原有 19 项回归测试继续通过。
- 当前完整测试套件 31 项通过，包括保存失败、迁移回滚和 M1A UI 纵向流程。
- Windows `onedir` 构建成功，打包内项目存储烟测退出码为 0。

## 0.0.5 — 2026-07-19

### Added

- 确认 SceneLens 产品边界、技术栈和 M0.5 范围。
- 建立项目文档、Python `src` 布局、一键启动与测试入口。
- 完成参考图/当前截图拖放、双画布并排、同步缩放和平移与 A/B 切换。
- 完成灰度、可调高斯模糊、三阶/五阶明度视图。
- 完成线性 sRGB 明度计算、直方图和默认 8 色 Oklab 色板。
- 完成 EXIF 方向、ICC 到 sRGB、中文空格路径和常用图片格式验证。
- 完成后台图片读取/分析和 PyInstaller `onedir` 功能烟测。

### Validation

- 19 项自动化测试通过。
- 用户使用真实图片完成试用，未发现影响使用的问题；M0.5 正式冻结。
