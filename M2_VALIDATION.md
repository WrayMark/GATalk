# SceneLens M2 验证记录

状态：内部候选通过，进入 M3 连续开发  
日期：2026-07-19  
候选标签：`v0.3.0a0-m2`

## 已确认事实

- M1B.2 回归功能继续通过。
- 完整自动化测试共 122 项，全部通过；默认测试没有发起网络请求，也未消耗
  API 额度。
- 源码 `--smoke-test` 退出码为 0。
- PyInstaller `onedir` 构建成功。
- 打包内 `SceneLens.exe --smoke-test` 退出码为 0；烟测覆盖图像分析、项目
  schema v6、成对区域分析、严格审阅 Schema 和离线 Mock 专项审阅。
- 候选目录总大小为 266,410,388 bytes（约 254.1 MiB）。
- 候选程序：
  `dist/SceneLens/SceneLens.exe`

## 本轮覆盖

- `VisionReviewProvider`、`StructuredOutputProvider`、
  `ImageEditProvider`、Capability、Manifest 和注册表。
- 百炼 Qwen VL、SiliconFlow Qwen VL、OpenAI、Gemini、xAI Grok
  视觉请求适配位置和离线契约测试。
- Windows Credential Manager、主动发送门禁、发送清单、去元数据/降分辨率
  副本、后台取消/超时/重试和错误脱敏。
- 主美专项审阅、灯光专项审阅、最多五个核心问题和严格 JSON Schema。
- 第二意见、来源/分歧保留、本地 AI 证据校验和冲突可信度降级。
- 分维度质量门禁、新 Version 变化状态、用户确认发现转任务。
- 曝光伪色、明暗溢出、可调剪影、缩略图、明度模糊和灯光明度代理图。
- 三套灯光目标方案、结构化画布标注、标注转任务。
- 离线 AI 审阅包 ZIP；没有 API Key 时不影响本地项目、测量、区域和任务。

## Provider 完成度

| Provider | 当前完成度 | 真实联网验证 |
|---|---|---|
| 离线 Mock | 完整可执行，严格 Schema 与 UI 流程可测 | 不需要 |
| 阿里云百炼 Qwen VL | Manifest、适配器、请求契约、错误边界完成 | 未验证真实 Key |
| SiliconFlow Qwen VL | Manifest、适配器、请求契约、错误边界完成 | 未验证真实 Key |
| OpenAI | Responses 风格视觉/严格输出契约完成 | 未验证真实 Key |
| Google Gemini | `generateContent` 图像和结构化输出契约完成 | 未验证真实 Key |
| xAI Grok | Responses 风格视觉/严格输出契约完成 | 未验证真实 Key |
| 万相 / Gemini Image / GPT Image / Grok Imagine | M3 图像编辑能力位置与 Mock | M2 不执行真实编辑 |

## 未验证项与边界

- 真实 API Key、账号区域、计费、网络可达性和供应商当前模型可用性尚未验证；
  它们列入人工联网烟测，不阻塞 M3 本地能力开发。
- 取消可在请求前、重试间和响应后生效；底层同步 HTTP 正在等待 socket 时只能在
  返回后丢弃结果，不能保证立即中断远端计费。
- 真实 125%/150% 高 DPI 显示器和完全无 Python 的干净 Windows 机器仍是
  Windows Alpha 前验收项，不误记为本轮已通过。
- 灯光明度代理图只减弱色彩和局部细节干扰，不能剥离材质与纹理，也不是真正
  “灰模”。

## M2 重大外部试用建议

1. 打开中世纪村庄项目，确认 M1B.2 区域和历史结果仍在。
2. 在显示模式中依次检查六种灯光观察模式，并调整剪影阈值。
3. 在“AI 审阅与任务”选择离线 Mock，检查发送清单后运行主美与灯光审阅。
4. 导出离线审阅包，确认 ZIP 中只有结构化 JSON 和发送副本。
5. 如有可用 Key，再分别人工验证百炼及一个海外可选 Provider。
6. 对真实 AI 结果检查本地证据支持/冲突、三套灯光方案和标注转任务。

按照用户要求，M2 候选完成后不暂停开发，继续进入 M3；外部试用反馈可并行
回收。
