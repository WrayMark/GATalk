# 第三方依赖与许可证

状态：`0.18.1 Beta 1` 公开发布审计；复核日期：2026-08-14。

本文记录 GATalk 直接依赖与公开二进制分发边界，不构成法律意见。实际 Release
随附机器生成的 `THIRD_PARTY_NOTICES.txt`、`licenses/` 和 `QT_SOURCE_OFFER.md`。

## 运行依赖

| 组件 | 固定版本 | 用途 | 许可证 | 发布处理 |
|---|---:|---|---|---|
| Python | 3.11.x x64 | 解释器与标准库 | PSF License | 许可证随包提供 |
| PySide6 Essentials / Shiboken6 | 6.11.1 | Qt Widgets 桌面 UI | LGPL-3.0-only 或 GPL/商业许可 | 采用 LGPL；动态 DLL、完整许可文本和精确对应源码随 Release 提供 |
| Qt Base / Qt SVG | 6.11.1 | Core、Gui、Widgets、Network、OpenGL、SVG 与平台/图片插件 | LGPL-3.0-only 及各组件第三方许可 | 仅收集实际所需模块；许可目录、通知和源码归档随 Release 提供 |
| Pillow | 12.3.0 | 解码、EXIF、ICC、缩略图 | MIT-CMU 及随 wheel 组件许可 | 完整 wheel 许可文本随包提供 |
| NumPy | 2.3.5 | 数组与数值计算 | BSD-3-Clause；wheel 含 OpenBLAS、LAPACK 与 GCC Runtime Exception 等 | 使用 wheel 的完整 `LICENSE.txt`，不自行摘录 |
| opencv-python-headless | 4.13.0.92 | 滤镜、直方图、聚类、GrabCut | Apache-2.0；wheel 含第三方编解码器通知 | `LICENSE.txt` 与 `LICENSE-3RD-PARTY.txt` 随包提供 |
| Colour Science | 0.4.7 | Oklab 与色彩转换 | BSD-3-Clause | 许可证随包提供 |
| typing_extensions | 4.16.0 | 兼容类型定义 | PSF-2.0 | 许可证随包提供 |

## 开发与构建依赖

| 组件 | 固定版本 | 用途 | 许可证 | 发布处理 |
|---|---:|---|---|---|
| pytest | 9.1.1 | 自动化测试 | MIT | 不作为运行时模块打包 |
| pytest-qt | 4.5.0 | Qt UI 测试 | MIT | 不作为运行时模块打包 |
| PyInstaller | 6.21.0 | Windows `onedir` | GPL-2.0-or-later + Bootloader Exception | Bootloader 进入发行包；完整构建许可随包提供，未修改 bootloader |
| pyinstaller-hooks-contrib | 2026.6 | 构建钩子 | GPL/Apache 等混合，按文件标注 | 只在构建期使用，不把钩子源码作为应用运行模块发布 |

## Qt LGPL 发布方式

- GATalk 自有源码使用 MIT；Qt for Python 与 Qt 保持其 LGPL-3.0-only 许可证。
- PyInstaller 使用 `onedir`，Qt 以独立 DLL 分发；不静态链接、不修改 Qt DLL、
  不禁止用户调试或替换这些库。
- `GATalk.spec` 只保留 Core、Gui、Widgets、Network、OpenGL、SVG 及实际平台、图片、
  TLS 插件；不发布未使用的 QML、Quick、PDF 或虚拟键盘组件。
- Release 同时提供精确版本的 `pyside-setup`、`qtbase`、`qtsvg` 对应源码归档和
  SHA-256，避免仅依赖上游链接。
- 所有 Qt/PySide 与内含第三方许可证文本保存在仓库 `licenses/` 并进入二进制包。

## 未随程序分发的研究候选

Grounding DINO、SAM 2、Florence-2、LaMa、Zero123++、TripoSR、Argos Translate、
OpenCC 与翻译模型只出现在调研或开发记录中；其代码、模型权重和数据集不进入 Git、
运行依赖或 Windows 发行包。研究文档中的外部链接不表示 GATalk 重新分发相关内容。

M2 竞品审查仅记录公开页面和产品分类。未复制无明确许可证的 Pro 版代码或长提示词；
也未复用灯光版代码。若未来实际复用，必须在合并前记录来源文件、提交、许可证、
版权声明和修改范围。

## 生成与复核

```powershell
.\.venv\Scripts\python.exe .\scripts\collect_third_party_notices.py
```

每次升级运行时依赖后必须重新生成通知、核对实际打包二进制，并重新取得精确版本的
对应源码。正式商业发行、安装器或代码签名前仍建议进行独立法律审查。
