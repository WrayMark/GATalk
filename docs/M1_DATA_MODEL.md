# GATalk M1 数据模型与迁移方案

状态：schema v1 已实现，等待 M1A 人工试用  
评审日期：2026-07-19

## 1. 设计目标

M1 的存储必须支持以下闭环：

> Art Brief → Shot 参考图与 Version 截图 → 可复现分析 → 历史恢复

同时满足：

- 项目可整体复制，不依赖原始导入路径；
- 原始图片字节不可变，不因 EXIF、ICC 或分析过程被重新编码；
- 项目清单、业务数据和可重建产物职责单一；
- 保存失败不损坏上一次成功状态；
- 旧项目先备份再迁移；
- 高版本项目不被旧版程序误写；
- M1A 不提前实现 M1B 的交互功能。

## 2. 项目目录

```text
中世纪村庄.scenelens/
├─ project.json
├─ project.db
├─ assets/
│  └─ originals/
│     └─ ab/
│        └─ <sha256>.<检测格式的规范扩展名>
├─ artifacts/
│  └─ <asset_id>/
│     └─ <analysis_run_id>/
├─ exports/
└─ backups/
   └─ pre-migration_0001_to_0002_<UTC时间>/
      ├─ project.json
      ├─ project.db
      └─ backup.json
```

规则：

- 项目目录后缀建议为 `.scenelens`，但读取不依赖后缀。
- 所有清单内路径均为相对项目根目录的 POSIX 风格路径。
- 拒绝绝对路径、`..` 和逃逸项目根目录的路径。
- `assets/originals` 只保存导入时的原始字节。
- `artifacts` 只保存可删除、可重建的派生文件。
- `exports` 预留给后续 AI 审阅包，不在 M1A 中实现导出。
- `backups` 只保存迁移前一致性备份。

## 3. `project.json`

`project.json` 是项目入口，不是业务数据的第二份副本。

示例：

```json
{
  "format": "scenelens.project",
  "format_version": 1,
  "project_id": "5c8a716f-eafd-4ebd-a625-4bfa78bed95f",
  "name": "中世纪村庄",
  "created_at": "2026-07-19T08:00:00.000Z",
  "updated_at": "2026-07-19T08:30:00.000Z",
  "app_version": "0.1.0",
  "database": {
    "path": "project.db",
    "schema_version": 1
  },
  "directories": {
    "assets": "assets",
    "artifacts": "artifacts",
    "exports": "exports",
    "backups": "backups"
  }
}
```

职责：

- 识别 GATalk 项目和项目 ID；
- 保存清单格式版本、数据库入口和目录入口；
- 保存名称、创建时间、最后成功保存时间等基础元数据；
- 在打开数据库前完成最低限度兼容性检查。

不保存：

- Art Brief；
- Shot、Version、区域、任务；
- 当前选择、缩放或分析参数；
- 分析数值结果。

这些可变数据只以 `project.db` 为事实来源，避免双写分歧。

## 4. SQLite 约定

- ID 使用 UUID 字符串，避免导入、复制或未来合并时依赖本机自增值。
- 时间使用 UTC ISO 8601 字符串，界面按本地时区显示。
- 布尔值使用 `INTEGER NOT NULL CHECK (value IN (0, 1))`。
- JSON 字段写入前使用稳定键顺序和紧凑分隔符规范化。
- 每次连接启用 `PRAGMA foreign_keys = ON`。
- 正常项目使用 WAL；迁移备份通过 SQLite backup API 取得一致快照。
- `PRAGMA user_version` 是数据库 schema 版本的机器可读事实来源；
  `schema_migrations` 记录人可审计的迁移历史。

## 5. M1A schema v1

### 5.1 `project_identity`

每个数据库只允许一条项目身份记录，用于与清单交叉校验。

| 字段 | 说明 |
|---|---|
| `id` | 与清单 `project_id` 一致 |

项目名称和基础时间只以清单为事实来源，不在数据库重复保存。打开项目时
必须校验数据库和清单的项目 ID 一致。

### 5.2 `art_briefs`

M1A 使用项目级 Art Brief；数据结构预留 Shot 级覆盖。

| 字段 | 说明 |
|---|---|
| `id` | Art Brief ID |
| `project_id` | 所属项目 |
| `shot_id` | `NULL` 表示项目级；非空表示 Shot 级覆盖 |
| `scene_type` | 场景类型 |
| `production_stage` | 当前制作阶段 |
| `target_style` | 目标风格 |
| `time_weather` | 时间和天气 |
| `target_mood` | 目标情绪 |
| `primary_focus` | 第一视觉焦点 |
| `secondary_focus` | 次要视觉焦点 |
| `preserve_content` | 希望保留的内容 |
| `main_issues` | 当前主要问题 |
| `excluded_review` | 暂不需要审阅的部分 |
| `constraints` | 制作条件与限制 |
| `created_at` / `updated_at` | 时间 |

项目级 Brief 只有一条；每个 Shot 最多一条覆盖。M1A 界面只编辑项目级
Brief，Shot 级覆盖等出现真实需求后再开放。

### 5.3 `image_assets`

| 字段 | 说明 |
|---|---|
| `id` | 资源 ID |
| `sha256` | 导入原始字节的 SHA-256，唯一 |
| `original_filename` | 原文件名，不保存原机器绝对路径 |
| `stored_relpath` | 项目内不可变资源路径，唯一 |
| `byte_size` | 原始字节数 |
| `media_type` | 检测到的图片媒体类型 |
| `source_format` | PNG/JPEG/WebP 等 |
| `width` / `height` | 完成方向修正后的工作尺寸 |
| `exif_orientation` | 原文件 EXIF 方向值，可空 |
| `icc_status` | `converted_to_srgb`、`assumed_srgb` 或错误状态 |
| `imported_at` | 导入时间 |

`sha256` 基于原始字节，不基于解码像素。资源的用途不写入路径或本表，
而由 Shot/Version 外键表达。同字节文件在同一项目内复用一份资源。

### 5.4 `shots`

| 字段 | 说明 |
|---|---|
| `id` | Shot ID |
| `project_id` | 所属项目 |
| `name` | 镜头名称 |
| `reference_asset_id` | 概念参考资源，可空 |
| `sort_order` | 导航排序 |
| `created_at` / `updated_at` | 时间 |

一个 Project 可以包含多个 Shot。参考图只用于审阅目标，不自动视为与
Version 像素对齐。

### 5.5 `versions`

| 字段 | 说明 |
|---|---|
| `id` | Version ID |
| `shot_id` | 所属 Shot |
| `asset_id` | 截图原始资源 |
| `ordinal` | Shot 内递增序号 |
| `name` | 用户可读名称 |
| `notes` | 版本说明 |
| `created_at` | 创建时间 |

`(shot_id, ordinal)` 唯一。同一 Shot 的 Version 表示稳定机位历史，未来
透明叠加、滑块和像素比较只能在这些 Version 之间执行。

### 5.6 `workspace_state`

每个项目一条，保存可恢复的全局工作状态：

- 当前 Shot 和 Version；
- 显示模式与 A/B/并排模式；
- 是否同步视图；
- 高斯模糊参数；
- 三阶/五阶明度阈值；
- 色板数量、随机种子和采样上限；
- 最后成功自动保存时间。

### 5.7 `canvas_states`

保存归一化视图状态：

- `shot_id`；
- `version_id`：参考画布为 `NULL`，当前画布为具体 Version；
- `role`：`reference` 或 `current`；
- 相对缩放；
- 归一化中心 `center_x`、`center_y`；
- 更新时间。

归一化坐标避免把状态绑定到 100% DPI 或具体窗口像素尺寸。

### 5.8 `analysis_runs`

| 字段 | 说明 |
|---|---|
| `id` | 分析运行 ID |
| `asset_id` | 输入资源 |
| `algorithm_id` / `algorithm_version` | 算法身份 |
| `parameters_json` | 规范化参数，包括随机种子和采样上限 |
| `input_sha256` | 运行时输入原始字节哈希 |
| `cache_key` | 上述身份、参数和输入哈希的组合哈希 |
| `status` | `complete`、`failed`、`stale` |
| `created_at` | 运行时间 |

同一 `cache_key` 的已完成结果可复用。算法版本或参数变化不会静默覆盖
历史结果。

### 5.9 `analysis_results`

| 字段 | 说明 |
|---|---|
| `id` | 结果 ID |
| `analysis_run_id` | 所属运行 |
| `result_key` | 如 `luminance_histogram`、`oklab_palette` |
| `evidence_type` | `measurement`、`algorithm_inference`、`art_judgment` |
| `payload_json` | 可直接恢复的结构化数值结果 |
| `artifact_relpath` | 可选派生文件路径 |

测量结果、算法推断和美术判断不得混成同一条记录。M1A 只写入前两类；
美术判断留给后续人工审阅和 AI 交换。

## 6. 已设计、暂不在 M1A 开放的表

以下关系在模型评审中确定，但 UI 和业务功能按开发顺序延后：

- `regions`：矩形归一化坐标、名称、所属资源；
- `region_pairs`：参考区域与 Version 区域的人工配对；
- `review_findings`：带证据类型、来源和状态的审阅发现；
- `tasks`：修改任务、状态、优先级及关联发现；
- `task_version_links`：任务与复查 Version 的关系。

它们应在功能首次实现时通过新的 schema migration 创建，不在 schema v1
建立无业务约束的空壳表。

## 7. 原始资源导入

导入顺序：

1. 从用户选择的路径只读打开源文件；
2. 分块复制到 `assets/originals` 下的临时文件，同时计算 SHA-256 和字节数；
3. 刷新文件缓冲区并关闭；
4. 根据哈希计算最终相对路径；
5. 若同哈希资源已存在则复用，否则原子重命名临时文件；
6. 在数据库事务中写入资源和 Shot/Version 关系；
7. 事务失败时不修改源文件；未引用的临时文件可安全清理。

EXIF 方向修正、ICC 到 sRGB 和分析只发生在读取后的内存工作副本中，绝不
写回 `assets/originals`。

## 8. 保存与自动保存

- 新建项目先在目标目录旁建立临时目录，初始化成功后再原子改名。
- `project.json` 使用同目录临时文件、刷新和 `os.replace` 原子更新。
- SQLite 每次业务修改在显式事务中完成。
- 文本编辑和视图变化使用短延迟防抖自动保存；“保存”命令立即刷新待保存项。
- 只有数据库事务和清单更新都成功后，界面才清除 dirty 状态。
- 保存失败时保留内存中的待保存值，显示非技术性错误，并将异常细节写日志；
  不用空值或旧默认值覆盖用户输入。
- 导入资源、保存业务数据和更新最近项目列表互相隔离；最近列表失败不能损坏项目。

## 9. 最近项目

最近项目不是项目内容，保存在：

```text
%LOCALAPPDATA%/GATalk/recent-projects.json
```

每条只记录项目 ID、名称、清单绝对路径和最后打开时间，最多保留 12 条。
文件使用原子更新。路径失效时在界面标记，只有用户确认或再次刷新时移除。

## 10. 迁移流程

支持版本：

- `MANIFEST_FORMAT_VERSION = 1`
- `DATABASE_SCHEMA_VERSION = 1`

打开流程：

1. 只读解析并校验 `project.json`；
2. 清单格式高于当前支持版本时停止，禁止写入；
3. 打开数据库并核对项目 ID；
4. 读取 `PRAGMA user_version`；
5. 数据库版本高于当前支持版本时停止，禁止写入；
6. 版本较低时先创建一致性备份；
7. 按版本顺序逐个执行迁移；
8. 每个迁移在独立 `BEGIN IMMEDIATE` 事务中执行；
9. 成功后同时写入 `schema_migrations` 和 `PRAGMA user_version`；
10. 全部成功后原子更新清单中的数据库版本。

迁移前备份：

1. 使用 SQLite backup API 将活动数据库复制到备份目录临时文件；
2. 复制迁移前的 `project.json`；
3. 写入包含源/目标版本、时间和校验信息的 `backup.json`；
4. 最后将备份标记为 `complete`；
5. 只有完整备份存在才开始迁移。

失败处理：

- 当前迁移事务回滚；
- 原项目清单不更新；
- 备份保留；
- 项目保持 dirty/未打开状态并显示明确错误；
- 不自动降级，不删除原始资源，不用“最佳猜测”修改数据。

若数据库已经迁移成功但清单更新前进程退出，下一次打开以数据库
`user_version` 为事实来源，在校验项目 ID 后修复清单版本。

## 11. 分析复现和 artifacts

分析缓存键至少包含：

- 输入资源 SHA-256；
- 算法 ID 和算法版本；
- 规范化参数；
- Oklab 随机种子；
- 采样上限；
- 颜色空间和明度公式版本。

结构化结果保存在 `analysis_results.payload_json`，因此重新打开项目时可立即
恢复数字和色板。派生图片只保存在 `artifacts`。artifact 缺失、被用户删除
或校验失败时，界面将结果标为需重建，并以相同参数重新分析。

## 12. M1A 实现边界

本轮实现：

- schema v1、迁移框架和迁移前备份；
- 新建、打开、保存与最近项目；
- Project、Shot、Version 与项目级 Art Brief；
- 原始资源复制、SHA-256 和只读资产；
- 当前工作状态与分析结果恢复；
- 自动保存和失败保护；
- 左侧导航及 M1A 所需界面入口。

本轮不实现：

- 色板来源遮罩；
- 明度区间比较；
- 色板自动/手动匹配；
- 矩形成对区域；
- 审阅发现、修改任务或 AI 审阅包。

这些功能必须等待 M1A 回归测试和用户试用通过。
