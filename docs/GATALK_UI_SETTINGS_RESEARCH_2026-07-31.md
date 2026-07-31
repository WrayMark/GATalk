# GATalk 界面与全局设置调研

日期：2026-07-31  
范围：Windows 桌面外壳、主题、设置和既有 Qt Widgets 工作台统一

## 结论

本轮不更换 PySide6，也不增加第三方 UI 框架。采用 Qt 原生调色板、样式表和
集中式设计令牌，能够满足浅色、深色、跟随系统、强调色、字号和密度，同时
维持当前打包体积、商业许可边界和三个工作台的稳定性。

## 采用的设计原则

1. 使用中性底色和有限层级，不把每个控件都做成高反差边框。
2. 强调色只用于主要动作、当前页签、焦点和状态，不铺满整个界面。
3. 首页先表达产品与任务，再让用户选择工作台。
4. 工作台内统一菜单、工具栏、停靠面板、输入、表格、页签和滚动条。
5. 深浅主题保持同一信息层级，不仅做颜色反转。
6. 主题、字号和布局属于应用偏好，不写入项目业务数据。

这些原则参考 Windows 11 的层级、材质、颜色与清晰任务流建议，以及
WinUI Gallery 的控件组织方式；实现仍是独立的 Qt Widgets 代码。

## 技术依据

- Qt `QStyleHints.colorScheme` 可读取平台配色，并通过
  `colorSchemeChanged` 响应系统主题变化。
- Qt Style Sheets 能够集中覆盖既有 Widgets，不要求重写成 QML。
- `QPalette` 提供绘图控件和未显式样式控件的语义颜色。
- `QMainWindow.saveGeometry/saveState` 可保存窗口、停靠面板和工具栏布局。

## 调研来源

- Qt QStyleHints：
  https://doc.qt.io/qt-6/qstylehints.html
- Qt Style Sheets：
  https://doc.qt.io/qt-6/stylesheet.html
- Windows 11 设计原则：
  https://learn.microsoft.com/en-us/windows/apps/design/design-principles
- Windows 应用主题：
  https://learn.microsoft.com/en-us/windows/apps/develop/ui/theming
- Windows 颜色指导：
  https://learn.microsoft.com/zh-cn/windows/apps/design/signature-experiences/color
- Microsoft WinUI Gallery：
  https://github.com/microsoft/WinUI-Gallery
- PyQt-Fluent-Widgets：
  https://github.com/zhiyiYo/PyQt-Fluent-Widgets
- qt-material：
  https://github.com/UN-GCPDS/qt-material

## 依赖与许可证判断

PyQt-Fluent-Widgets 的公开仓库说明免费版本为 GPLv3，并另售商业许可。
GATalk 未来保留商业发布可能，因此本轮不引入。`qt-material` 可作为样式组织
参考，但引入新主题依赖没有必要。没有复制上述仓库代码、图标、样式资源或
提示词。

## 兼容策略

- 用户可见品牌改为 GATalk。
- Python 包、模块 ID、数据库和 `.scenelens*` 扩展名保持不变。
- 新设置进入 `%LOCALAPPDATA%/GATalk`。
- 最近项目和 Windows 凭据读取旧 SceneLens 路径后迁移，不要求用户重新配置。
