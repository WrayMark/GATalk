from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from scenelens.storage.diagnostics import (
    ProjectDiagnostic,
    create_recovery_point,
    inspect_project,
    list_recovery_points,
    repair_project_directories,
    restore_recovery_point,
    write_diagnostic_report,
)
from scenelens.storage.recent_projects import RecentProjects
from scenelens.storage.workspace_catalog import WorkspaceCatalogStore


class DiagnosticsDialog(QDialog):
    def __init__(self, previous_unclean_session: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GATalk 项目诊断与恢复检查")
        self.resize(760, 520)
        self._results: list[ProjectDiagnostic] = []
        layout = QVBoxLayout(self)
        notice = QLabel(
            "检查项目入口、结构化数据、资料引用、写入权限和恢复点。"
            "检查本身不会修改项目；只有下方明确标注的修复或恢复操作会写入。"
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        if previous_unclean_session:
            warning = QLabel(
                "检测到上次 GATalk 未正常关闭。进行中的任务已标记为“上次退出时中断”；"
                "建议检查最近项目并确认最新保存结果。"
            )
            warning.setWordWrap(True)
            warning.setProperty("tone", "warning")
            layout.addWidget(warning)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        scan_recent = QPushButton("检查最近项目")
        scan_recent.clicked.connect(self._scan_recent)
        row.addWidget(scan_recent)
        choose = QPushButton("检查指定目录…")
        choose.clicked.connect(self._scan_folder)
        row.addWidget(choose)
        self.snapshot_button = QPushButton("建立恢复点")
        self.snapshot_button.clicked.connect(self._snapshot)
        row.addWidget(self.snapshot_button)
        self.repair_button = QPushButton("修复目录")
        self.repair_button.clicked.connect(self._repair_directories)
        row.addWidget(self.repair_button)
        self.restore_button = QPushButton("从备份恢复…")
        self.restore_button.clicked.connect(self._restore)
        row.addWidget(self.restore_button)
        self.relink_button = QPushButton("重连移动项目…")
        self.relink_button.clicked.connect(self._relink)
        row.addWidget(self.relink_button)
        row.addStretch(1)
        export = QPushButton("导出诊断报告…")
        export.clicked.connect(self._export)
        row.addWidget(export)
        layout.addLayout(row)
        self.list.currentRowChanged.connect(self._selection_changed)
        self._selection_changed(-1)

    def _scan_recent(self) -> None:
        roots = {
            item.manifest_path.parent.resolve()
            for item in RecentProjects().load()
        }
        if not roots:
            QMessageBox.information(self, "没有最近项目", "最近项目列表中没有可检查的目录。")
            return
        for root in sorted(roots):
            self._add_result(inspect_project(root))

    def _scan_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择 GATalk 项目目录")
        if path:
            self._add_result(inspect_project(path))

    def _add_result(self, result: ProjectDiagnostic) -> None:
        self._results = [item for item in self._results if item.root != result.root]
        self._results.append(result)
        self._refresh()

    def _refresh(self) -> None:
        self.list.clear()
        labels = {"ok": "正常", "warning": "需要检查", "invalid": "无法识别", "missing": "目录缺失"}
        for result in self._results:
            detail = "；".join(result.issues) if result.issues else "结构检查未发现问题"
            row = QListWidgetItem(
                f"{labels.get(result.status, result.status)}  ·  {result.project_type}\n"
                f"{result.root}\n{detail}  ·  备份 {result.backup_count} 项"
            )
            row.setData(256, result.root)
            self.list.addItem(row)

    def _selection_changed(self, row: int) -> None:
        enabled = 0 <= row < len(self._results)
        self.snapshot_button.setEnabled(enabled)
        self.repair_button.setEnabled(enabled)
        self.restore_button.setEnabled(enabled)
        self.relink_button.setEnabled(enabled)

    def _selected(self) -> ProjectDiagnostic | None:
        row = self.list.currentRow()
        if 0 <= row < len(self._results):
            return self._results[row]
        return None

    def _snapshot(self) -> None:
        result = self._selected()
        if result is None:
            return
        label, accepted = QInputDialog.getText(
            self,
            "建立恢复点",
            "备注：",
            text="manual",
        )
        if not accepted:
            return
        try:
            point = create_recovery_point(result.root, label=label)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法建立恢复点", str(exc))
            return
        self._add_result(inspect_project(result.root))
        QMessageBox.information(
            self,
            "恢复点已建立",
            f"已保存项目入口和结构化数据库：\n{point.path}",
        )

    def _repair_directories(self) -> None:
        result = self._selected()
        if result is None:
            return
        try:
            created = repair_project_directories(result.root)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法修复目录", str(exc))
            return
        self._add_result(inspect_project(result.root))
        message = (
            "已补建：" + "、".join(created)
            if created
            else "项目基础目录完整，不需要处理。"
        )
        QMessageBox.information(self, "目录检查完成", message)

    def _restore(self) -> None:
        result = self._selected()
        if result is None:
            return
        points = [item for item in list_recovery_points(result.root) if item.restorable]
        if not points:
            QMessageBox.information(self, "没有恢复点", "当前项目没有可用的备份。")
            return
        labels = [f"{item.kind} · {item.label}" for item in points]
        selected, accepted = QInputDialog.getItem(
            self,
            "从备份恢复",
            "选择恢复点：",
            labels,
            0,
            False,
        )
        if not accepted:
            return
        index = labels.index(selected)
        if QMessageBox.warning(
            self,
            "确认恢复",
            "恢复会替换当前项目入口及结构化数据库。GATalk 会先自动建立一个"
            "“恢复前”安全点。原始图片不会被覆盖。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            safety = restore_recovery_point(result.root, points[index].path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "恢复失败", str(exc))
            return
        self._add_result(inspect_project(result.root))
        QMessageBox.information(
            self,
            "恢复完成",
            f"项目结构化数据已恢复。恢复前状态保存在：\n{safety.path}",
        )

    def _relink(self) -> None:
        result = self._selected()
        if result is None:
            return
        path = QFileDialog.getExistingDirectory(
            self,
            "选择项目移动后的新目录",
        )
        if not path:
            return
        replacement = inspect_project(path)
        if not replacement.entry_filename or replacement.status in {"invalid", "missing"}:
            QMessageBox.warning(self, "无法重连", "新目录不是可识别的 GATalk 项目。")
            return
        old_root = Path(result.root).resolve()
        recent = RecentProjects()
        updated_recent = False
        for item in recent.load():
            if item.manifest_path.parent.resolve() == old_root:
                updated_recent = recent.relink(
                    item.project_id,
                    Path(path) / replacement.entry_filename,
                ) or updated_recent
        try:
            WorkspaceCatalogStore().relink(old_root, path)
            updated_catalog = True
        except (OSError, ValueError):
            updated_catalog = False
        self._results = [item for item in self._results if item.root != result.root]
        self._add_result(replacement)
        if updated_recent or updated_catalog:
            QMessageBox.information(
                self,
                "项目位置已更新",
                "最近项目和全局检索将使用新位置；项目内容没有被移动或复制。",
            )
        else:
            QMessageBox.information(
                self,
                "项目已检查",
                "新目录有效，但旧位置不在最近项目或全局索引中，无需更新记录。",
            )

    def _export(self) -> None:
        if not self._results:
            QMessageBox.information(self, "没有诊断结果", "请先检查至少一个项目目录。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出诊断报告",
            "GATalk_诊断报告.json",
            "JSON (*.json)",
        )
        if path:
            write_diagnostic_report(Path(path), self._results)
            QMessageBox.information(self, "报告已导出", "诊断报告不含图片、API Key 或项目正文。")
