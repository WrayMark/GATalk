# GATalk 开源发布审计

审计日期：2026-08-14

范围：当前 Git 工作树、全部可达提交与标签、受跟踪二进制、运行依赖、现有 Windows
`onedir` 和公开文档。结果是工程审计，不代替律师意见或第三方平台合规审查。

## 结论

未发现必须重写 Git 历史的真实 API Key、Token、账号、私人路径、用户项目或测试原图。
未发现进入仓库的第三方模型、字体或无权再分发图片。历史 Word 与 PNG 元数据只包含
GATalk/SceneLens 产品名、生成时间和 DPI，不包含本机用户名或私人路径。

审计发现并已修正两个公开发布风险：

1. 旧构建使用 `PySide6` 元包，导致未使用的 Addons、QML、Quick、PDF 和虚拟键盘
   二进制进入 `onedir`。直接依赖改为 `PySide6-Essentials`，构建明确排除未使用模块。
2. 旧许可证记录仍把 Qt 合规列为待办，且没有随包第三方文本。现已加入完整许可目录、
   自动通知生成、Qt LGPL 分发说明和精确对应源码归档计划。

## 凭据与隐私

- 当前树和所有 Git blob 扫描 Google、OpenAI、GitHub、AWS、私钥等常见格式。
- `sk-never-log-this` 与 `sk-abcdefghijk` 是脱敏测试夹具，不是有效凭据。
- 扫描 Windows/macOS/Linux 用户目录形式；未发现具体本机绝对路径。
- 检查 `.docx` 的 core/app 属性和全部受跟踪 PNG/JPEG/WebP 元数据；无私人标识。
- 现有凭据代码使用 Windows Credential Manager，并保留 SceneLens 旧命名读取兼容；
  这不是硬编码凭据。

自动复核命令：

```powershell
.\.venv\Scripts\python.exe .\scripts\audit_public_release.py
```

模式扫描无法证明所有未知格式的秘密都不存在；每个 Release 前仍需人工检查 diff、
GitHub Actions 日志和上传附件。

## 用户数据与构建文件

- Git 跟踪文件中没有 `project.db`、用户 `project.json`、日志、缓存、虚拟环境、
  `dist/`、`build/` 或本地配置。
- 仓库本机存在的 `.venv`、`.artifacts`、`.qa`、旧构建和临时 Word 文件均被忽略，
  不进入提交或 Release 源码归档。
- `.gitignore` 已增加凭据文件、环境文件、项目目录、IDE、缓存和发布压缩包规则。

## 图片、字体、模型与第三方素材

- 受跟踪图片均由 GATalk 合成夹具和界面截图脚本生成；不含用户提供的真实项目图。
- 代码不捆绑字体文件，使用系统/Qt 字体选择。
- Grounding DINO、SAM 2、Florence-2、LaMa、Zero123++、TripoSR、Argos/OpenCC 与
  翻译模型只在调研记录中引用；代码、权重和数据集未进入仓库或发布包。
- 竞品文档只保存链接和独立审查结论；未复制许可证不明的 Pro 源码或长提示词，
  也未复用灯光版代码。

## 依赖与许可证

- GATalk 自有源码：MIT。
- Qt for Python/PySide6、Shiboken6、Qt Base、Qt SVG：LGPL-3.0-only 路径；动态
  `onedir` 分发，不修改 Qt DLL，允许替换。
- Pillow、NumPy、OpenCV、Colour Science、typing_extensions、Python 和
  PyInstaller 的完整上游文本进入 `THIRD_PARTY_NOTICES.txt`。
- Release 将上传以下精确源码：
  - `pyside-setup-everywhere-src-6.11.1.tar.xz`
  - `qtbase-everywhere-src-6.11.1.tar.xz`
  - `qtsvg-everywhere-src-6.11.1.tar.xz`

哈希记录见 `QT_SOURCE_OFFER.md`。依赖升级后这些结论必须重新审查。

## 仍需人工确认

- Windows 程序尚未代码签名；SmartScreen 信任不等于恶意软件判定。
- 当前开发机已验证源码环境与打包环境，但不能替代完全无 Python 的独立 Windows
  设备验收。
- 繁中、英语、日语和法语界面仍需母语审校。
- 真实 AI 供应商的账号、地区、配额、内容政策和数据保留由用户与供应商确认。
- 若原代码由雇主委托或使用工作时间/设备完成，公开前需由权利人确认代码版权归属。
- MIT 与 Qt LGPL 方案适合当前工程边界，但正式收费发行前仍建议独立法律审查。

## 发布候选验证

- 离线自动化测试：291 项通过。
- Windows `onedir`：285 个文件，解压后约 240.2 MiB。
- 打包烟测：100%、125% 与 150% 缩放均以退出码 0 完成。
- Release zip 已在独立目录解压，并再次执行 `GATalk.exe --smoke-test`，退出码 0。
- 发布包扫描未发现本机用户名、工作区路径、邮箱、聊天账号或已知凭据模式。Qt
  二进制中出现的短字符串 `AKIA` 是随机机器码片段，不满足 AWS Access Key 的完整格式。
- Word 手册已渲染为 9 页 PNG 并逐页检查，无裁切、重叠、私人路径或 API Key。
