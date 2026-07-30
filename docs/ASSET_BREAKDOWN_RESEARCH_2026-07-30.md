# 资产拆分工作台调研与技术选型

日期：2026-07-30

## 1. 调研问题

本轮关注的不是“给图片做一次物体检测”，而是如何把游戏场景原画整理成具有
实际制作价值的资产规划：资产类别、父子层级、模块套件、重复与变体、制作
优先级、原画证据、不确定性、可见区域和后续概念生成必须同时成立。

## 2. 视觉理解与分割

- [Grounding DINO](https://github.com/IDEA-Research/GroundingDINO) 使用文本
  类别或指代表达做开放集检测，代码为 Apache-2.0。它适合把 VLM 的语义清单
  转成候选框，但不直接理解游戏资产的模块套件和制作层级。
- [Grounded SAM](https://arxiv.org/abs/2401.14159) 展示了开放词汇检测与
  Segment Anything 的组合方式，证明“先语义定位、再提示分割”是合理管线。
- [SAM 2](https://github.com/facebookresearch/sam2) 提供提示式图像/视频分割，
  代码和检查点为 Apache-2.0；官方安装要求 PyTorch 2.5.1，并强烈建议 Windows
  使用 WSL，GPU/CUDA 路径明显。它不适合直接进入当前 CPU `onedir`。
- [Florence-2](https://huggingface.co/docs/transformers/model_doc/florence2)
  可用任务提示完成描述、检测和分割，基础模型页面标注 MIT。它仍会引入
  PyTorch、Transformers 和模型权重，不纳入本次安装包。
- [Qwen3-VL](https://qwen.ai/blog?id=99f0335c4ad9ff6153e517418d48535ab6d8afef)
  公开能力包括多目标定位；它说明云端 VLM 可以同时输出语义与归一化区域。
  SceneLens 因此保持 Provider 可替换，不把领域数据绑定到某个模型 ID。

结论：当前正式路线由视觉 Provider 生成生产语义、层级和归一化矩形；本地
OpenCV GrabCut 只在该矩形内估计“直接可见像素遮罩”。遮罩标记为算法近似，
失败时退回矩形代理。用户修订始终高于 AI 结果。没有捆绑本地视觉大模型。

## 3. 遮挡补全、对象提取与视图重建

- [LaMa](https://github.com/advimman/lama) 是 Apache-2.0 图像修补研究实现，
  适合遮挡补全，但旧 PyTorch/CUDA 环境和外部权重不适合当前安装边界。
- [Break-A-Scene](https://arxiv.org/abs/2305.16311) 研究从单图学习多个
  概念；[AssetDropper](https://arxiv.org/abs/2506.07738) 研究从复杂图像
  提取资产。这些工作说明对象级生成可行，也同时说明“提取结果”仍是生成模型
  重建，不等于原图背面真相。
- [Zero123++](https://github.com/SUDO-AI-3D/zero123plus) 可从单图生成一致多
  视图，但模型权重是 CC-BY-NC 4.0、约需 5.7 GB VRAM，不适合未来商业发布
  的默认能力。
- [TripoSR](https://github.com/VAST-AI-Research/TripoSR) 代码与权重为 MIT，
  单图 3D 仍建议约 6 GB VRAM。它可以作为未来独立 3D Provider 的研究候选，
  本版不生成生产三维模型。

结论：本版生成“独立概念图、保守遮挡补全图、评审展示图”，全部保存为
`AssetConceptArtifact`，记录来源矩形、输入哈希、供应商、模型和参数。不可见
结构在界面与导出中明确称为 AI 生成补全，不能回写为原画可见证据。

## 4. 游戏资产生产逻辑

- Epic 的
  [Designing and Building Worlds](https://dev.epicgames.com/documentation/en-us/unreal-engine/designing-and-building-worlds-in-unreal-engine-for-maya-users)
  和 GDC 的
  [Fallout 4 Modular Level Design](https://www.gdcvault.com/play/1023202/-Fallout-4-s-Modular)
  强调模块套件与迭代搭建，而不是把画面中的每个可见块都做成唯一模型。
- Autodesk 的
  [Creating and Implementing Modular 3D Environments](https://www.autodesk.com/autodesk-university/class/Copy-and-Paste-Your-Universe-Creating-and-Implementing-Modular-3D-Environments-2013)
  讨论用可复用构件快速搭建大型环境。
- Adobe Substance 3D Sampler 的
  [Image to Material](https://experienceleague.adobe.com/en/docs/substance-3d-sampler/using/filters/tools/image-to-material)
  可以从图像产生材质通道，但不能代替场景中的“模型、材质、贴花、纯背景”
  边界判断。
- 商业产品
  [GenioPlus Scene Asset Extraction](https://genioplus.com/en/blog/scene-generation-split-scene-into-game-assets)
  展示了“场景清单—选择单项—重新生成”的产品流程。SceneLens 只吸收这一类
  交互思想，没有复制代码、提示词或专有实现。

由此建立七种场景配置：通用环境、历史聚落、城市街道、科幻工业、自然景观、
室内、风格化环境。它们共享数据结构，但给 AI 不同的制作关注点：

- 建筑：墙段、开口、柱、转角、屋顶、收边、重复立面和变体。
- 道具：独立物件、组合、重复实例和复用组。
- 植被：物种、尺度层级、单株变体与群落。
- 地表：地形几何、可平铺材质、混合层、贴花和纯绘制背景。
- 工业：结构模块、管线系统、面板、机械道具和灯光/特效代理。

## 5. 最终选择

正式能力采用：

1. 现有 `VisionReviewProvider` 输出严格资产 Schema。
2. 现有 `ImageEditProvider` 只生成用户勾选的资产。
3. OpenCV GrabCut 在 AI/用户矩形内生成可见像素近似遮罩。
4. 用户可移动矩形、改名、改分类、改层级、拆分、合并、删除和补充。
5. 项目包原子保存原始字节、SHA-256、AI Run、遮罩、生成记录和导出记录。
6. 本地 Pillow 生成带来源标签的资产展示板和结构化清单。

未采用：

- 不捆绑 Grounding DINO、SAM 2、Florence-2、LaMa、Zero123++ 或 TripoSR。
- 不引入 PyTorch、Transformers、CUDA、模型权重或动态未知代码加载。
- 不声称矩形或 GrabCut 是精确实例分割。
- 不生成生产可用三维模型，不伪造不可见结构。

本轮没有复制上述仓库代码或长提示词，没有新增运行依赖。未来若采用任何候选，
必须重新检查模型权重许可证、商业使用边界、Windows 打包和显存成本。

