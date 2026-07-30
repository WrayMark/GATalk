# 全自动资产板调研与技术选型

日期：2026-07-31

## 结论

当前版本采用“可替换视觉 Provider 输出结构化资产区域 + 本地可见遮罩 + 可替换图片 Provider 逐项生成 + 本地资产板合成”。

这条路线能直接复用现有 Windows CPU 架构、凭据、主动发送门禁、取消、重试和项目保存，不增加 CUDA、模型权重或大型运行依赖。资产分类、层级、复用和不可见结构仍是 AI 推断；原画可见区域与本地遮罩单独记录。

## 公开技术路线

- Qwen2.5-VL 官方资料展示了边界框、点定位和结构化 JSON，可作为远程视觉 Provider 的开放词汇定位能力参考。
- Florence-2 官方模型卡覆盖目标检测、区域描述、开放词汇检测和区域提议，适合未来 CPU/GPU 可选本地分析器评估。
- SAM 2 官方仓库支持图像自动掩码生成；Grounded SAM 2 将开放词汇检测与 SAM 2 组合，适合未来精细实例遮罩。
- 这些本地路线会引入 PyTorch、模型权重、显存/内存、Windows 打包和许可证复核成本。本版本不加入。

## Google 图片模型核对

- Nano Banana 2：`gemini-3.1-flash-image`，Google 推荐的通用均衡模型，支持多参考和最高 4K。
- Nano Banana Pro：`gemini-3-pro-image`，面向复杂指令和专业质量，最高 4K。
- Nano Banana 2 Lite：`gemini-3.1-flash-lite-image`，速度与成本优先，只提供 1K。
- 旧 Nano Banana 是 `gemini-2.5-flash-image`，不作为新默认。
- 同一个 Gemini API Key 可用于同一 Google 项目获准访问的模型；Key 本身不承诺模型权限、计费或额度。

## 交互与可靠性

- 使用 Qt Undo Framework 管理可撤销资产编辑。
- 资产树沿用 Qt 扩展选择；画布增加 Shift 拖动框选。
- 批量远程生成串行执行并保留部分成功。认证、权限、模型、额度、网络或服务端错误触发熔断；失败详情写入记录并显示给用户。
- 全自动运行与人工清单使用独立数据分支，避免一次自动结果覆盖人工校正。

## 来源

- Google Gemini API：<https://ai.google.dev/gemini-api/docs/image-generation>
- Google 模型目录：<https://ai.google.dev/gemini-api/docs/models>
- Google 发布记录：<https://ai.google.dev/gemini-api/docs/changelog>
- Qwen2.5-VL：<https://qwenlm.github.io/blog/qwen2.5-vl/>
- Florence-2：<https://huggingface.co/microsoft/Florence-2-large-ft>
- SAM 2：<https://github.com/facebookresearch/sam2>
- Grounded SAM 2：<https://github.com/IDEA-Research/Grounded-SAM-2>
- Qt Undo Framework：<https://doc.qt.io/qt-6/qundo.html>
- QGraphicsView：<https://doc.qt.io/qt-6/qgraphicsview.html>
