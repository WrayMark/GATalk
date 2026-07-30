# 作品研究方法调研

日期：2026-07-30

用途：为 SceneLens“作品研究”模块建立可解释、可教学的单图研究方法。

## 结论

作品研究不能只是把“构图、色彩、明度、光影”逐项填满。有效的主美式拆解应按
以下顺序工作：

1. 先描述实际可见内容，不急于归因。
2. 观察视觉元素之间的关系，而不是孤立罗列元素。
3. 说明这些关系如何控制注意力、空间、节奏、情绪和叙事。
4. 在作品可能的目标下评价其有效性与代价。
5. 区分画面事实、本地测量、专家推断和背景假设。
6. 最后提炼可迁移规律与继续观察的问题，不把表面复刻步骤当作主要学习成果。

因此本模块固定覆盖十二维，同时要求输出跨维度因果链。没有总分，也不把启发式
注意力代理称为真实显著性。

## 公开资料与吸收内容

### Pixar in a Box：视觉语言与灯光

- [The Art of Lighting](https://www.khanacademy.org/computing/pixar/art-of-lighting)
- [Color Scripts](https://www.khanacademy.org/computing/pixar/art-of-lighting/introduction-to-virtual-lighting/v/colorscripts?t=406)
- [Visual Language: Line](https://www.khanacademy.org/humanities/hass-storytelling/storytelling-pixar-in-a-box/ah-piab-visual-language/v/storytelling-line)

吸收：

- 光、色彩和构图首先服务故事、情绪与可信度。
- Color Script 的价值在于把叙事压缩成连续的明度、色彩与情绪关系。
- 线、形、空间、调子、运动和色彩是视觉语言，不是独立评分项目。

不吸收：

- 不把电影制作流程直接套到每张静态作品。
- 不声称从单张成图恢复作者真实工作过程。

### Smarthistory：Close Looking 与 Formal Analysis

- [Introduction to art historical analysis](https://smarthistory.org/introduction-to-art-historical-analysis/)
- [Close looking and approaches](https://smarthistory.org/reframing-art-history/introduction-close-looking-approaches/)
- [How to do visual (formal) analysis](https://smarthistory.org/visual-analysis/)

吸收：

- 先近距离描述，再分析形式关系和观看效果。
- 观察尺度、构图、视点、空间、形、线、色、光、调子、质感、平衡和图像意义。
- 正式分析具有解释性，必须展示证据和推理过程，不能伪装成唯一客观答案。

### James Gurney：色域与空气透视

- [Digital gamut mapping tool for Windows](https://gurneyjourney.blogspot.com/2013/02/digital-gamut-mapping-tool-for-windows.html)
- [Reverse Atmospheric Perspective](https://gurneyjourney.blogspot.com/2007/09/reverse-atmospheric-perspective.html)

吸收：

- 色彩研究不仅看主色，还要看色域的宽窄、中心、互补关系和中性色组织。
- “暖进冷退”不是无条件规则；湿气、尘埃、观察方向和日照条件可以反转常见
  空气透视现象。

产品约束：

- AI 不得用一个冷暖口诀替代对实际画面条件的观察。
- 本地工具只测量 Oklab 色板、彩度、中性色和空间分布；大气解释属于美术判断。

### Feng Zhu / FZD：设计可信度与视觉资料

- [FZD School of Design](https://fzdschool.com/)
- [Design Cinema Episode 96](https://fzdschool.com/blog_posts/design-cinema-episode-96)

吸收：

- 设计语言来自历史、文化、自然和真实功能，不只来自表面造型。
- 环境设计应同时检查熟悉性、独特性、功能逻辑和世界观一致性。
- 具体场景内容需要分析其尺度、用途、文化来源和叙事作用。

产品约束：

- 未知作者、文化或项目背景只能标记为假设。
- AI 不得因视觉相似就断言确定出处。

### Gnomon Workshop：环境叙事与电影化构图

- [Environment Design / Games Learning Path](https://ea.thegnomonworkshop.com/learning-path-environment-design-games)
- [Creating Cinematic Compositions for Production](https://thegnomonworkshop.com/workshops/creating-cinematic-compositions-for-production)
- [Creating a Sci-Fi Alleyway](https://sbc.thegnomonworkshop.com/tutorials/creating-a-sci-fi-alleyway)

吸收：

- 环境作品研究需要同时覆盖构图、尺度、形状语言、布景、材质、光、叙事细节和
  最终呈现。
- 构图评价必须联系调子平衡、光对观看者的影响和叙事目的。
- 可信场景的“具体内容”不是附录，而是视觉叙事的重要证据。

## SceneLens 研究契约

### 信息来源

- `visible_image_evidence`：画面中可直接指出的位置与关系。
- `local_measurement`：SceneLens 实际提供的明度、Oklab、彩度、边缘等数值。
- `expert_inference`：基于美术经验的解释，必须写明不确定性。
- `contextual_hypothesis`：作者、世界观、文化和制作方法等背景假设。

### 十二维

构图组织、视觉层级、明度结构、色彩设计、光影组织、空间层次、形状语言、
边缘与细节控制、材质与表面、环境叙事、风格与技法、情绪作用。

### 评价方式

不问“是不是好看”或“几分”，而问：

- 作品可能要解决什么视觉或叙事问题？
- 当前选择是否有效？
- 哪些画面证据支持该判断？
- 它牺牲了什么或只在什么条件下成立？
- 哪条规律可以迁移，哪部分只是该作品的表面特征？

## 版权与实现边界

本轮只吸收公开资料中的分析方法和课程主题，不复制付费课程、长篇原文、提示词
或实现代码。AI 系统指令、Schema、本地算法和界面均为 SceneLens 独立实现。
