# Changelog

## Unreleased

### Changed

- 开始 M1A 项目、Shot、Version 与保存恢复开发。

## 0.0.5 — 2026-07-19

### Added

- 确认 SceneLens 产品边界、技术栈和 M0.5 范围。
- 建立项目文档、Python `src` 布局、一键启动与测试入口。
- 完成参考图/当前截图拖放、双画布并排、同步缩放和平移与 A/B 切换。
- 完成灰度、可调高斯模糊、三阶/五阶明度视图。
- 完成线性 sRGB 明度计算、直方图和默认 8 色 Oklab 色板。
- 完成 EXIF 方向、ICC 到 sRGB、中文空格路径和常用图片格式验证。
- 完成后台图片读取/分析和 PyInstaller `onedir` 功能烟测。

### Validation

- 19 项自动化测试通过。
- 用户使用真实图片完成试用，未发现影响使用的问题；M0.5 正式冻结。
