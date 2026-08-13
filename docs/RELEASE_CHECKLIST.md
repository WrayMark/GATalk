# Public release checklist

## Repository

- 工作区无无关改动，真实 Git 历史和标签保持不变。
- `python scripts/audit_public_release.py` 通过。
- README、英文 README、隐私、安全、贡献、路线图和 Issue 模板已更新。
- 没有用户项目、缓存、日志、构建目录、虚拟环境、凭据或私人配置被跟踪。

## License

- 运行依赖与实际二进制清单一致。
- 运行 `python scripts/collect_third_party_notices.py`。
- 发行包包含 `LICENSE`、`THIRD_PARTY_NOTICES.txt`、`licenses/` 和
  `QT_SOURCE_OFFER.md`。
- 同一 Release 上传 PySide6、Qt Base 和 Qt SVG 精确对应源码归档并核对 SHA-256。

## Quality

- 完整离线测试通过。
- 重新生成中英文 Markdown 手册与 Word 手册。
- Word 手册渲染为逐页 PNG，并检查每一页无裁切、重叠或私密数据。
- Windows `onedir` 构建、1.0/1.25/1.5 缩放烟测通过。
- 发布压缩包在独立目录解压，运行 `GATalk.exe --smoke-test`。
- 记录候选 zip 的 SHA-256、解压体积、文件数和对应源码哈希。

## GitHub

- 仓库为公开，About、Topics、默认分支、Issues 和私密漏洞报告正确。
- 标签为测试版，Release 标为 pre-release，不使用“正式版”措辞。
- 上传 Windows zip、SHA-256、SBOM/清单和 Qt 对应源码。
- 从 GitHub 下载 Release zip 后再次核对哈希与启动结果。
