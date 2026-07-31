# M1B.2 成对区域数据模型

状态：schema v4 / M1B.2A 实现基线  
日期：2026-07-19

## 1. 模型结论

区域使用经过 EXIF 方向纠正后的工作图坐标，并归一化为 `x`、`y`、`width`、
`height`，范围为 0 至 1。坐标不依赖窗口尺寸、DPI、画布缩放、平移或分析代理图。

参考区域绑定 Shot 的主要参考图，`version_id` 必须为空；当前区域绑定具体
Version，`version_id` 必须存在。同一参考区域允许被多个 Version 的区域对复用，
但每个 Version 的当前区域是独立记录。

## 2. schema v4

### `visual_review_regions`

- `id`
- `module_id`
- `shot_id`
- `image_role`：`reference` 或 `current`
- `version_id`
- `name`
- `semantic_type`
- `rect_x`、`rect_y`、`rect_width`、`rect_height`
- `created_at`、`updated_at`

数据库约束保证矩形非空且不越界，并保证参考区域不绑定 Version、当前区域必须绑定
Version。

### `visual_review_region_pairs`

- `id`
- `shot_id`
- `reference_region_id`
- `current_region_id`
- `name`
- `semantic_type`
- `notes`
- `created_at`、`updated_at`

第一版只支持一对一配对。`current_region_id` 唯一；`reference_region_id` 不唯一，
因为同一个 Shot 的参考区域需要复用于多个截图 Version。

“待配对”不是不完整 Pair 记录，而是尚未进入 Pair 的独立 Region。这样完整 Pair
始终具有两侧外键，分析器不需要处理半条关系。

### `visual_review_region_analyses`

- `id`、`pair_id`
- `module_id`、`analyzer_id`、`analyzer_version`
- `reference_image_hash`、`current_image_hash`
- 双方区域几何快照
- `shared_palette_cache_key`
- `parameters_json`、`cache_key`
- `result_json`、`status`、`created_at`

区域移动或缩放后，与该区域相关的完成分析立即标记为 `stale`。M1B.2B 的缓存键还会
覆盖双方图片哈希、明度阈值、低彩度阈值、共享色板身份和分析器版本，因此这些输入
变化不会命中旧结果。

## 3. Version 复制语义

“复制上一版本区域”执行以下操作：

1. 选择当前 Shot 中最近且已有区域对的较早 Version；
2. 复用参考 Region；
3. 为目标 Version 克隆每个 Current Region，生成新 ID；
4. 为目标 Version 生成新 Pair ID；
5. 不复制旧分析结果。

后续移动新 Version 的当前区域不会修改旧 Version。复制完成后界面明确要求用户检查
位置，软件不推断不同 Version 已精确对齐。

## 4. 迁移与回退

schema v3 打开时先使用 SQLite backup API 备份 `project.db`，并复制
`project.json` 与备份元数据，再执行 v4 迁移。模块数据版本由 2 升至 3。
高于 v4 的项目继续拒绝写入；只读模式不执行迁移。

## 5. 模块边界

- `ui.image_canvas` 只提供与业务无关的归一化矩形叠层交互。
- `modules.visual_review.ui.RegionController` 负责 GATalk 的区域工作流。
- `modules.visual_review.RegionStore` 拥有模块表 SQL。
- `ProjectStore` 只暴露受模块 ID 限制的连接事务边界。
- M1B.2B 的像素统计继续放在纯 NumPy `analysis`，通过分析器注册表运行。

这次局部拆分解决了区域业务继续堆入 `MainWindow` 的扩展障碍，但没有引入动态插件
系统或为未知模块制造抽象。
