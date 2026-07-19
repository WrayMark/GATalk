# SceneLens

SceneLens 是一款面向游戏场景美术、UE 地编和环境艺术作品的 Windows
本地游戏场景美术控制工作台。它将制作目标、参考图、当前截图、证据测量、
AI 专项审阅、修改任务、优化预演、新版本复查和质量门禁串成可追踪的工作流。

M0.5、M1A、M1B.1 和 M1B.2 已于 2026-07-19 通过真实项目人工验收并冻结。
当前 `0.3.0a0` 开始开发 **M2 AI 主美控制台与灯光审片台**。

## 环境要求

- Windows 10/11 x64
- Python 3.11 x64
- 首次安装依赖时需要网络连接

## 一键启动

双击根目录下的 `start_dev.cmd`。脚本会：

1. 检查 Python 3.11 x64；
2. 在项目目录创建 `.venv`；
3. 安装锁定的开发依赖；
4. 启动 SceneLens。

命令行启动方式：

```powershell
.\start_dev.cmd
```

当前图片工作台操作：

- 使用“新建项目”创建 `.scenelens` 项目目录，或选择项目内的
  `project.json` 打开已有项目。
- 在左侧创建 Shot，通过“Art Brief”填写项目目标与制作上下文。
- 项目模式下，“参考图”会更新当前 Shot 的参考；“当前截图 / 新版本”会
  追加 Version。直接拖入左右画布也遵循相同规则。
- `Ctrl+S` 立即保存；视图、显示模式和当前 Version 会自动保存。
- 未打开项目时仍可直接拖入两张图片，继续使用不落盘的 M0.5 工作方式。
- 将参考图和当前截图分别拖到左右画布，或点击“导入”按钮。
- 鼠标滚轮缩放，按住左键拖动画面，双击恢复适配。
- “同步视图”开启时，两张不同尺寸图片按归一化中心和相对缩放同步。
- 使用“显示”切换原图、灰度、三阶和五阶明度。
- 模糊滑杆范围为高斯 `sigma=0.0–20.0`。
- 选择“A/B 单图”后按空格快速切换。
- 在“对比分析”页进入区域模式，分别在参考图和当前截图创建矩形；选中双方
  区域后建立配对。
- 选中区域可移动和用八向手柄调整；Esc 退出区域模式或颜色遮罩。
- 区域详细比较显示明度、P10/P50/P90、Oklab、彩度、色相和共享色板组成。
- 新截图 Version 可复制上一版本区域，复制后需人工检查位置。

## 测试

```powershell
.\scripts\test.ps1
```

## 构建 Windows Alpha

```powershell
.\build_alpha.cmd
```

输出目录为 `dist/SceneLens/`。这是 PyInstaller `onedir` 目录，不需要目标
电脑预装 Python。

`pyproject.toml` 固定直接依赖；`requirements-lock.txt` 保存本轮已验证环境的
完整版本快照。

## 文档

- [PROJECT_BRIEF.md](PROJECT_BRIEF.md)：产品目标与范围
- [DECISIONS.md](DECISIONS.md)：已接受的产品与技术决策
- [ROADMAP.md](ROADMAP.md)：开发阶段与验收标准
- [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)：依赖与许可证记录
- [AGENTS.md](AGENTS.md)：持续开发规则
- [M0.5_VALIDATION.md](M0.5_VALIDATION.md)：技术验证结果
- [M1A_VALIDATION.md](M1A_VALIDATION.md)：M1A 工程验证与人工试用步骤
- [M1B.2_VALIDATION.md](M1B.2_VALIDATION.md)：M1B.2 自动验证与人工试用步骤
- [docs/M1_DATA_MODEL.md](docs/M1_DATA_MODEL.md)：M1 数据结构与迁移方案
- [docs/M2_DATA_MODEL.md](docs/M2_DATA_MODEL.md)：M2 共享核心与 schema v5
- [docs/COMPETITOR_REVIEW_M2.md](docs/COMPETITOR_REVIEW_M2.md)：M2 竞品审查
- [docs/M1B2_REGION_DATA_MODEL.md](docs/M1B2_REGION_DATA_MODEL.md)：区域 schema 与 Version 语义
