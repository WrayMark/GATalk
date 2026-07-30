# SceneLens 决策记录

状态标记：`Accepted` 已接受，`Proposed` 待确认，`Deferred` 已推迟。

## D-001 Windows 原生技术栈

- 状态：Accepted
- 日期：2026-07-18
- 决策：Python 3.11 x64、PySide6 Qt Widgets、QGraphicsView/QGraphicsScene。
- 原因：与 Python 图像生态直接结合，无需本地服务和多语言 IPC。
- 后果：Windows 包体积较大；需持续验证 Qt/OpenCV 打包与 LGPL 合规。

## D-002 暂不采用其他应用形态

- 状态：Accepted
- 决策：V0.1 不采用 Tauri、Electron、本地 Web 服务或 UE 插件。
- 原因：减少工具链、进程管理和打包复杂度。

## D-003 正式数据层级

- 状态：Accepted
- 决策：Project → Shot → Version。
- 约束：透明叠加、滑块、像素差分和 SSIM 仅用于同一稳定镜头的版本。

## D-004 结果信息类型

- 状态：Accepted
- 决策：结果必须区分测量结果、算法推断和美术判断。
- 后果：数据模型中的每条结果必须带 `evidence_type`。

## D-005 正式项目存储

- 状态：Accepted，M1 执行
- 决策：`project.json` + SQLite + 原始资源目录 + 可重建 artifacts。
- 边界：`project.json` 只保存入口、格式版本和基础元数据；可变业务数据与
  工作状态进入 `project.db`。

## D-006 原始图片只读

- 状态：Accepted
- 决策：不覆盖源文件；正式导入保留原始字节；派生图只写入 artifacts。
- M0.5：只以内存方式读取，关闭软件不修改输入文件。

## D-007 色彩与方向处理

- 状态：Accepted
- 决策：Pillow 负责解码和 EXIF 方向；ImageCms 读取 ICC 并转换到 sRGB；
  NumPy 为内部图像格式；Colour Science 提供 Oklab 变换；OpenCV Headless
  提供滤镜、直方图和聚类。
- 原因：避免 OpenCV 自带 Qt 与 PySide6 插件冲突。

## D-008 色板语义

- 状态：Accepted
- 决策：M0.5 在 Oklab 中提取默认 8 色并显示面积比例。
- 限制：不自动断言主色、辅助色或点缀色；色板属于算法推断。

## D-009 AI 交换与隐私

- 状态：Accepted，M5 执行
- 决策：JSON 是正式交换格式；支持文件导入和粘贴；可去除常见代码围栏。
- 限制：只报告格式错误位置，不猜测或改变 AI 结论语义；软件不自动上传。

## D-010 Alpha 打包

- 状态：Accepted
- 决策：PyInstaller `onedir`。
- 推迟：安装器、`onefile`、自动更新和代码签名在 Beta 再评估。

## D-011 Qt 许可证策略

- 状态：Accepted
- 决策：当前个人专业使用采用 PySide6 社区发行版，并记录 LGPLv3/GPLv3
  义务。正式对外发行前进行完整法律与许可证审查，必要时购买 Qt 商业许可。
- 注意：本记录不是法律意见。

## D-012 先做 M0.5 技术验证

- 状态：Accepted
- 决策：在完整 M1 前，以最小纵向原型验证双画布、基础分析、ICC/EXIF、
  4K 性能和 Windows `onedir`。
- 禁止：M0.5 不提前实现 M1 之后的数据系统。

## D-013 依赖版本策略

- 状态：Accepted
- 决策：直接运行依赖固定到已核对版本；开发与打包依赖单独分组。
- 原因：提高 Windows 打包和算法复现的一致性。
- 例外：在独立兼容性分支完成验证后才能升级。

## D-014 Colour Science 可选能力

- 状态：Accepted
- 日期：2026-07-18
- 决策：M0.5 只使用 Colour 的 sRGB/XYZ/Oklab 核心变换，不安装 SciPy 和
  Matplotlib 可选能力。
- 原因：当前算法烟测证明 Oklab 路径无需这两个大型依赖；加入它们会显著
  增加依赖与打包体积。
- 后果：构建分析阶段会出现可选能力缺失警告，不影响 SceneLens 当前功能。

## D-015 PyInstaller 收集策略

- 状态：Accepted
- 日期：2026-07-18
- 决策：使用显式 `SceneLens.spec` 和静态导入分析，不使用
  `--collect-all colour`。
- 原因：`collect-all` 会错误收集 Colour 自带测试和 pytest，扩大包体积并
  引入无关模块。
- 当前结果：`onedir` 约 264 MB，仍需在后续阶段继续评估裁剪空间。

## D-016 M0.5 冻结

- 状态：Accepted
- 日期：2026-07-19
- 决策：用户已使用真实图片完成试用，未发现影响使用的问题；M0.5 通过
  人工验收并冻结。
- 后果：M0.5 基线只接受阻断性回归修复；新功能进入 M1A。干净无 Python
  Windows 环境和真实高 DPI 显示器验证仍属于后续发布验证，不虚报为已完成。

## D-017 M1 分阶段交付

- 状态：Accepted
- 日期：2026-07-19
- 决策：先完成并试用 M1A 项目、Shot、Version 与保存恢复，再启动 M1B
  证据化对比；不得同时铺开。
- 原因：存储格式和恢复语义是后续区域、任务与分析记录的基础，需先稳定。

## D-018 M1 混合存储职责

- 状态：Accepted
- 日期：2026-07-19
- 决策：项目目录采用 `project.json`、`project.db`、`assets`、
  `artifacts`、`exports` 和 `backups`。原图按原始字节 SHA-256
  内容寻址保存；业务关系不编码在文件路径中。
- 后果：同字节资源可去重；原始文件名、格式、尺寸和色彩处理状态在数据库
  中记录。派生结果缺失或损坏时允许按算法版本和参数重新生成。

## D-019 迁移与失败保护

- 状态：Accepted
- 日期：2026-07-19
- 决策：数据库使用递增 schema version 和逐步迁移；迁移前通过 SQLite
  backup API 备份数据库并复制清单。清单和资源导入使用临时文件加原子替换。
- 后果：迁移失败必须回滚并保留备份；遇到高于当前程序支持的格式版本时
  拒绝写入并给出明确错误，不尝试降级或猜测。

## D-020 M1A schema v1 边界

- 状态：Accepted
- 日期：2026-07-19
- 决策：schema v1 只建立项目身份、Art Brief、图片资源、Shot、Version、
  工作状态、画布状态和分析记录。区域、配对、审阅发现与任务在功能首次
  实现时通过后续迁移加入。
- 原因：先验证项目保存与恢复闭环，不为尚未实现的业务建立约束不足的空壳表。

## D-021 分析结果与产物分层

- 状态：Accepted
- 日期：2026-07-19
- 决策：可直接恢复的结构化数值保存到 `analysis_results`；可重建 JSON 和
  后续派生图片进入 `artifacts`。缓存键包含输入 SHA-256、算法身份、版本、
  规范化参数、Oklab 随机种子和采样上限。
- 后果：删除 artifact 不删除历史数值；软件可从数据库按原参数重建 artifact。
  每条结果分别标记 `measurement` 或 `algorithm_inference`。

## D-022 最近项目与 SQLite 依赖

- 状态：Accepted
- 日期：2026-07-19
- 决策：最近项目保存在 `%LOCALAPPDATA%/SceneLens/recent-projects.json`，
  不写入项目目录；SQLite 使用 Python 3.11 标准库，不增加第三方依赖。
- 后果：最近列表保存失败不影响项目，失效路径保留并在界面标记。

## D-023 M1A 冻结

- 状态：Accepted
- 日期：2026-07-19
- 决策：用户已使用真实项目完成试用并确认 M1A 通过人工验收；以 `0.1.0`
  冻结 M1A。
- 后果：M1A 基线只接受阻断性回归修复。真实高 DPI 显示器和完全无 Python
  干净机测试保留为 Windows Alpha 前验收项；多进程写保护在 M1B.0 首先实现。

## D-024 模块化单体与分析器契约

- 状态：Accepted
- 日期：2026-07-19
- 决策：长期采用“模块化单体，预留插件能力”。公共核心只提供分析器契约、
  注册表和真正跨模块复用的能力；当前 SceneLens 业务归属
  `scenelens.visual_review` 模块。
- 分析器身份至少包含 `module_id`、`analyzer_id`、`display_name`、`version`、
  `supported_inputs`、`parameter_schema`、`output_schema`、`run()` 和
  `cache_key()`。
- 后果：分析记录从 schema v2 起同时记录模块、分析器、版本、参数和输入哈希。
  本阶段不实现动态插件发现、隔离加载、权限系统或插件市场。

## D-025 同项目单写者保护

- 状态：Accepted
- 日期：2026-07-19
- 决策：每个项目通过 `.scenelens.write.lock` 建立跨进程操作系统文件锁；
  锁文件 JSON 只保存诊断元数据，操作系统锁才是写权限事实来源。
- 后果：第二个进程不能获得写权限，可由用户选择只读打开或取消。进程异常退出
  后操作系统自动释放锁；残留元数据不能永久阻止项目再次打开。

## D-026 M1B Brief 字段来源与写入优先级

- 状态：Accepted
- 日期：2026-07-19
- 决策：制作意图和参考图视觉简报使用文档加字段结构。字段保存 `value`、
  `source`、`confidence`、`evidence`、`user_confirmed` 和 `updated_at`。
- 写入规则：自动测量、算法推断或 AI 分析不得覆盖用户填写、用户修订或已确认
  字段。参考图视觉简报绑定图片 SHA-256；参考图变化时旧文档标记为 `stale`。
- 迁移规则：M1A 合并的“时间与天气”不由程序猜测拆分，保留原值和迁移依据。

## D-027 schema v2 与模块配置

- 状态：Accepted
- 日期：2026-07-19
- 决策：schema v2 新增模块数据版本、分析器身份、Brief 文档/字段表和活动分析
  页签。模块业务表使用 `visual_review_` 前缀；迁移前继续执行完整备份。
- 决策：时间、制作阶段、季节、天气、情绪、参考用途和区域标签从
  `modules/visual_review/config/presets.json` 加载，配置项使用稳定 ID，但保存
  用户实际输入值。
- 后果：未知或自定义值不会因预设中没有对应 ID 而丢失；不增加第三方依赖。

## D-028 共享色板与来源遮罩

- 状态：Accepted
- 日期：2026-07-19
- 决策：共享色板从参考图和当前截图各取严格等量的有界空间样本，在 Oklab
  中使用固定随机种子共同聚类。双方占比按各自样本对同一组中心分类计算。
- 决策：独立和共享色板遮罩都只使用已显示/保存的聚类中心重新分类，不在点击时
  重新聚类。未选像素降低亮度，源图字节和内存原图均不修改。
- 后果：色板属于算法推断；遮罩是该推断的空间证据，不代表好坏判断。

## D-029 M1B.1 schema v3

- 状态：Accepted
- 日期：2026-07-19
- 决策：schema v3 增加 `visual_review_comparison_analyses`，保存 Shot、
  Version、双方资源与哈希、模块/分析器/版本、规范化参数、缓存键、结果和
  证据类型。模块数据版本升为 2。
- 后果：共享色板和明度比较可在关闭重开后恢复；参考图变化会把旧对比记录标记
  为过期。M1B.0 schema v2 项目迁移前仍生成完整备份。

## D-030 三阶明度阈值语义

- 状态：Accepted
- 日期：2026-07-19
- 决策：三阶明度比较使用线性 sRGB 相对明度再编码到显示明度的既有流程，
  低/高阈值属于工作区分析参数。阈值变化同步更新比例、缩略图和三阶显示模式。
- 后果：表格只显示双方百分比和百分点差，不自动生成美术结论。

## D-031 M1B.1 冻结

- 状态：Accepted
- 日期：2026-07-19
- 决策：用户已使用真实项目完成试用，并确认共享 Oklab 色板、双图颜色遮罩、
  三阶明度比例、制作意图、参考图视觉简报和保存恢复符合当前预期；M1B.1
  通过人工验收并冻结。
- 后果：M1B.1 基线只接受阻断性回归修复；区域系统进入 M1B.2。真实高 DPI
  和完全无 Python 干净机测试继续保留为 Windows Alpha 前验收项。

## D-032 M1B.2 schema v4 与区域身份

- 状态：Accepted
- 日期：2026-07-19
- 决策：schema v4 新增 `visual_review_regions`、
  `visual_review_region_pairs` 和 `visual_review_region_analyses`，模块数据版本
  升为 3；v3 → v4 迁移前继续完整备份。
- 决策：区域坐标使用 EXIF 纠正工作图上的归一化矩形。参考区域绑定 Shot 且
  `version_id` 为空；当前区域绑定具体 Version。
- 决策：同一参考区域可以被多个 Version 的 Pair 复用；当前区域和 Pair 在复制
  上一 Version 时生成新 ID。未配对区域保存为独立 Region，不建立半完整 Pair。
- 后果：新 Version 可以复用参考语义，同时保持当前区域可独立调整；软件不会把
  归一化坐标等同于机位精确对齐。

## D-033 区域模块边界

- 状态：Accepted
- 日期：2026-07-19
- 决策：通用 `ImageCanvas` 只提供归一化矩形叠层、选择、移动和缩放信号；
  SceneLens 的区域语义、配对、Version 复制和持久化由
  `modules.visual_review` 的控制器与仓储负责。
- 原因：区域是 SceneLens 业务，不应继续写入应用外壳或通用画布；矩形交互本身
  又是可跨模块复用的显示能力。
- 后果：`MainWindow` 只挂载模块面板和传递当前项目上下文，不执行区域 SQL 或
  局部图像统计。

## D-034 成对区域分析语义

- 状态：Accepted
- 日期：2026-07-19
- 决策：平均明度、标准差及 P10/P50/P90 使用线性 sRGB 相对明度；三阶比例
  沿用既有“线性计算后转显示明度”的可调阈值语义。
- 决策：Oklab、彩度、色相和共享色板组成使用确定性的有界空间采样，默认每侧
  最多 250,000 像素。低于 `Oklab C=0.03` 的像素归为中性色，不进入色相分布；
  色相均值使用彩度加权圆形统计。
- 决策：区域色板不重新聚类，严格复用当前全图共享色板中心。区域遮罩只重新
  分类，并把高亮限制在当前成对矩形内。
- 后果：明度统计标记为测量结果；Oklab、色相和共享中心归类标记为算法推断。
  所有阈值、采样上限、中心身份、图片哈希、几何和分析器版本进入缓存与过期判断。

## D-035 M1B.2 冻结

- 状态：Accepted
- 日期：2026-07-19
- 决策：用户已使用真实项目完成试用并确认 M1B.2 通过；成对区域工作流、局部
  分析、区域遮罩、Version 复制及保存恢复冻结为稳定基线。
- 后果：建立验证标签后进入 M2。真实 125%/150% 高 DPI 显示器和完全无
  Python 干净 Windows 机器测试仍是 Windows Alpha 前验收项，不误记为已通过。

## D-036 M2/M3 竞品吸收边界

- 状态：Accepted
- 日期：2026-07-19
- 决策：只吸收专项审阅台、画布证据标注、本地观察模式和“诊断到预演”的产品
  类别。Pro 未发现明确许可证，不复用其代码、长提示词或表达；灯光版虽标记
  MIT，本轮也不复制其源码。
- 决策：拒绝 0–10 泛化总分、用建议条数表示改动强度、从 Markdown 关键词生成
  改图指令、从截图输出伪精确 Lux/EV/性能收益/Actor 数量，以及把截图处理命名
  为真实灰模。
- 后果：SceneLens 使用严格 Schema、用户确认任务、证据校验、质量门禁和
  `AIConceptPreview` 隔离实现同类能力。

## D-037 schema v5 共享工作台实体

- 状态：Accepted
- 日期：2026-07-19
- 决策：共享核心表示 Project、Asset、Shot、Version、Region、Evidence、
  Annotation、Task、DerivedArtifact、AIRun、SourceDocument、ReviewProfile
  和 QualityGate。schema v5 新增对应的 `workbench_*` 持久化表。
- 决策：模块私有表继续使用模块前缀；共享实体保留 `module_id`。项目存储通过
  `module_schema_versions` 判断模块是否已安装，不在外壳中硬编码业务模块列表。
- 决策：`AIRun` 只记录 provider/model ID、请求哈希、数据清单、状态和脱敏
  结果；输入清单拒绝 API Key、Authorization 和访问令牌字段。
- 后果：v4 → v5 迁移前自动备份。M2 后续能力优先复用共享实体，只有出现真实
  模块私有关系时才提升 `scenelens.visual_review` 模块 schema。

## D-038 Provider Manifest、凭据与联网门禁

- 状态：Accepted
- 日期：2026-07-19
- 决策：供应商通过 `VisionReviewProvider`、`StructuredOutputProvider` 和
  `ImageEditProvider` 能力接口接入。端点、默认模型和能力从可打包的 Manifest
  加载；领域模型不保存具体模型名。
- 决策：应用启动和 Provider 注册完全离线。真实请求必须由用户主动触发并确认
  发送清单；默认测试只使用 Mock 或录制传输层。
- 决策：API Key 使用 Windows Credential Manager，不进入项目、SQLite、
  JSON、日志或 Git。`AIRun` 只保存 provider/model ID、请求哈希和脱敏元数据。
- 决策：M2 为万相、Gemini/Nano Banana、OpenAI GPT Image 和 Grok Imagine
  注册图像编辑能力位置，只允许 Mock 执行；真实编辑放在 M3。
- 后果：真实 Key、区域开通、计费和供应商响应列为人工联网验收。无 Key 时所有
  本地项目、测量、区域、任务、报告和离线交换能力仍必须工作。

## D-039 M2 审阅 Schema 与证据冲突策略

- 状态：Accepted
- 日期：2026-07-19
- 决策：`ArtDirectorReview` 与 `LightingReview` 使用随包发布的严格 JSON
  Schema，最多返回五个核心问题，不包含泛化总分。灯光 Schema 不接受真实
  Lux、真实 EV、动态范围、性能收益百分比或确定 Actor 数量等截图无法支持的
  字段。
- 决策：AI 的位置、明暗、局部对比、溢出和冷暖推断必须保留原结论，同时由
  本地测量标记为“得到支持、部分支持、存在冲突、无法验证”。发生冲突时降低
  可信度并显示原因，不静默删除结论。
- 决策：第二意见只审查主模型证据、遗漏与可疑推断；合并结果保留双方
  provider/model 来源与分歧，不生成第二篇平行长报告。
- 后果：质量状态由用户定义的分维度门禁和 Version 变化状态表达；审阅结果只有
  经用户确认后才能转为任务。

## D-040 schema v6 与灯光观察状态

- 状态：Accepted
- 日期：2026-07-19
- 决策：schema v6 只为 `workspace_state` 增加可恢复的
  `silhouette_threshold`；AI Run、Evidence、Annotation 和 Task 继续复用
  schema v5 的共享工作台实体，不创建供应商专属表。
- 决策：曝光伪色是显示明度分段图，不命名或解释为真实 EV；灯光明度代理图
  不能声称剥离材质或纹理。所有观察模式只处理内存工作副本。
- 后果：v5 → v6 和更早版本跨级迁移均先备份；显示模式和剪影阈值可以随项目
  保存恢复。

## D-041 估计匹配度与证据覆盖

- 状态：Accepted
- 日期：2026-07-19
- 决策：M3 以十个独立维度表达参考目标匹配，允许用户修改非负透明权重。
  “估计匹配度”只在有证据的维度间加权；视觉焦点、灯光氛围和空间层次等缺少
  语义证据时保存为不可用，而不是猜测或按零分处理。
- 决策：界面必须同时显示证据覆盖率、分维度来源和算法解释；估计匹配度不称为
  作品质量分、审美分或好坏判断。
- 后果：高估计匹配但低证据覆盖不能被解释为目标已经达成；用户修改权重只改变
  汇总视角，不改变原始测量。

## D-042 安全调色的可复现边界

- 状态：Accepted
- 日期：2026-07-19
- 决策：本地安全调色只处理内存工作副本，不覆盖项目资产。强度在原图和目标
  处理结果之间使用线性 sRGB 插值；区域作用范围复用已保存的归一化当前区域。
- 决策：有限参考色迁移只允许有界 Oklab 均值偏移。包含区域作用或参考色迁移的
  配方不能导出成通用 `.cube`；其余配方可以导出确定性 3D LUT。
- 后果：PNG 是派生预览，JSON 配方保存参数语义；任何导出都不替换真实
  Version，撤销重做只操作配方历史。

## D-043 AIConceptPreview 与图像编辑适配

- 状态：Accepted
- 日期：2026-07-19
- 决策：生成式改图指令只从制作意图、参考图视觉简报、用户确认任务、成对区域
  和保护约束构造，不解析 Markdown，也不以建议条数表示强度。AI 强度是允许的
  改动预算，不是数学插值比例。
- 决策：供应商输出必须保存为 `artifacts/ai_previews` 下的
  `AIConceptPreview`，记录 provider/model、输入哈希、结构化指令、保护约束、
  漂移校验和状态；绝不插入 Version 表。
- 决策：结构漂移、保护区变化或构图偏移超过本地阈值时标记“仅适合概念参考”。
  预演可经用户确认转为任务，但正式验证只能使用后续导入的真实 UE 截图。
- 决策：万相、Gemini、OpenAI 和 xAI 适配器默认不联网测试。只处理内嵌图片
  响应；URL-only 输出暂不自动下载，避免未经重新确认的第二次网络取回。
- 后果：所有网络发送继续经过主动触发、发送清单、系统凭据、后台取消/重试和
  脱敏 AIRun。真实 Key、模型可用性、计费和响应字段需逐供应商人工验证。

## D-044 Provider 兼容 Schema、错误诊断与结果下载

- 状态：Accepted
- 日期：2026-07-19
- 决策：本地审阅 Schema 是领域数据真相；供应商只接收由适配器生成的兼容
  Schema。Gemini 适配器移除其不支持的关键字并把 `const` 转成单值
  `enum`，响应返回后仍使用完整本地 Schema 验证，不降低 SceneLens 数据要求。
- 决策：公共 HTTP 层读取有界错误正文，提取并脱敏 status、code、type 和
  message。界面显示 HTTP 分类、内部错误代码和供应商原因，不显示 API Key、
  Authorization、图片字节或完整请求正文。
- 决策：D-043 中“URL-only 输出不下载”的限制由本决策替代。用户确认并主动
  发起图像编辑后，同一后台任务可以下载供应商返回的 HTTPS 结果 URL；只接受
  图片媒体类型，最大 50 MiB，不携带 API Key 到结果 URL。
- 决策：xAI 图像编辑使用 JSON；OpenAI 图像编辑使用 multipart；万相和
  Gemini 使用各自原生 JSON。不得仅因端点路径相似而共享错误的传输格式。
- 后果：真实 Key 仍不进入自动测试。离线契约测试证明请求结构、错误脱敏和
  响应解析；账号权限、区域、配额、计费和真实服务响应继续列为人工联网验收。

## D-045 Gemini generateContent MIME 枚举兼容

- 状态：Accepted
- 日期：2026-07-28
- 决策：Gemini `generateContent` 的新 `responseFormat.text.mimeType` 按
  `TextResponseFormat.MimeType` 发送 `APPLICATION_JSON`，不发送旧式
  MIME 字符串 `application/json`。独立图片输入的 `inlineData.mimeType`
  仍使用 `image/png` 等真实媒体类型。
- 依据：真实 v1beta 请求返回 `INVALID_ARGUMENT`，明确指出
  `generation_config.response_format.text.mime_type` 的枚举值无效；官方
  API 参考同时列出 `APPLICATION_JSON` 枚举。
- 后果：Provider 契约测试必须精确断言该字段，避免只验证 Schema 而漏掉
  线上的枚举兼容问题。

## D-046 M4 八维深度主美审阅

- 状态：Accepted
- 日期：2026-07-28
- 决策：新增 `DeepArtDirectorReview`，固定覆盖构图、视觉引导、焦点层级、
  色彩设计、明度结构、灯光氛围、材质可读性、世界设计与叙事八个维度。输出
  继续使用严格 JSON Schema、最多五个核心问题且不设总分。
- 决策：输入必须包含制作阶段、制作意图、参考图视觉简报、本地全图证据摘要、
  当前 Version 的全部成对区域分析、Version 历史和锁定目标。每张发送图片在
  Provider 请求中显式标记 reference/current 角色。
- 决策：AI 可测声明使用统一 `evidence_claims`，由本地像素验证明暗、反差、
  高光、暗部、Oklab 冷暖和参考明度差。冲突不删除原结论，只降低可信度并显示
  原因；无法测量的语义判断必须保留不确定性。
- 后果：深度审阅可以更丰富，但准确性仍受图片、制作意图和所选视觉模型限制；
  离线 Mock 只验证结构和流程，不执行本地美术推理。

## D-047 schema v7 与构图辅助线

- 状态：Accepted
- 日期：2026-07-28
- 决策：schema v7 仅为 `workspace_state` 增加 `composition_guide`。三分法、
  黄金分割、对角线、中心、三角形、单点透视和两点透视使用归一化线段定义，
  由通用画布缩放绘制。
- 决策：构图辅助线属于用户观察叠层，不是算法推断、显著性分析或构图评分。
  原图不被修改；`Esc` 可关闭叠层。
- 后果：v6 → v7 和更早版本跨级迁移均先备份；构图辅助选择随项目恢复。

## D-048 Gemini 复杂 Schema 双层约束

- 状态：Accepted
- 日期：2026-07-28
- 决策：完整本地 JSON Schema 继续作为 SceneLens 领域数据真相。Gemini
  Schema 超过保守复杂度阈值时，服务端只接收顶层字段和类型约束；完整 Schema
  同时作为纯文本输出契约发送，响应返回后仍执行完整本地校验。
- 决策：若 Gemini 对带 Schema 的请求返回 `HTTP 400`，同一次用户主动操作可
  自动改用只约束 JSON 媒体类型的兼容请求重试一次。该降级不放宽本地校验，
  不适用于认证、额度或服务端错误，也不允许无限重试。
- 决策：只提供 JSON 对象模式的百炼和 SiliconFlow 必须在提示中接收完整
  Schema；不得只要求“返回 JSON”而省略字段契约。
- 依据：M4 真实请求已到达 `gemini-3.5-flash`，但八维深度 Schema 被服务以
  `INVALID_ARGUMENT` 拒绝；Google 官方文档明确说明过大或过深的 Schema
  可能被拒绝。
- 后果：Provider 的服务端约束可按兼容性收紧或降级，但 SceneLens 保存结果的
  结构要求不变。真实联网验证继续由用户使用自己的 Key 主动执行。

## D-049 Gemini 嵌套结构约束与一次性纠错

- 状态：Accepted
- 日期：2026-07-28
- 决策：完整本地 JSON Schema 仍是唯一数据真相。Gemini 的复杂服务端 Schema
  不再只保留顶层字段，而是保留全部嵌套对象、必填字段、数组和元素类型；枚举、
  数值范围等非结构约束可以省略，以控制服务端语法复杂度。
- 决策：完整 Schema 与一个通过本地校验的 JSON 结构模板同时进入提示，明确
  `evidence_claims` 只能是完整对象数组；证据结构不完整时返回空数组，不得改成
  自由文本。
- 决策：首次结果未通过完整本地 Schema 时，同一次用户主动操作最多再调用一次
  Gemini 做结构纠错。纠错只能修复形状并保留已有语义，不得增加美术结论或虚构
  坐标；第二次仍失败就停止并显示字段路径。
- 决策：确认发送窗口必须提前说明纠错可能再次发送同一审阅副本并增加少量费用。
  结构纠错次数和两次用量分开记录，不能静默无限重试。
- 依据：`0.5.0a1` 真实请求已通过传输层，但返回缺少六个
  `target_readback` 必填字段，并把八条 `evidence_claims` 输出为字符串。
- 后果：服务端负责尽量生成正确结构，本地仍执行最终严格校验；真实模型的遵循
  程度继续列为用户联网验收项。

## D-050 AI 审阅跨字段悬空引用处理

- 状态：Accepted
- 日期：2026-07-28
- 决策：审阅结果先通过完整 JSON Schema，再由 Reviewer 执行本地技术归一化
  和领域校验。`linked_finding_ids` 或动作 `finding_ids` 中不存在于本次
  `findings` 的值直接移除；有效引用保持原顺序。
- 决策：不得按字符串相似度猜测对应 finding，不修改审阅正文、finding、动作
  内容或优先级，也不为悬空引用发起额外模型调用。
- 决策：清理结果作为“结构修复”提示显示，并保存只包含有效引用的结果。其他
  Schema 或领域错误仍按失败处理，不能借归一化放宽。
- 依据：真实 Gemini 结果偶发引用 `find_smoke_particle` 和
  `find_skybox_color`，但本次 findings 中没有这两个 ID；此前整份报告因此
  无法使用。
- 后果：模型随机产生的技术性链接错误不再丢弃完整报告，同时保留不猜测语义
  和可审计提示的边界。该防护属于 Reviewer，适用于所有 Provider。

## D-051 Gemini 原始 JSON 语法恢复

- 状态：Accepted
- 日期：2026-07-28
- 决策：Gemini 适配器在 JSON 解析前保留内存中的原始响应文本和
  `finishReason`。解析失败与 Schema 校验失败共用一次性纠错额度，不允许各自
  重试一次。
- 决策：候选响应包含多个文本 part 时先按原顺序拼接全部文本，再执行 JSON
  解析；不能只读取第一个 part 并把其余内容误判为丢失。
- 决策：语法纠错请求携带原文、解析行列、完成原因、完整 Schema 和原始审阅
  上下文，要求用更精简措辞返回完整对象。仍需保留既有语义，不得新增美术结论
  或虚构测量、坐标。
- 决策：不采用自动补括号、删除字符或宽松 JSON 解析器，因为这些本地猜测可能
  静默改变 AI 语义。第二次解析失败统一返回
  `invalid_structured_output_after_repair` 并停止。
- 决策：发送确认窗口必须把语法损坏、截断和结构不完整都列为可能触发一次额外
  调用的原因；运行用量记录纠错原因及前后两次用量。
- 依据：真实 Gemini 响应在 `line=461,column=17` 无法解析，既有纠错逻辑只在
  `json.loads` 成功后检查 Schema，因此没有接住。
- 后果：一次偶发截断不再立即丢弃审阅，但真实模型是否能在第二次压缩完成仍是
  联网人工验收项，且可能产生一次额外费用。

## D-052 应用首页与作品研究模块

- 状态：Accepted
- 日期：2026-07-30
- 决策：应用启动先显示工作台首页。`scenelens.visual_review` 保持场景美术
  控制职责；新增 `scenelens.artwork_study`，不把单图研究塞入 Project →
  Shot → Version 的对比模型。
- 决策：首版作品研究使用独立 `.scenelens-study` 目录包：
  `study.json` 保存入口和状态，`assets` 保存原始字节，`artifacts` 保存可重建
  证据，`exports` 保存显式导出。格式版本单独演进，不提升场景项目 schema。
- 后果：应用体量增加，但模块边界清楚；未来新增大模块通过首页与工作区注册
  接入，不要求持续修改场景审阅核心数据关系。

## D-053 作品研究方法与证据边界

- 状态：Accepted
- 日期：2026-07-30
- 决策：作品研究遵循“描述 → 形式关系 → 观看效果 → 解释 → 评价 → 迁移学习”，
  固定覆盖构图、视觉层级、明度、色彩、光、空间、形状、边缘细节、材质、环境
  叙事、风格技法和情绪十二维，并额外输出跨维度因果链。
- 决策：AI 字段区分 `visible_image_evidence`、`local_measurement`、
  `expert_inference`、`contextual_hypothesis`。评价说明目标、有效性、代价和
  适用边界，不使用总分；复刻步骤不作为本阶段重点。
- 决策：本地“注意力代理”只按九宫格组合局部明度反差、边缘密度和 Oklab
  彩度，明确不是眼动、语义显著性或构图结论。单图不能证明的作者意图、焦距、
  Lux、EV、材质节点和制作过程必须保留不确定性。
- 依据：Pixar 视觉语言与灯光、Smarthistory close looking / formal analysis、
  James Gurney 色域与空气透视、FZD 设计思维和 Gnomon 环境叙事公开资料。
- 后果：丰富度来自证据、关系和教学结构，不来自更多空洞维度或更长提示词。
