# M5 作品研究网络可靠性修复验证

版本：0.6.0a1

日期：2026-07-30

候选标签：`v0.6.0a1-m5-network`

## 问题

真实 Gemini 作品研究请求出现：

`Remote end closed connection without response`

该异常不是 HTTP 认证或参数响应。远端服务器、代理、VPN 或其他中间网络设备
在返回 HTTP 响应前关闭了连接。旧版没有捕获 `RemoteDisconnected`，因此绕过
重试并直接显示英文底层异常。

## 修复

- 视觉审阅和图像编辑共用传输层统一处理：
  - 远端提前关闭
  - 连接重置或中止
  - 响应读取不完整
  - TLS、DNS 和超时错误
- 临时网络错误转换为可重试的 `ProviderError`。
- 后台最多尝试 3 次，间隔 1 秒、2 秒。
- 重试耗尽后显示：
  - 中文原因
  - `connection_closed` 或对应错误代码
  - 请求字节数
  - 实际尝试次数
- 不记录 API Key、图片内容、Prompt 或响应正文。
- 发送确认窗口提示重复提交可能产生额外费用。

## 自动验证

- 针对性供应商与作品研究回归：34 项通过。
- 完整自动化测试：181 项通过。
- 源码 `--smoke-test`：退出码 0。
- Windows onedir：构建成功。
- 打包版 `--smoke-test`：退出码 0。
- 最终 onedir 文件数（含手册与验证记录）：228。
- 最终 onedir 大小：266,644,668 字节，约 254.3 MiB。

候选程序：

`dist-m5-network-a1/SceneLens/SceneLens.exe`

## 手册验证

- `SceneLens_使用手册.docx` 已更新至 0.6.0a1。
- Word 包结构检查通过，共 124 个段落、1 个 section、17 个内部文件。
- 已确认手册包含 `connection_closed` 和三次自动重试说明。
- 当前机器没有 LibreOffice，无法执行逐页 PNG 渲染检查。

## 仍需真实联网验证

自动测试不会消耗 API 额度，也不能证明用户所在地到 Google 的网络稳定。

请使用同一图片和模型再次执行作品研究：

1. 关闭旧版 SceneLens。
2. 启动本候选目录中的 `SceneLens.exe`。
3. 打开原作品研究。
4. 保持最长边 2048 px。
5. 再次主动确认发送。
6. 若仍失败，记录新的中文错误代码、请求字节数和 `retry_attempts`。

如果三次都出现 `connection_closed`，更可能是 Google 访问链路、代理或 VPN
稳定性问题，而不是 API Key 或 JSON Schema 问题。
