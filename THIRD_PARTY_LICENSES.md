# 第三方依赖与许可证

状态：M0.5 初始记录  
日期：2026-07-18

本文件用于工程跟踪，不替代正式法律意见。正式对外发行前必须核对最终打包
产物、传递依赖、许可证文本和通知义务。

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
- Tauri、Electron、Web 服务框架：不符合当前单栈目标。

## Qt LGPL 待办

正式发布前至少完成：

- 核对实际打包的 Qt 模块和各自许可证。
- 随发行包提供相应 LGPL/GPL 文本和版权通知。
- 确保 Qt 动态链接和用户替换库的实际可行性。
- 不移除 Qt 许可声明。
- 根据商业计划决定继续 LGPL 合规或采购 Qt 商业许可。

