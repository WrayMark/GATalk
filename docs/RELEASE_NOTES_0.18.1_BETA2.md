# GATalk 0.18.1 Beta 2

发布日期：2026-08-14

这是一次多语言文档与发布包修订。应用功能范围与 Beta 1 基本一致。

## 本次修订

- 英文 README 和英文使用手册改用英文界面截图；简中手册继续使用简中截图。
- 仓库首页明确列出界面语言：简体中文为基准界面，英语、繁体中文、日语和法语为预览。
- Windows 发布包同时附带简中、英文 Word 手册和对应的 Markdown、截图资源。
- 修正少量自绘分析文案和多行输入框占位文本未随语言切换的问题。

## 下载与启动

下载 `GATalk-0.18.1-beta.2-windows-x64.zip`，完整解压后运行
`GATalk/GATalk.exe`。这是未签名的 Windows x64 测试版；请先核对
`SHA256SUMS.txt`。GitHub 自动生成的 Source code 压缩包不包含可运行 EXE。

## 已知限制

- 除简体中文外的界面语言仍需母语审校。
- 程序未进行代码签名，首次启动可能出现 Windows SmartScreen 提示。
- 真实 AI 服务的模型、地区、额度和接口兼容性需要用户自行验证。

---

## English

This release corrects the multilingual documentation and Windows package. The
application scope is otherwise substantially unchanged from Beta 1.

- The English README and guide now use screenshots captured from the English UI.
- The repository states the current language status: Simplified Chinese is the
  reference UI; English, Traditional Chinese, Japanese, and French are previews.
- The Windows package includes separate Chinese and English Word guides,
  Markdown guides, and matching screenshots.
- A small set of custom-painted analysis labels and multiline placeholders now
  follows the selected interface language.

Download `GATalk-0.18.1-beta.2-windows-x64.zip`, extract the complete archive,
and run `GATalk/GATalk.exe`. This is an unsigned Windows x64 beta. Verify the
published SHA-256 before launch. GitHub's automatically generated source archives
do not contain a runnable EXE.
