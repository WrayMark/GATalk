# 资产拆分工作台架构与数据模型

版本：0.7.0  
模块 ID：`scenelens.asset_breakdown`

## 1. 模块边界

资产拆分是第三个内置工作区，不依赖场景审阅的 Shot/Version，也不依赖作品研究
状态。它复用的公共能力只有：

- 工作区与审阅器注册契约；
- Vision/ImageEdit Provider、凭据、主动发送门禁、取消、超时、重试和脱敏；
- 图片读取、EXIF/ICC/sRGB 工作副本；
- 原子 JSON 写入、操作系统写锁和通用画布。

模块自己的模型、配置、Schema、存储、业务服务和 UI 位于
`modules/asset_breakdown`。本地图像遮罩算法位于 `analysis/asset_masks.py`，
不导入 PySide6。

## 2. 项目包

扩展名：`.scenelens-assets`

```text
asset_project.json
assets/
artifacts/
  masks/
  generated/
  boards/
exports/
```

`asset_project.json` 使用 `format=scenelens.asset_breakdown`、
`format_version=1` 和 `module_schema_version=1`。高版本项目拒绝写入。保存为
原子替换；同一项目只允许一个写进程，异常退出遗留锁由操作系统锁判断并恢复。

## 3. 核心实体

`SourceImage`

- `image_id`、`role=main|reference`
- 原文件名、项目内相对路径、SHA-256、尺寸、导入时间

`AssetItem`

- 身份：`asset_id`、名称、分类、语义、父资产、层级
- 位置：EXIF 纠正后主图的 `[x,y,width,height]` 归一化矩形
- 来源：原画可见证据、AI 推断、用户补充/修订
- 证据：可见证据、推断内容、不确定性、可信度、遮挡状态
- 生产：复用组、实例数、优先级、制作策略、模块零件、变体、材质说明
- 派生：是否勾选生成、遮罩路径、遮罩方法、用户修订状态

`GenerationRecord`

- 生成 ID、资产 ID、输出类型
- 主图 SHA-256、来源矩形
- Provider、模型、结构化参数
- 产物相对路径、状态、脱敏错误和时间

`AIRun`

- 模块/审阅器/版本、Provider/实际模型
- 主图与补充参考哈希
- 场景类型和输出预算
- 场景摘要、生产策略、资产关系和不确定性

导出记录只保存文件名、计数和时间，不保存用户外部绝对路径。

## 4. 信息真实性

一条资产记录可以同时包含直接可见证据和 AI 推断，但二者分字段保存：

- `visible_evidence` 只能描述主图可核对的像素、位置、轮廓和重复。
- `inferred_details` 保存类别、模块边界、复用或结构推断。
- `uncertainty` 保存遮挡、背面、尺度和材质无法确认的部分。
- AI 图片输出只存在 `GenerationRecord`，不自动改变资产证据来源。

用户修订使用 `user_modified=true`，后续重新 AI 拆分时保留；上一批未修改的
AI 层可以替换。原始输入永远不重新保存。

## 5. Provider 流程

AI 拆分：

1. 主图与最多三张补充参考转为去元数据、限边长的内存 PNG。
2. 用户查看供应商、模型、字段、图片大小与哈希后确认。
3. Provider 返回严格 JSON；本地完整 Schema 再验证 ID、父级、关系和坐标。
4. 记录实际模型和全部输入哈希。

资产生成：

1. 只处理清单中勾选的资产。
2. 发送全图上下文与本地可见像素裁剪。
3. 指令来自资产结构化字段和三种固定输出模式，不从 Markdown 解析。
4. 顺序执行，单项失败不删除成功项；支持取消和有限重试。
5. 保存每项 Provider、模型、参数、来源区域和输入哈希。

## 6. 本地遮罩

`visible_asset_mask()` 只在资产矩形内部运行 GrabCut：

- 成功：`grabcut_visible_v1`；
- 区域太小、图像退化或算法失败：`rectangle_proxy_v1`。

两者都是算法推断，不是开放词汇识别，也不会补全遮挡像素。遮罩变化不修改
原图；资产矩形修改后旧遮罩路径会清空。

## 7. 未来扩展位置

当前字段已为以下能力保留稳定锚点：

- 3D Provider：以资产 ID、生成记录和来源区域作为输入，不改变当前实体。
- 资产库匹配：新增匹配记录，引用资产 ID 和库中 Asset ID。
- UE 导出：消费结构化清单、复用组和制作策略，不把外部路径写回输入资产。
- 制作任务：将选中资产转为共享 `Task`，保持模块 ID。
- 更强分割：新增 mask analyzer/version，不覆盖旧遮罩来源。

本版不实现第三方插件市场、动态未知代码、本地大模型或生产三维生成。

