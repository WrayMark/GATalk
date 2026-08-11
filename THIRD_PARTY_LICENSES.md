# 第三方依赖与许可证

状态：M1A 已复核
初始日期：2026-07-18
最近复核：2026-08-08

本文件用于工程跟踪，不替代正式法律意见。正式对外发行前必须核对最终打包
产物、传递依赖、许可证文本和通知义务。

M1A 使用 Python 3.11 标准库 `sqlite3` 和 `hashlib` 实现项目存储与哈希，
没有新增第三方运行依赖，也没有变更下列固定版本。

0.15.0 的全局检索、恢复点、任务依赖、生产交接和视觉资料板继续仅使用现有
Python、Qt、SQLite、Pillow 与标准库能力，没有新增第三方依赖。

## 运行依赖

| 依赖 | 固定版本 | 用途 | 许可证 | 商业化与分发注意 |
|---|---:|---|---|---|
| Python | 3.11.x x64 | 运行时 | PSF License | PyInstaller 会随包分发解释器组件 |
| PySide6 / Qt for Python | 6.11.1 | Windows UI | LGPLv3/GPLv3 或商业许可 | 当前采用社区版；保留动态库、许可证和替换能力；对外发行前复审 |
| Pillow | 12.3.0 | 解码、EXIF、ICC | HPND | 允许商业使用；需保留许可通知 |
| NumPy | 2.3.5 | 数组与数值计算 | BSD-3-Clause | 允许商业使用；记录二进制依赖通知 |
| opencv-python-headless | 4.13.0.92 | 滤镜、直方图、聚类 | Apache-2.0 | 允许商业使用；最终包附许可证与 NOTICE（如适用） |
| Colour Science | 0.4.7 | Oklab 与色彩转换 | BSD-3-Clause | 允许商业使用；其传递依赖也需记录 |

## 开发与打包依赖

| 依赖 | 固定版本 | 用途 | 许可证 | 注意 |
|---|---:|---|---|---|
| pytest | 9.1.1 | 单元测试 | MIT | 不进入正式运行时 |
| pytest-qt | 4.5.0 | Qt 测试 | MIT | 不进入正式运行时 |
| PyInstaller | 6.21.0 | Windows `onedir` | GPL-2.0-or-later + Bootloader Exception | 例外允许分发构建程序；若修改 bootloader 需重新审查 |

## 明确不采用或暂缓

- Color Thief Python：长期不活跃，RGB/MMCQ 不符合 Oklab 路线。
- scikit-image：M0.5 无具体必要算法，不加入初始运行依赖。
- Depth Anything V2：模型权重、PyTorch 和商业许可证风险，推迟。
- SAM 2：Windows/CUDA 打包复杂，推迟。
- Grounding DINO：Apache-2.0；开放词汇检测有价值，但会引入 PyTorch、
  模型权重和新的打包边界，0.7.0 不集成、不复制代码。
- Florence-2 base：模型页标注 MIT；仍需 Transformers/PyTorch 和权重，
  0.7.0 不集成。
- LaMa：Apache-2.0；旧 PyTorch/CUDA 环境和外部权重不进入当前安装包。
- Zero123++：代码 Apache-2.0，但模型权重 CC-BY-NC 4.0，不作为未来商业
  默认能力。
- TripoSR：代码与权重 MIT；约 6 GB VRAM 的 3D 路线仅作为未来候选，本版
  不集成。
- Tauri、Electron、Web 服务框架：不符合当前单栈目标。

M6 资产拆分只复用已锁定的 OpenCV GrabCut 和 Pillow，没有复制调研仓库代码、
提示词或模型权重，也没有新增运行依赖。

0.8.0 未新增运行依赖，也未复制外部仓库代码、模型权重或提示词。SAM 2、
Grounded SAM 2、Florence-2 与 Qwen2.5-VL 仅用于技术路线调研，当前安装包
未包含它们。Nano Banana 是远程服务产品名，不是随程序分发的第三方库。

0.16.0 未新增运行依赖。双图分布、审阅历史、灯光 Schema 和统一导航均为项目
内部实现，没有复制第三方界面代码、模型权重或提示词。

## Qt LGPL 待办

正式发布前至少完成：

- 核对实际打包的 Qt 模块和各自许可证。
- 随发行包提供相应 LGPL/GPL 文本和版权通知。
- 确保 Qt 动态链接和用户替换库的实际可行性。
- 不移除 Qt 许可声明。
- 根据商业计划决定继续 LGPL 合规或采购 Qt 商业许可。
