from dataclasses import replace
from pathlib import Path
import shutil

from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.comparative_study.storage import ComparativeStudyStore
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.storage.diagnostics import (
    create_recovery_point,
    inspect_project,
    repair_project_directories,
    restore_recovery_point,
    write_diagnostic_report,
)


def test_diagnostics_recognizes_new_project_types(tmp_path: Path):
    library = KnowledgeLibraryStore.create(tmp_path / "library", "资料库")
    comparison = ComparativeStudyStore.create(tmp_path / "comparison", "对照")

    library_result = inspect_project(library.root)
    comparison_result = inspect_project(comparison.root)

    assert library_result.status == "ok"
    assert library_result.project_type == "参考资料库"
    assert comparison_result.status == "ok"
    assert comparison_result.project_type == "作品对照研究"


def test_diagnostic_report_has_privacy_contract(tmp_path: Path):
    result = inspect_project(tmp_path / "missing")
    path = write_diagnostic_report(tmp_path / "report.json", (result,))
    text = path.read_text(encoding="utf-8")

    assert "不包含 API Key" in text
    assert "gatalk.diagnostic_report" in text


def test_asset_project_directories_can_be_repaired_without_touching_entry(
    tmp_path: Path,
):
    store = AssetBreakdownStore.create(tmp_path / "资产项目", "桥梁套件")
    entry_bytes = (store.root / "asset_project.json").read_bytes()
    shutil.rmtree(store.root / "artifacts")

    result = inspect_project(store.root)
    created = repair_project_directories(store.root)

    assert result.status == "warning"
    assert "artifacts" in result.issues[0]
    assert created == ("artifacts",)
    assert (store.root / "asset_project.json").read_bytes() == entry_bytes


def test_manifest_recovery_point_restores_project_state(tmp_path: Path):
    store = AssetBreakdownStore.create(tmp_path / "资产项目", "恢复前")
    recovery = create_recovery_point(store.root, label="known_good")
    store.state = replace(store.state, title="错误修改")
    store.save()
    store.close()

    restore_recovery_point(store.root, recovery.path)
    reopened = AssetBreakdownStore.open(store.root)

    assert reopened.state.title == "恢复前"
    assert any((store.root / "backups").glob("recovery_*_pre_restore"))
