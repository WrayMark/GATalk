# Changelog

## Unreleased

### Added

- 增加 M4“深度主美审阅（八维）”，逐项呈现制作目标、参考呈现、当前效果、
  证据摘要、已有优点、风险、可信度和不确定性。
- 增加最多五个跨维度核心问题、需要保留内容及带依赖顺序的 UE 执行计划。
- 增加有界九宫格本地证据摘要，并将主美审阅中的可测声明接入本地证据校验器。
- 增加三分法、黄金分割、对角线、中心、三角形、单点透视和两点透视构图辅助线。
- 增加 schema v7，使构图辅助选择随项目保存恢复并保留迁移前备份。
- 增加供应商 HTTP 错误状态和脱敏原因显示，区分参数、认证、权限、模型、
  请求大小、额度和服务端错误。
- 增加 Gemini JSON Schema 兼容转换、万相/OpenAI/Grok 远程结果图片安全
  下载，以及对应离线契约测试。
- 增加 `docs/PROVIDER_COMPATIBILITY_AUDIT_2026-07-19.md` 兼容性审计记录。
- 增加随每次用户可见更新同步维护的 `SceneLens_使用手册.docx` 纯文字简明
  Word 使用手册及可重复生成脚本。
- 增加 M3“优化实验室”页签，集中呈现目标匹配画像、本地安全调色与
  `AIConceptPreview` 生成式预演。
- 增加十维透明权重的估计匹配画像和证据覆盖率；缺少语义证据的维度明确显示
  “证据不足”，不自动生成美术评分。
- 增加保持几何的本地安全调色：曝光、对比、白平衡、阴影/中间调/亮部、彩度、
  有限 Oklab 参考色迁移、全图/区域作用范围和线性 sRGB 强度插值。
- 增加 5% 步进及 5/10/15/25/50/75/100 快捷强度、A/B、配方撤销重做、
  PNG、JSON 配方和可行时的 `.cube` LUT 导出。
- 增加万相、Gemini/Nano Banana、OpenAI GPT Image、Grok Imagine 的真实请求
  构造适配器、二进制传输契约和完全离线图像编辑 Mock。
- 增加结构化改图指令、改动预算语义、保护约束和主动发送清单。
- 增加 `AIConceptPreview` artifact 隔离、结构漂移、稳定/保护区变化、构图偏移、
  色调目标改善校验及“仅适合概念参考”边界。
- 增加预演经用户确认转任务，并强制记录后续需导入真实 UE Version 验证。
- 增加 M2 AI 审阅与任务面板、发送清单、系统凭据操作、后台运行/取消、脱敏 AI Run 保存和用户确认转任务。
- 增加结构化三套灯光方案、画布箭头/区域/视线流向/视觉重量标注及标注转任务。
- 增加可自包含图片副本的离线 AI 审阅包 ZIP。
- 增加 schema v6，使灯光剪影阈值随项目恢复，并保持迁移前备份。
- 增加主美专项审阅与灯光专项审阅的严格 JSON Schema、最多五个核心问题限制和本地 Schema 校验错误路径。
- 增加 AI 证据校验器，覆盖区域明暗、局部对比、高光、暗部、Oklab 冷暖及参考/当前差异，并在冲突时显式降低可信度。
- 增加曝光伪色、明暗溢出警告、可调剪影、缩略图观察、明度模糊和灯光明度代理图纯分析能力。
- 增加分维度 Quality Gate、新 Version 改善状态、保留来源与分歧的第二意见合并，以及不含本地路径的离线审阅包。
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

- 视觉审阅请求现在逐张显式标记 reference/current 图片角色；深度主美与灯光
  审阅分别配置结构化输出预算。
- 深度审阅上下文从“当前选中区域”扩展为当前 Version 的全部成对区域及其最新
  分析记录。
- 项目版本进入 `0.5.0a0`；M4 形成新的真实项目试用候选。
- Gemini `generateContent` 的 `responseFormat.text.mimeType` 改用服务端要求的
  `APPLICATION_JSON` 枚举值；此前的 `application/json` 会被 v1beta 端点以
  `INVALID_ARGUMENT` 拒绝。
- Gemini 视觉审阅改用当前 `responseFormat`，不再向 Gemini 发送不支持的
  Schema 关键字或强制低温度；百炼和 SiliconFlow 明确启用 JSON 对象模式。
- Grok Imagine 图像编辑改用 JSON 请求；OpenAI 图像默认模型更新为
  `gpt-image-2`。
- 项目版本进入 `0.4.0a0`；M3 形成第二个重大外部试用候选。
- M2 注册的四类图像编辑能力位置在 M3 获得请求适配实现；真实 Key、区域开通、
  计费和供应商响应仍不属于默认自动测试。
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

- M4 候选完整离线回归 156 项通过；源码和打包内 `--smoke-test` 退出码均为 0。
- M4 Windows `onedir` 构建成功，目录为 `dist-m4/SceneLens/`，224 个文件，
  266,553,088 bytes（约 254.2 MiB），包含新版 Word 使用手册。
- Word 手册结构检查为 96 段、1 节、无替换字符；本机未安装 LibreOffice，
  因此标准逐页渲染检查未完成。
- Gemini MIME 枚举回归测试与完整离线回归共 149 项通过。
- Gemini 接口修复候选 `dist-gemini-fix/SceneLens/` 构建成功，包含简明
  Word 使用手册；目录总大小 266,520,924 bytes（约 254.2 MiB），包内
  `--smoke-test` 退出码为 0。
- Provider 兼容修复完整回归 149 项通过；新增测试全部离线且不读取真实 Key。
- Provider 兼容修复 Windows 候选 `onedir` 构建成功，目录总大小
  266,480,131 bytes（约 254.1 MiB）；包内离线烟测退出码为 0。旧
  `dist/SceneLens/SceneLens.exe` 被运行中进程占用，因此候选输出到
  `dist-provider-fix/SceneLens/`。
- M3 候选完整回归 145 项通过；默认测试完全离线，包含 Mock
  `AIConceptPreview` 端到端隔离和不新增 Version 的 UI 测试。
- M3 Windows `onedir` 构建成功，目录总大小 266,472,228 bytes（约
  254.1 MiB）；扩展后的包内烟测退出码为 0，并覆盖 M3 匹配、调色、漂移、
  图像编辑 Mock 和预演/Version 隔离。
- M2 候选完整回归 122 项通过；源码和打包内离线烟测退出码均为 0。
- M2 Windows `onedir` 构建成功，目录总大小 266,410,388 bytes（约 254.1 MiB）。
- M2 专项审阅、严格 Schema、证据校验和灯光观察模式切片完整回归 108 项通过；默认测试无网络、无 API 消耗。
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
