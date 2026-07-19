# M2 Provider 架构与完成度

状态：M2 供应商基础与离线契约测试完成  
日期：2026-07-19

## 1. 统一能力接口

- `VisionReviewProvider`
- `StructuredOutputProvider`
- `ImageEditProvider`
- `ProviderCapability`
- `ProviderManifest`
- `ProviderRegistry`

领域审阅器只依赖能力接口，不依赖供应商名或模型 ID。默认模型、端点、能力和
中国大陆优先级从 `providers/config/providers.json` 加载；用户选择的模型 ID
可以覆盖 Manifest 默认值。

## 2. 视觉审阅适配器

| Provider | 请求风格 | 默认模型来源 | 当前完成度 |
|---|---|---|---|
| 阿里云百炼 | OpenAI-compatible Chat | Manifest | 请求构造、Base64 图像、解析、Mock 契约完成 |
| SiliconFlow | OpenAI-compatible Chat | Manifest | 请求构造、Base64 图像、解析、Mock 契约完成 |
| OpenAI | Responses | Manifest | 图像输入、严格 JSON Schema 请求、解析、Mock 契约完成 |
| Google Gemini | `generateContent` | Manifest | inline image、JSON Schema 请求、解析、Mock 契约完成 |
| xAI Grok | Responses | Manifest | 图像输入、严格 JSON Schema 请求、解析、Mock 契约完成 |

公开协议核查依据：

- [阿里云百炼 OpenAI 兼容 Chat](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)
- [SiliconFlow Vision](https://docs.siliconflow.cn/en/userguide/capabilities/vision)
- [OpenAI 图像输入 Quickstart](https://platform.openai.com/docs/quickstart/make-your-first-api-request)
- [Gemini 图像理解](https://ai.google.dev/gemini-api/docs/generate-content/image-understanding)
- [Gemini Structured Outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [xAI 图像理解](https://docs.x.ai/developers/model-capabilities/images/understanding)
- [xAI Structured Outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs)

模型和协议会变化，因此这些 URL 只解释初始 Manifest 的来源。真实发布前必须
重新核对控制台可用模型、区域端点、价格、配额、数据保留和条款。

## 3. 图像编辑能力位置

M2 已注册以下 `ImageEditProvider` 位置：

- 阿里云万相：初始 Manifest 使用 `wan2.7-image-pro`
- Gemini / Nano Banana：`gemini-3.1-flash-image`
- OpenAI GPT Image：`gpt-image-1`
- Grok Imagine：`grok-imagine-image-quality`

同时提供完全离线的 `MockProvider`。真实图像编辑传输、异步结果获取和生成物
落盘放在 M3；M2 的非 Mock 位置会明确返回“尚未启用”，不会假装成功。

参考：

- [阿里云图像生成与编辑模型](https://help.aliyun.com/en/model-studio/image-model/)
- [Gemini Nano Banana](https://ai.google.dev/gemini-api/docs/image-generation)
- [xAI Image Editing](https://docs.x.ai/developers/model-capabilities/images/editing)

## 4. 隐私、凭据与执行

- 创建注册表和启动应用不会联网。
- 请求必须同时具有“用户主动触发”和“已确认发送清单”状态。
- 发送清单只显示字段名、图片角色、媒体类型、字节数和 SHA-256，不回显图片
  二进制或凭据。
- API Key 通过 Windows Credential Manager 的 Generic Credential 保存。
- 项目、SQLite、JSON 和日志不保存 API Key；`AIRun` 输入清单拒绝常见凭据字段。
- 后台执行支持协作取消、请求超时、有限指数退避和错误脱敏。底层同步 HTTP
  已发出后不能保证立即中断 socket，但取消后的结果不会被接受。

## 5. 未验证项

- 未使用任何真实 API Key，未验证供应商账户、余额、地区路由、当前模型开通
  状态、计费或实际响应 Schema。
- 百炼和 SiliconFlow 的严格 JSON Schema 服务端能力可能随具体模型不同；
  SceneLens 仍必须对返回结果做本地 Schema 校验，不把提示词约束当作保证。
- Windows Credential Manager 已完成接口和非破坏性测试，但尚未使用真实用户
  Key 做写入/读取/删除人工烟测。
- 真实联网测试默认关闭，以上项目列入 M2 人工联网验收，不阻塞离线功能。

