# GATalk 导航与视觉 AI 供应商审查

日期：2026-08-12

## 结论

本轮采用“应用外壳统一导航，专业工作台保留业务工具”的两级结构。
每个专业工作台只保留一个位于左上方的“工作台首页”按钮；全局检索、运行状态和
全局设置与它处于同一行，模块专有命令位于下一行。工作台切换时继承用户当前的
普通、最大化或全屏状态，不自行缩放窗口。

视觉 AI 接入采用经筛选的可替换供应商目录，不把“供应商数量”当成功能质量。
只有已确认能够接收图像的服务才声明视觉审阅能力；模型 ID 始终可编辑。所有真实
联网调用仍需用户查看发送清单并确认，API Key 只进入 Windows 系统凭据。

## 导航依据

- Microsoft Windows 应用指南建议把返回按钮放在应用左上方，并由应用层统一处理，
  避免各页面重复实现。
- Microsoft NavigationView 指南强调跨页面保持一致的顶层导航，并把全局搜索、
  设置和业务内容分为清楚的层级。
- GATalk 不引入新的 UI 框架；以上规则由现有 Qt 应用外壳实现，避免为了视觉更新
  重写稳定业务窗口。

参考：

- https://learn.microsoft.com/en-us/windows/apps/develop/ui/navigation/navigation-history-and-backwards-navigation
- https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/navigationview

## 供应商范围

| 供应商 | 当前适配 | 默认模型 | 结构化策略 | 当前验证 |
|---|---|---|---|---|
| 离线 Mock | 流程与契约 | mock-vision-v1 | 本地固定结构 | 自动化通过，不做语义推理 |
| 阿里云百炼 | 视觉审阅、结构化输出 | qwen3-vl-plus | JSON object | 离线契约通过，真实 Key 待人工验证 |
| SiliconFlow | 视觉审阅、结构化输出 | Qwen3-VL-32B-Instruct | JSON object | 离线契约通过，真实 Key 待人工验证 |
| 智谱 GLM | 视觉审阅、结构化输出 | glm-5v-turbo | 提示约束并本地校验 | 离线契约通过，真实 Key 待人工验证 |
| 火山方舟 | 视觉审阅、结构化输出 | doubao-seed-2-0-lite-260215 | 提示约束并本地校验 | 离线契约通过，真实 Key 待人工验证 |
| 腾讯混元 | 视觉审阅、结构化输出 | hunyuan-vision | 提示约束并本地校验 | 离线契约通过；账号入口可能调整 |
| OpenAI | 视觉审阅、结构化输出 | gpt-5.6-terra | Responses JSON Schema | 离线契约通过，真实 Key 待人工验证 |
| Anthropic Claude | 视觉审阅、结构化输出 | claude-sonnet-5 | 原生 JSON Schema；400 时有界回退 | 离线契约通过，真实 Key 待人工验证 |
| Google Gemini | 视觉审阅、结构化输出 | gemini-3.6-flash | Gemini Schema 与现有修复链 | 已有真实项目验证，新版本待复查 |
| xAI Grok | 视觉审阅、结构化输出 | grok-4.5 | Responses JSON Schema | 离线契约通过，真实 Key 待人工验证 |

图片生成仍使用现有万相、Gemini / Nano Banana、OpenAI GPT Image 和 Grok
Imagine 适配器。Claude 等未声明图片生成的供应商不会出现在图片生成位置。

DeepSeek 当前未加入视觉审阅目录：本轮没有确认其通用 API 能够按 GATalk 所需方式
接收场景图片。把纯文本服务列成视觉审阅器会造成错误预期。以后确认稳定视觉接口
后，可通过 Provider Manifest 加入，不需修改领域模型。

## 主要技术依据

- OpenAI 模型与 Responses 文档：https://developers.openai.com/api/docs/models
- Anthropic 结构化输出：https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Google Gemini 3.6 Flash：https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash
- 阿里云 Qwen3-VL Plus：https://help.aliyun.com/zh/model-studio/qwen3-vl-plus
- 智谱 GLM-5V Turbo：https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5v-turbo
- 腾讯混元 OpenAI 兼容接口：https://cloud.tencent.com/document/product/1729/111007
- 火山方舟视觉模型说明：https://www.volcengine.com/docs/82379/1795150

## 风险与边界

- 模型名称、额度、地域和服务入口会变化；默认模型来自当前公开资料，用户可在界面
  修改模型 ID。真实可用性以对应账户控制台为准。
- 不自动跨供应商回退，避免在用户不知情时把图片发送给另一家公司。
- 真实网络测试默认关闭，不计入自动化测试；缺少 API Key 时全部本地功能可用。
- 提示约束型供应商的返回仍由 GATalk 严格 Schema 校验，不能把格式正确等同于
  审阅结论准确。
