# Contributing to GATalk

感谢你参与 GATalk。当前项目处于测试阶段，优先接受可复现缺陷、数据安全问题、
Windows 兼容性改进、文档修订和已有工作流的聚焦增强。

## 提交问题前

1. 搜索已有 Issue。
2. 确认问题出现在最新公开 Beta。
3. 准备最小复现步骤、Windows 版本、显示缩放、GATalk 版本和预期结果。
4. 删除截图或诊断中的 API Key、私人路径、项目机密和无权公开的作品。

安全漏洞请使用 [SECURITY.md](SECURITY.md) 的私密报告流程，不要建立公开 Issue。

## 本地开发

```powershell
git clone https://github.com/WrayMark/GATalk.git
cd GATalk
.\start_dev.cmd
.\scripts\test.ps1
```

要求 Python 3.11 x64。默认测试必须完全离线，不得消耗 API 额度。真实供应商测试需
显式启用、使用个人测试账号，并不得把凭据或响应正文提交到仓库。

## 代码边界

- `core` 只放跨模块契约；业务代码归入相应 `modules/<module_id>`。
- `analysis` 不导入 PySide6；`storage` 不导入 UI。
- 原图只读，派生产物可重建；图像和网络重任务离开 GUI 线程。
- 固定界面文案以简体中文为源并进入本地化目录。修改文案时同步更新繁中、英文、
  日文和法文目录，且不要把机器翻译标成已完成母语审校。
- 新依赖需说明许可证、Windows wheel、包体和打包影响。

更完整的持续开发规则见 [AGENTS.md](AGENTS.md)。

## Pull Request

- 从最新默认分支创建聚焦分支；不要把无关格式化混入功能修复。
- 增加或更新测试，并运行 `scripts/test.ps1`。
- 用户可见变化同步更新 `CHANGELOG.md`、中英文手册和必要截图。
- 说明数据迁移、兼容性、网络发送、许可证和已知限制。
- 提交信息简短、具体；不要伪造或重写历史时间。

提交贡献即表示你有权提交相关代码、文本和素材，并同意贡献按仓库的 MIT License
发布。不要提交来源不明的图片、字体、模型、提示词或第三方源码。
