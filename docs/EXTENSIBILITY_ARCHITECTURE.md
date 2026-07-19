# SceneLens 扩展性架构

状态：M1B.0 基线  
日期：2026-07-19

## 1. 结论

SceneLens 采用“模块化单体，预留插件能力”。当前不拆多进程服务，不开发动态
插件系统，也不把尚未出现的功能提前抽象。目标是在不牺牲当前开发速度的前提下，
让未来模块能拥有稳定身份、独立数据和明确接入点。

## 2. 当前边界审查

### 已成立的边界

- `analysis` 是纯 NumPy 计算，不依赖 Qt。
- `imaging` 集中处理 EXIF、ICC、sRGB 和 NumPy/QImage 边界。
- `storage` 不依赖 Qt，UI 不直接执行 SQL。
- 图片加载、分析与显示渲染通过后台任务运行。

### 明显扩展障碍

1. `MainWindow` 过去直接选择并调用具体测量函数，新增分析器需要修改主窗口。
2. schema v1 的分析记录只有旧式 `algorithm_id`，无法区分未来业务模块。
3. 预设项若写在主窗口中，会把 SceneLens 业务配置和应用外壳绑定。
4. `MainWindow` 与 `ProjectStore` 体量已经较大，但当前只有一个成熟业务模块；
   现在全面拆控制器和仓储会引入超过实际收益的回归面。

### M1B.0 最小修正

- 新增公共分析器契约与注册表，主窗口通过注册表取得基础测量分析器。
- 建立 `scenelens.visual_review` 业务模块和模块配置目录。
- schema v2 为分析记录补充模块/分析器身份，并增加模块数据版本。
- Brief 表使用 `visual_review_` 前缀，预设从模块 JSON 配置加载。
- 暂不全面拆分 `MainWindow` 和 `ProjectStore`；M1B.1 完成后依据真实调用点再
  提取应用服务或模块面板。

这不是“已经完成插件化”。它只消除了当前最明确的硬编码接入点。

## 3. 目标依赖方向

```text
app / ui shell
    ↓
core contracts / task boundary / shared imaging
    ↓
modules.visual_review
    ↓
analysis + storage public APIs
```

约束：

- `core` 不导入具体模块。
- 业务模块可以依赖 `core`、`analysis`、`imaging` 和存储公共接口。
- UI 外壳不实现算法，不拼 SQL。
- 模块表和 artifact 使用稳定模块 ID，避免 Python 包重命名改变数据身份。

## 4. 分析器契约

每个分析器逐步提供：

- `module_id`
- `analyzer_id`
- `display_name`
- `version`
- `supported_inputs`
- `parameter_schema`
- `output_schema`
- `run(request)`
- `cache_key(request)`

缓存键至少由模块 ID、分析器 ID、分析器版本、规范化参数和所有输入哈希构成。
随机算法的随机种子属于参数。`run()` 不产生 UI 或存储副作用。

当前注册分析器为：

```text
scenelens.visual_review/basic_image_measurements@1
scenelens.visual_review/shared_oklab_palette@1
scenelens.visual_review/three_value_luminance_comparison@1
scenelens.visual_review/paired_region_comparison@1
```

## 5. 模块数据与迁移

- 应用数据库继续使用一个 SQLite 文件，保持本地事务和备份简单。
- 公共表只保存项目身份、资源等跨模块事实。
- 模块业务表使用稳定前缀，例如 `visual_review_brief_documents`。
- `module_schema_versions` 记录各模块的数据版本。
- 当前总 schema 迁移仍由应用按顺序执行；未来出现第二个真实模块时，再将模块
  迁移注册表从总迁移文件中拆出，避免现在形成空框架。
- 每次总 schema 升级前备份 `project.db` 和 `project.json`。

未来模块可以拥有独立表、迁移注册、界面入口和后台任务，但不得越过公共接口直接
修改其他模块的私有表。

## 6. UI 与后台任务演进

M1B.0 不重写主窗口。后续按真实需求逐步拆分：

1. 模块提供面板/动作描述，由应用外壳挂载；
2. 分析请求通过注册表和统一后台任务执行；
3. 任务结果带请求代次，快速切换 Shot/Version 后旧结果被丢弃；
4. 模块应用服务协调存储与分析，主窗口只绑定命令和显示状态。

只有当第二或第三个模块出现相同需求时，才把模块能力提升为公共核心。

M1B.2 的实际演进：

- 通用 `ImageCanvas` 提供无业务语义的矩形叠层交互；
- `modules.visual_review.ui.RegionController` 协调区域模式、配对和 Version；
- `modules.visual_review.RegionStore` 拥有区域模块 SQL；
- 应用外壳只注入当前 Project / Shot / Version 并挂载模块面板。

这是由真实区域工作流驱动的局部拆分。其他模块若不需要相同能力，不会被迫依赖
SceneLens 的区域表或语义。

## 7. 本阶段明确不做

- 动态发现和加载第三方 Python 包；
- 进程隔离、权限清单和签名；
- 插件 SDK、兼容性承诺和市场；
- 为博客、翻译、知识库或关卡设计建立空表或空界面；
- 将本地桌面应用拆成服务或联网架构。
