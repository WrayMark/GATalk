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
| 阿里云百炼 | OpenAI-compatible Chat | Manifest | Base64 图像、JSON 对象模式、解析、Mock 契约完成 |
| SiliconFlow | OpenAI-compatible Chat | Manifest | Base64 图像、JSON 对象模式、解析、Mock 契约完成 |
| OpenAI | Responses | Manifest | 图像输入、严格 JSON Schema 请求、解析、Mock 契约完成 |
| Google Gemini | `generateContent` | Manifest | inline image、`responseFormat`、兼容 Schema、解析、Mock 契约完成 |
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

Provider Manifest 还可按能力声明 `fallback_models`。当前仅 Google Gemini
视觉审阅配置稳定 `gemini-2.5-flash` 作为容量回退：主模型有限重试后仍返回
503 才会使用；只尝试一个备用模型，不跨供应商。发送清单和 AI Run 都记录
该行为。

## 3. 图像编辑能力位置

M2 已注册以下 `ImageEditProvider` 位置：

- 阿里云万相：初始 Manifest 使用 `wan2.7-image-pro`
- Gemini / Nano Banana：`gemini-3.1-flash-image`
- OpenAI GPT Image：`gpt-image-2`
- Grok Imagine：`grok-imagine-image-quality`

M3 已完成真实请求构造：万相和 Gemini 使用原生 JSON，OpenAI 使用
multipart，Grok Imagine 使用 JSON。供应商返回 HTTPS 结果 URL 时，由同一
用户主动触发任务在后台安全下载；只接受图片媒体类型并限制最大 50 MiB。
同时保留完全离线的 `MockProvider`。

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
- 视觉主模型重试后仍返回 503 时，可按发送清单使用一次同供应商备用模型；
  参数、认证、权限和额度错误不会触发回退。
- HTTP 错误会显示脱敏后的状态和供应商原因；不保存 Key、请求正文或图片字节。

## 5. 未验证项

- 未使用任何真实 API Key，未验证供应商账户、余额、地区路由、当前模型开通
  状态、计费或实际响应 Schema。
- 百炼和 SiliconFlow 当前使用 JSON 对象模式，不声称服务端保证完整
  SceneLens Schema；返回结果仍由本地完整 Schema 验证。
- Gemini 只接收兼容子集，返回结果仍由本地完整 Schema 验证。
- Windows Credential Manager 已完成接口和非破坏性测试，但尚未使用真实用户
  Key 做写入/读取/删除人工烟测。
- 真实联网测试默认关闭，以上项目列入 M2 人工联网验收，不阻塞离线功能。
