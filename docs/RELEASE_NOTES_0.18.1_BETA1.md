# GATalk 0.18.1 Beta 1

这是 GATalk 的首个公开测试版。项目仍在调整界面、项目格式和 AI 供应商兼容性，
重要项目请保留独立备份。

> 普通用户请在下方 **Assets** 中下载
> `GATalk-0.18.1-beta.1-windows-x64.zip`。GitHub 自动提供的
> `Source code (zip)` 和 `Source code (tar.gz)` 仅包含源码，没有可运行的 EXE。

## 主要功能

- 场景美术控制：参考图与 UE 截图对比、证据测量、区域分析、AI 专项审阅与版本复查。
- 作品研究与对照研究：单图拆解、学习记录，以及 2–6 幅作品并置比较。
- 资产拆分工作台：可校正资产清单、拆分层级、自动资产板和生成提示语。
- 参考资料与知识库，以及跨项目制作任务与验收中心。
- 简体中文基准界面；繁中、英语、日语和法语目前为预览。

## Windows 版本

下载 `GATalk-0.18.1-beta.1-windows-x64.zip`，完整解压后运行
`GATalk/GATalk.exe`。程序未签名，首次启动前请核对 `SHA256SUMS.txt`。

本次构建通过 295 项离线自动化测试，以及 100%、125% 和 150% Windows 缩放烟测。
尚未完成无 Python 独立设备验收、代码签名、各 AI 供应商真实账号全覆盖测试和非简中
语言母语审校。

## 数据与 AI

项目默认本地保存，原图只读。软件没有遥测、后台上传或自动更新。真实 AI 请求必须
由用户主动确认；API Key 可存入 Windows Credential Manager。离线 Mock 只验证流程，
不是本地视觉模型。

完整安装、限制和隐私说明见仓库 `README.md`、`SECURITY.md` 与发布包内使用手册。

---

This is the first public beta of GATalk. It includes visual comparison and scene
review, single-artwork and comparative study, asset breakdown, a reference
library, and cross-project production tasks. The Windows build is unsigned.
Regular users should download `GATalk-0.18.1-beta.1-windows-x64.zip` under
**Assets**. GitHub's automatically generated source archives do not contain a
runnable EXE.
Please verify `SHA256SUMS.txt`, extract the full archive, and run
`GATalk/GATalk.exe`.

The build passed 295 offline automated tests and packaged smoke tests at 100%,
125%, and 150% Windows scaling. Clean-PC validation, comprehensive live-provider
testing, code signing, and native-language review outside Simplified Chinese are
still pending. GATalk has no telemetry or automatic background upload; network
requests require an explicit user action.
