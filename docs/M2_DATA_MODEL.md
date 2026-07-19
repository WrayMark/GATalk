# SceneLens M2 共享核心与 schema v5

状态：M2 基础切片已实现  
日期：2026-07-19

## 1. 目标

M2 将 SceneLens 从单一场景审阅模块扩展为可承载未来 Game Art Workbench
模块的模块化单体。共享核心只表达跨模块关系，不包含场景审阅算法、供应商 SDK
或 PySide6 控件。

## 2. 共享领域对象

`scenelens.core.domain` 可以表示：

- `Project`、`Asset`、`Shot`、`Version`、`Region`
- `Evidence`、`Annotation`、`Task`
- `DerivedArtifact`、`AIRun`、`SourceDocument`
- `ReviewProfile`、`QualityGate`

持久化对象保留 `module_id`，使来源和所有权明确。Evidence 继续区分测量结果、
算法推断和美术判断；AI 输出是带 `source=ai_provider` 的证据来源，不新增一个
模糊的“AI 就是真相”类别。

## 3. schema v5

schema v5 新增以下共享表：

- `workbench_evidence`
- `workbench_annotations`
- `workbench_tasks`
- `workbench_derived_artifacts`
- `workbench_ai_runs`
- `workbench_source_documents`
- `workbench_review_profiles`
- `workbench_quality_gates`

这些表只保存可追踪的数据和 provider/model ID。API Key 不属于项目数据；
`workbench_ai_runs.input_manifest_json` 会拒绝常见凭据字段。

M1B 的 `visual_review_*` 表保持不变，模块 schema 版本仍为 3。全局数据库从
v4 升到 v5 时，先把数据库、`project.json` 和备份清单写入
`backups/pre-migration_0004_to_0005_*`，再在独立事务中迁移。

## 4. 工作区注册

`WorkbenchRegistry` 显式注册受信任的内置：

- Workspace
- Reviewer
- Provider

注册身份稳定且拒绝重复。当前不扫描目录、不执行未知代码，也不提供第三方插件
市场。测试示例模块使用 `example.notes` 证明新的 Workspace、Reviewer 和
Provider 不需要修改 SceneLens 场景审阅实现。

项目存储不再用 Python 条件硬编码唯一业务模块；`module_schema_versions` 是
模块是否已安装到项目数据库的事实来源。共享表通过独立
`workspace_read_connection()` / `workspace_write_connection()` 访问。

## 5. 后续迁移

M2 后续供应商、审阅器和灯光方案优先写入现有 `AIRun`、`Evidence`、
`Annotation`、`Task`、`ReviewProfile` 与 `QualityGate`。只有出现 SceneLens
模块独有且无法合理表达的数据时，才新增 `visual_review_*` 表和模块 schema
版本，避免共享核心吸收业务细节。

