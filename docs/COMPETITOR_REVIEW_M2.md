# M2 竞品审查：AI 主美 Pro 与游戏场景灯光分析

日期：2026-07-19  
范围：只审查公开页面、README 与公开源码；不复制提示词、实现代码或界面文案。

## 1. 核查来源与许可证

- AI 主美 Pro：
  [公开 Space](https://huggingface.co/spaces/Smalleast23/AI_Personal_ArtDirector_Pro)、
  [README](https://huggingface.co/spaces/Smalleast23/AI_Personal_ArtDirector_Pro/blob/main/README.md)、
  [app.py](https://huggingface.co/spaces/Smalleast23/AI_Personal_ArtDirector_Pro/blob/main/app.py)。
  仓库根目录公开文件为 README、版本说明、单体 `app.py` 和依赖文件；截至本次
  核查，Space 元数据、README 和根目录均未发现明确许可证。因此不复用代码、
  长提示词、结构化文案或受表达保护的界面内容。
- 游戏场景灯光分析：
  [公开 Space](https://huggingface.co/spaces/Smalleast23/AI_Personal_ArtDirector_Light)、
  [README](https://huggingface.co/spaces/Smalleast23/AI_Personal_ArtDirector_Light/blob/main/README.md)、
  [index.html](https://huggingface.co/spaces/Smalleast23/AI_Personal_ArtDirector_Light/blob/main/index.html)。
  Space 元数据明确标记 `license: mit`。SceneLens 本轮仅借鉴产品类别，没有
  复制其 HTML、CSS、JavaScript 或提示词，因此当前无需增加源码归属条目；若
  未来实际复用，必须先记录文件、提交、MIT 版权声明和修改范围。

## 2. 可吸收的产品思路

- 把“主美审阅”和“灯光审阅”做成有清晰目的的专项工作区，而不是一个泛化
  长报告入口。
- 画布和报告联动：灯光区域、推测组件、视觉动线、剪影和空间分割应能回到
  具体坐标证据。
- 保留无需 API 的观察工具：缩略图、模糊、剪影、曝光伪色和溢出警告。
- 分析结果可以继续进入修改预演，但中间必须经过用户确认和结构化任务。
- 供应商可切换是必要能力；国内服务应是中国大陆用户的一级路径。

## 3. 不吸收或需要纠正的做法

- **不使用泛化 0–10 总分。** 两个竞品均把多维观察压成评分，容易制造不透明
  的权威感。SceneLens 改用用户定义的质量门禁和分维度状态。
- **不从长 Markdown 中抽取改图指令。** Pro 将分析文本按关键词、优先级和
  “建议条数”转为大/中/小改动；条数不是改动强度。SceneLens 使用严格 JSON
  Schema、用户确认任务和明确的改动预算。
- **不把模型和端点写进业务模型。** 竞品在单体界面代码中直接绑定供应商、
  模型和请求格式。SceneLens 通过 Provider Manifest、能力接口和注册表隔离。
- **不把浏览器本地存储当凭据保险箱。** 灯光版把 API Key 写入
  `localStorage`；SceneLens 使用 Windows 系统凭据存储，项目和日志只保存
  provider ID，不保存密钥。
- **不宣称截图能恢复真实灰模。** 灯光版“灰模灯光”只是从最终截图构造的明度
  代理，无法剥离纹理、材质颜色、后处理和曝光。SceneLens 命名为“灯光明度
  代理图”，并显示限制说明。
- **不输出伪精确物理量。** 单张 LDR 截图不足以确定真实 Lux、EV、动态范围、
  灯光 Actor 数量或性能收益百分比；缺少 UE 工程设置时只能给检查清单。
- **不信任 AI 坐标本身。** 竞品虽然要求坐标与依据，但缺少本地测量回查。
  SceneLens 增加证据校验器，保留“支持、部分支持、冲突、无法验证”。

## 4. 对 M2/M3 的直接影响

- M2 先建立 Provider 契约、严格审阅 Schema、证据校验、专项灯光台、画布标注
  和质量门禁；默认完全离线，网络只能由用户主动触发。
- M3 把“分析到改图”改造成两条明确路径：可复现的本地安全调色，以及隔离为
  `AIConceptPreview` 的生成式预演。任何预演都不能伪装成真实 UE Version。
- 竞品未解决的核心问题——制作意图、参考图、当前版本、局部证据、任务和新版本
  复查之间的可追溯关系——继续作为 SceneLens 的差异化重点。

