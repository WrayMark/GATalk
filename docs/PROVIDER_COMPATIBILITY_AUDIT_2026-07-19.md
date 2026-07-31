# AI Provider 兼容性审计

日期：2026-07-19  
范围：视觉审阅与图像编辑 Provider  
结论：本次 Gemini 失败主要属于 GATalk 适配缺陷，不归因于用户操作。

## 已修复

- 2026-07-30 复查 Google 当前稳定模型和弃用表后，默认视觉模型更新为
  `gemini-3.6-flash`，备用链更新为 `gemini-3.5-flash`、
  `gemini-3.5-flash-lite`；移除已不再向新用户开放的
  `gemini-2.5-flash`。404/503 可以越过当前不可用模型继续尝试下一项。
- 2026-07-28 复查真实 Gemini 400 响应后，将
  `generationConfig.responseFormat.text.mimeType` 从文档示例中的
  `application/json` 改为 v1beta 服务端实际接受的
  `APPLICATION_JSON` 枚举值，并增加精确请求契约断言。
- 公共 HTTP 层读取供应商错误状态和脱敏错误原因，不再把
  400/401/403/404/413/429/5xx 全部显示成同一句话。
- Gemini 视觉审阅改用当前 `responseFormat`，并在发送前把完整本地 JSON
  Schema 转成 Gemini 支持的子集。`const` 转为单值 `enum`；`$schema`、
  `minLength` 和 `pattern` 等不支持字段不发送。本地仍用完整 Schema 验证结果。
- Gemini 3 系列不再强制 `temperature=0.2`，使用供应商默认值。
- 百炼与 SiliconFlow 使用 `json_object` 模式，并明确要求只返回 JSON。
- OpenAI 与 xAI 视觉审阅继续使用 Responses API、图片 Data URL、关闭服务端
  存储和严格结构化输出；离线契约与当前公开协议一致。
- Grok Imagine 图像编辑从错误的 multipart 请求改为官方要求的 JSON 请求。
- 万相、OpenAI 和 Grok Imagine 支持供应商返回 HTTPS 图片 URL；程序在用户
  已主动发起同一任务的边界内下载结果，并限制协议、媒体类型和最大 50 MiB。
- OpenAI 图像编辑默认模型更新为 `gpt-image-2`；模型 ID 仍可由用户覆盖。

## 错误解释

- `http_400`：请求参数、Schema 或模型参数被拒绝。
- `http_401`：Key 未通过认证。
- `http_403`：Key 权限、服务开通、地域或模型访问不满足。
- `http_404`：模型 ID 或接口不存在。
- `http_413`：发送图片或请求过大。
- `http_429`：频率或额度限制。
- `http_5xx`：供应商服务暂时异常。

界面只显示经过长度限制和凭据脱敏的供应商原因。API Key、Authorization
Header、请求图片和完整请求正文不写入错误信息。

## 完成度

| 供应商 | 视觉审阅 | 图像编辑 | 自动验证 |
|---|---|---|---|
| 百炼 Qwen VL | JSON 模式契约完成 | 万相请求与 URL 结果完成 | 离线 |
| SiliconFlow Qwen VL | JSON 模式契约完成 | 不在当前范围 | 离线 |
| OpenAI | Responses 严格 Schema 完成 | multipart 编辑完成 | 离线 |
| Google Gemini | 当前结构化格式与 Schema 子集完成 | inline image 完成 | 离线 |
| xAI | Responses 严格 Schema 完成 | JSON 编辑与 URL 结果完成 | 离线 |

## 尚需人工联网验证

- Key 是否属于正确平台和地域。
- 账号是否已开通所选模型，以及是否有余额或额度。
- 自定义模型 ID 是否仍在供应商控制台可用。
- 国内网络到 Google、OpenAI 和 xAI 的实际可达性。
- 供应商真实响应字段、计费和内容政策。

这些项目需要真实 Key，默认自动测试不会联网或消费额度。

## 自动验证结果

- 2026-07-30 Gemini 模型路由修复后，新增默认模型、双备用链、404/503
  越级回退、全链失败和发送清单测试；完整 207 项通过，源码与新
  `onedir` 包内烟测退出码均为 0。真实联网烟测仍由用户主动执行。
- 2026-07-28 Gemini MIME 枚举修复后，149 项完整测试通过。
- 2026-07-28 修复候选输出到 `dist-gemini-fix/GATalk/`，包含简明 Word
  使用手册；目录总大小 266,520,924 bytes（约 254.2 MiB），包内
  `--smoke-test` 退出码为 0。
- Windows `onedir` 候选构建成功，大小 266,480,131 bytes（约 254.1 MiB）。
- 包内 `--smoke-test` 退出码为 0。
- 真实供应商联网烟测未执行，不读取或消费用户 Key。

## 公开协议依据

- [Gemini Structured Outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [Gemini 模型列表](https://ai.google.dev/gemini-api/docs/models)
- [Gemini 模型弃用](https://ai.google.dev/gemini-api/docs/deprecations)
- [Gemini 3.6 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash)
- [Gemini 3.5 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash)
- [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
- [Gemini 图像生成与编辑](https://ai.google.dev/gemini-api/docs/generate-content/image-generation)
- [百炼 OpenAI 兼容 Chat](https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions)
- [百炼 Structured Output](https://help.aliyun.com/en/model-studio/qwen-structured-output)
- [万相 2.7 图像编辑](https://help.aliyun.com/en/model-studio/wan-image-generation-and-editing-api-reference)
- [SiliconFlow Chat Completions](https://docs.siliconflow.cn/en/api-reference/chat-completions/chat-completions)
- [SiliconFlow Vision](https://docs.siliconflow.cn/en/userguide/capabilities/vision)
- [OpenAI GPT Image 2](https://developers.openai.com/api/docs/models/gpt-image-2)
- [xAI Structured Outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs)
- [xAI Image Understanding](https://docs.x.ai/developers/model-capabilities/images/understanding)
- [xAI Image Editing](https://docs.x.ai/developers/model-capabilities/images/editing)
