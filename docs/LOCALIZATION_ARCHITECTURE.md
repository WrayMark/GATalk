# GATalk 本地化架构与翻译质量

## 目标

GATalk 的界面语言由应用外壳统一管理。工作台可以继续拥有自己的界面和数据，
但不得把译文作为业务 ID、数据库枚举或分析器契约。

## 当前语言

- 基准：简体中文 `zh-CN`
- 预览：繁体中文 `zh-TW`、英语 `en`、日语 `ja`、法语 `fr`
- 自动：`system` 根据 Windows 显示语言选择最接近的已支持语言，无法识别时回退
  简体中文。

界面语言和地区格式是不同概念。本版只切换显示语言，不擅自更改用户的日期、数字、
小数点、文件路径或操作系统区域设置。

## 运行结构

- `core/locales.py`：稳定 locale、语言说明和 AI 输出语言约束。
- `ui/localization.py`：加载目录、切换现有窗口、处理动态控件和安全回退。
- `i18n/<locale>.json`：随程序打包的固定界面目录，保存覆盖与审校元数据。
- `storage/app_settings.py`：把选择写入本机 `%LOCALAPPDATA%/GATalk/settings.json`。
- Provider 执行层：只为新请求增加目标语言，不改变 Schema 和用户原文。

## 翻译质量流程

1. 从 UI 源码提取固定简中文案。
2. 产品术语表先确定稳定译名，例如 Art Direction、Asset Breakdown、Quality Gate、
   Oklab、Value 和 Chroma。
3. 构建期可用离线模型生成初稿；源码文案不发送给公共翻译服务。
4. 语言目录记录覆盖数、人工校核数和阶段。机器初稿只能标记为预览。
5. 正式发行前由对应语言母语者逐条审校，并检查按钮宽度、换行、快捷键和 125%／
   150% 高 DPI。
6. 删除、联网发送、费用、凭据、隐私和不可逆操作属于高风险文案，必须优先人工
   审校。

覆盖率不是准确率。某语言即使固定文案达到 100% 覆盖，只要尚未逐条复核，仍保持
“预览”状态。

## 数据与安全边界

- 切换语言不修改项目、图片、笔记、引用、任务或已有 AI 历史。
- 下拉框显示文本可以翻译，保存值必须使用稳定 ID 或原始数据。
- 缺少目录或词条时显示简体中文；不猜测，不保存空值。
- 本地化不触发网络。真实 AI 请求仍需用户主动确认，语言指令不会扩大原发送清单。

## 维护规则

- 新增用户可见固定文案后运行 `scripts/build_i18n_catalogs.py --glossary-only` 更新
  目录覆盖统计。
- 新增核心术语时先更新词表，再生成目录；不要逐窗口发明不同译名。
- 新增可编辑下拉框时把稳定值写入 `itemData`，不得把翻译后的显示文本写入项目。
- 发布前运行目录完整性、占位符、语言往返、打包资源和多语言窗口烟测。

## 研究依据

- [Qt QTranslator](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QTranslator.html)：
  应用级翻译器安装、语言切换和回退机制。
- [Microsoft - Prepare your app for localization](https://learn.microsoft.com/en-us/windows/apps/design/globalizing/prepare-your-app-for-localization)：
  把可见文本与代码分离、避免字符串拼接、预留界面伸缩空间。
- [Argos Translate](https://github.com/argosopentech/argos-translate)：MIT 许可的离线
  翻译工具；本项目只用于构建机器初稿，不作为运行依赖。

德语、西班牙语和韩语目录尚未达到可选择的覆盖门槛，因此本版不在设置中展示；
以后完成完整目录和审校后再启用。
