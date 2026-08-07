# GATalk 资产工作流与界面审查

日期：2026-08-08

## 审查目标

本轮不做纯装饰换肤。审查范围是资产拆分工作台的任务结构、导航层级、
动作命名、状态反馈、方案追溯和桌面生产工具密度。

## 参考依据

- Blender 使用面向任务的 Workspace 组织编辑器区域。GATalk 保留独立工作台，
  在单个工作台内持续显示当前项目与拆分依据，不把完整流程塞进一个长页面。
  参考：<https://docs.blender.org/manual/en/latest/interface/window_system/workspaces.html>
- Microsoft Fluent 2 建议导航标签简短、可扫描并围绕用户目标；次要动作不应
  堆进导航项。GATalk 顶层只保留“清单与校正、自动资产板、生成提示语”，
  编辑动作留在对应工作区。参考：
  <https://fluent2.microsoft.design/components/web/react/core/nav/usage>
- Fluent 2 的页面级消息应放在命令区下方并给出解决动作。GATalk 将当前拆分
  依据固定在工作区顶部，过期结果直接说明原因和重新生成方式。
  参考：<https://fluent2.microsoft.design/components/web/react/core/messagebar/usage>
- Adobe Spectrum 认为标签页只适合组织同等重要且相关的内容，并应避免同形态
  的多层嵌套。GATalk 区分顶层工作方式与内部编辑页，使用不同密度和清晰标题。
  参考：<https://spectrum.adobe.com/page/tabs/>
- Spectrum 建议强调按钮只用于当前视图的核心动作；常规编辑动作保持低强调。
  GATalk 每个页面只突出一个主要执行动作，新增、拆分、合并、删除保持次级。
  参考：<https://spectrum.adobe.com/page/button/>、
  <https://spectrum.adobe.com/page/action-button/>
- Qt 官方建议让标准控件继续表达活动、悬停、按下、禁用和系统调色板状态。
  本轮继续使用 Qt Widgets、QPalette、QSplitter 和局部样式层，不自绘一套无法
  随高 DPI 与主题变化的控件。
  参考：<https://doc.qt.io/qt-6/qwidget-styling.html>、
  <https://doc.qt.io/qt-6/qsplitter.html>

## 采用的界面原则

1. 顶部固定显示当前拆分方案、确认状态、场景结构关联和主要类别深度。
2. 三种工作方式共享同一依据，但资产清单、自动资产板和提示语输出独立保存。
3. 方案修改后，旧输出标记为“旧版依据”，不删除、不自动混入当前结果。
4. 页面名称使用行业动作与产物名称，避免“一键、强大、智能、让 AI”等宣传式
   或拟人化表达。
5. 状态文案采用“状态 + 结果/原因 + 下一步”；错误对话框保留解决办法，技术
   细节写入日志或展开信息。
6. 深浅主题、强调色、字号与界面密度继续由全局设置控制；工作台局部样式只
   增强层级，不写死主题颜色。

## 明确不采用

- 不引入 Web UI 框架或大型第三方 Qt 主题库。
- 不使用大量阴影、玻璃效果、渐变卡片和装饰图标挤占原画画布。
- 不把三个工作方式合并成单个不可追溯的“自动流程”。
- 不让方案变化静默改写已有 AI 结果。
