from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from scenelens.storage.workspace_catalog import (
    GlobalWorkspaceSearch,
    WorkspaceSearchRecord,
)


ENTITY_LABELS = {
    "project": "项目",
    "shot": "镜头",
    "workbench_task": "项目任务",
    "knowledge_item": "资料",
    "visual_board": "视觉资料板",
    "asset": "资产",
    "dimension_study": "研究维度",
    "comparison_work": "对照作品",
    "review_task": "审阅任务",
    "quality_gate": "质量门禁",
}


class GlobalSearchDialog(QDialog):
    result_activated = Signal(object)

    def __init__(
        self,
        service: GlobalWorkspaceSearch | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service or GlobalWorkspaceSearch()
        self._records: list[WorkspaceSearchRecord] = []
        self.setWindowTitle("GATalk 全局检索")
        self.resize(1040, 680)
        layout = QVBoxLayout(self)
        header = QLabel("搜索项目、资料、研究结论、资产、任务和质量门禁")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)
        note = QLabel(
            "检索只读取已登记的本地 GATalk 项目。结果保留所属工作台、项目和来源对象，"
            "不会建立内容副本。"
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        layout.addWidget(note)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入标题、标签、项目名或正文关键词…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.refresh)
        layout.addWidget(self.search_edit)
        self.results = QTreeWidget()
        self.results.setHeaderLabels(
            ["结果", "类型", "所属项目", "工作台", "更新时间"]
        )
        self.results.setRootIsDecorated(False)
        self.results.setAlternatingRowColors(True)
        self.results.setColumnWidth(0, 330)
        self.results.setColumnWidth(1, 110)
        self.results.setColumnWidth(2, 230)
        self.results.setColumnWidth(3, 170)
        self.results.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.results, 1)
        footer = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setProperty("role", "muted")
        footer.addWidget(self.summary)
        footer.addStretch(1)
        refresh = QPushButton("重新建立索引")
        refresh.clicked.connect(self.refresh)
        footer.addWidget(refresh)
        self.open_button = QPushButton("打开来源")
        self.open_button.setProperty("primary", True)
        self.open_button.clicked.connect(self._open_selected)
        footer.addWidget(self.open_button)
        layout.addLayout(footer)
        self.results.currentItemChanged.connect(
            lambda *_args: self.open_button.setEnabled(
                self.results.currentItem() is not None
            )
        )
        self.open_button.setEnabled(False)
        self.refresh()

    def refresh(self, *_args) -> None:
        query = self.search_edit.text().strip()
        self._records = list(self._service.search(query))
        self.results.clear()
        for index, record in enumerate(self._records):
            row = QTreeWidgetItem(
                [
                    record.title,
                    ENTITY_LABELS.get(record.entity_type, record.entity_type),
                    record.project_title or "未命名项目",
                    _workspace_label(record.workspace_id),
                    record.updated_at[:19].replace("T", " "),
                ]
            )
            row.setData(0, Qt.ItemDataRole.UserRole, index)
            row.setToolTip(
                0,
                (record.summary[:800] or "无摘要")
                + f"\n\n来源：{record.project_root}",
            )
            self.results.addTopLevelItem(row)
        self.summary.setText(
            f"{len(self._records)} 项结果  ·  "
            f"已登记 {len(self._service.locations())} 个本地项目"
        )
        self.open_button.setEnabled(self.results.currentItem() is not None)

    def _open_selected(self, *_args) -> None:
        row = self.results.currentItem()
        if row is None:
            return
        index = int(row.data(0, Qt.ItemDataRole.UserRole))
        if not 0 <= index < len(self._records):
            return
        self.result_activated.emit(self._records[index])
        self.accept()


def _workspace_label(workspace_id: str) -> str:
    return {
        "scene_art_control": "场景美术控制",
        "artwork_study": "作品研究",
        "asset_breakdown": "资产拆分",
        "reference_knowledge": "参考资料库",
        "comparative_study": "对照研究",
        "review_control": "审阅中心",
    }.get(workspace_id, workspace_id)
