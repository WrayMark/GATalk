# GATalk Quick User Guide

Applies to version `0.18.0` (unified navigation and visual AI providers)  
Updated: 2026-08-12

This English guide covers the common workflow and the changes in this release. The Simplified
Chinese guide remains the complete reference while English UI copy is in preview review.

## 1. Start and navigation

- Release build: run `GATalk/GATalk.exe` from the current candidate folder.
- Development build: run `start_dev.cmd`.
- Imported images remain read-only. GATalk never uploads an image automatically.
- Every professional workbench has exactly one **Workbench Home** button in the upper-left.
- Global Search, Activity, and Global Settings remain in the same navigation row. Module-specific
  import and analysis commands appear in the row below.
- Moving between Home and a workbench preserves the current normal, maximized, or full-screen state.
- Press `Ctrl+Shift+H` to return Home, `Ctrl+K` for Global Search, and `Ctrl+,` for Settings.

## 2. Main workbenches

- **Scene Art Control** compares a reference image with UE screenshots, stores versions, runs
  evidence-based reviews, and tracks revisions.
- **Artwork Study** examines one concept image or finished artwork for learning.
- **Asset Breakdown** converts scene art into editable asset plans, prompts, and concept boards.
- **Comparative Study** studies two to six artworks under the same research question.
- **References & Knowledge Base** stores reusable images, articles, notes, excerpts, and links.
- **Production Tasks & Acceptance** collects user-confirmed tasks and version acceptance criteria.

## 3. Visual AI reviews

1. Open the review or study panel and select a provider.
2. Keep the default model or enter a model ID available to your account.
3. Save the API key to Windows Credential Manager.
4. Select **Review send manifest**, inspect the images and fields, then explicitly confirm.
5. Review visual evidence, measurement evidence, uncertainty, and conflicts before creating tasks.

Supported visual review providers are Alibaba Cloud Model Studio, SiliconFlow, Zhipu GLM,
Volcengine Ark, Tencent Hunyuan, OpenAI, Anthropic Claude, Google Gemini, and xAI Grok.
Availability, region, model permission, quota, and cost depend on the provider account.

Image generation remains available through Wanxiang, Gemini / Nano Banana, OpenAI GPT Image,
and Grok Imagine. A provider is only shown where it declares the required capability.

The **Offline Mock** checks request, UI, storage, and error-handling flows. It is not a local vision
model, does not make semantic judgments, needs no GPU, and consumes no API quota.

## 4. Language and storage

1. Open **Settings > Global Settings** or press `Ctrl+,`.
2. Choose Follow System, Simplified Chinese, Traditional Chinese, English, Japanese, or French.
3. Apply the setting. It remains active across restarts.

Changing the UI language does not translate or rewrite project names, notes, imported documents,
or previous AI results. API keys are not written to project files, SQLite, JSON, logs, or Git.

## 5. Common error meanings

- `http_400`: request, model, or structured-output incompatibility. Restore the provider default
  model and check the provider documentation.
- `http_401`: invalid, expired, or wrong-provider API key.
- `http_403`: missing model access, service activation, workspace, or region permission.
- `http_404`: retired model ID or wrong endpoint.
- `http_413`: request image is too large; reduce the send resolution.
- `http_429`: quota or rate limit reached.
- `http_503` or `connection_closed`: temporary provider or network failure. GATalk performs bounded
  retries; repeated failures require a later retry or a network check.

GATalk never silently sends the same image to a different provider. Error dialogs redact credentials;
do not share screenshots containing an API key.

## 6. Current validation limits

- Automated tests are fully offline and do not consume provider quota.
- New provider adapters have offline request-contract coverage. Each real account still requires one
  manual visual review to confirm region, model entitlement, quota, and live response behavior.
- Traditional Chinese, English, Japanese, and French UI packs remain previews pending native-speaker
  review and high-DPI truncation testing.
