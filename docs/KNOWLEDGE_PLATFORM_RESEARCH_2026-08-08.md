# GATalk 参考资料平台与对照研究调研记录

日期：2026-08-08

## 结论

“参考资料与知识库”不应是与场景审阅、作品研究和资产拆分同级的第四个工作台。
它是跨工作台的信息基础设施，负责资料的规范来源、分类、检索、复用和交接；
具体研究与生产任务仍由专业工作台完成。

首个启用资料域是“美术参考资料”。关卡设计和策划资料域只注册边界，本版不制造
空壳页面。启用新资料域不应要求修改美术资料数据结构。

## 资料组织

- Zotero 的资料条目归资料库所有，同一条目可以进入多个集合而不复制，集合更像
  播放列表；同时支持层级集合、标签和保存搜索。这适合 GATalk 的“一份来源，
  多种研究语境”。来源：[Zotero Collections and Tags](https://www.zotero.org/support/collections_and_tags)
- Adobe Bridge 用集合跨越物理文件夹组织文件，并用层级关键词检索。说明逻辑分类
  不应被硬绑定到磁盘目录。来源：[Adobe Bridge Collections](https://helpx.adobe.com/bridge/desktop/organize-and-find-files/organize-files-and-folders/use-collections.html)、
  [Adobe Bridge Keywords](https://helpx.adobe.com/uk/bridge/desktop/organize-and-find-files/tag-and-find-files/use-keywords.html)
- Blender Asset Browser 使用来源、目录树、资产网格和详情区的三段结构，并支持
  嵌套目录与 Shift 多选。GATalk 因此采用“领域/集合—资料列表—详情”的三栏界面。
  来源：[Blender Asset Browser](https://docs.blender.org/manual/en/4.1/editors/asset_browser.html)
- PureRef 的优势是快速拖入、链接或嵌入、批量选择与整理。GATalk 吸收快速导入和
  多选，但不把自由画布作为首版资料库的核心，以免检索与来源记录退化。
  来源：[PureRef Images](https://new.pureref.com/handbook/2.0/images/)、
  [PureRef Organize](https://pureref.com/handbook/images/organize/)

## 对照研究方法

- Getty 的形式分析教学强调先描述、再分析视觉元素与设计原则，并要求用相关、
  充分的画面证据支撑比较。来源：[Getty Formal Analysis](https://www.getty.edu/education/teachers/classroom_resources/formal_analysis.html)、
  [Getty Comparing Portraits](https://www.getty.edu/education/k-12-learning/comparing-portraits/)
- 美国国家美术馆的教学资料强调 close looking、学习视觉词汇，以及用同一主题的
  多件作品比较颜色、气氛和情绪。来源：[NGA Elements of Art: Color](https://www.nga.gov/educational-resources/elements-art/elements-art-color)
- 学术形式分析常用形状、构图、色彩、空间、表面/肌理和光等类别。GATalk 在此
  基础上加入游戏美术常用的视觉层级、边缘细节、材质、环境叙事和风格技法，但
  不用总分替代分析。来源：[A framework for the analysis of art](https://pmc.ncbi.nlm.nih.gov/articles/PMC7546898/)

对照研究采用同轴问题：每个比较维度同时观察全部作品，分别记录共同点、差异、
画面证据、视觉作用、解释、置信度和边界。测量差异不自动转换为质量判断。

## 任务与状态呈现

- VS Code 建议长任务用进度通知和输出详情，避免重复通知。来源：
  [VS Code Notification Guidelines](https://code.visualstudio.com/api/ux-guidelines/notifications)
- Visual Studio Tasks 窗口展示任务 ID、状态、开始时间、持续时间、位置和父子关系。
  GATalk 首版保留任务、状态、供应商、模型、进度、重试和错误详情，不保存密钥、
  图片或完整请求正文。来源：[Visual Studio Tasks Window](https://learn.microsoft.com/en-us/visualstudio/debugger/using-the-tasks-window?view=visualstudio)

## 本版不采用的方向

- 不自动抓取网页：版权、站点条款、登录状态和内容变更会引入新的产品与安全范围。
- 不做向量数据库和本地视觉模型：当前条目规模与检索需求尚不能证明依赖和打包成本。
- 不做动态第三方插件：继续使用可信内置模块的显式注册。
- 不把资料库变成笔记软件、网盘或资产商城；本版只解决来源、集合、标签、检索、
  研究交接和保存恢复。

