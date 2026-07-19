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
