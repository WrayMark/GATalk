from __future__ import annotations

from dataclasses import fields

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scenelens.storage.models import ArtBrief
from scenelens.storage.project_store import ProjectStore


ITEM_KIND_ROLE = Qt.ItemDataRole.UserRole
ITEM_ID_ROLE = Qt.ItemDataRole.UserRole + 1
ITEM_PARENT_ID_ROLE = Qt.ItemDataRole.UserRole + 2


class ProjectNavigator(QWidget):
    new_shot_requested = Signal()
    edit_brief_requested = Signal()
    shot_requested = Signal(str)
    version_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.project_label = QLabel("尚未打开项目")
        self.project_label.setWordWrap(True)
        self.project_label.setStyleSheet("font-weight: 600; padding: 4px;")
        layout.addWidget(self.project_label)

        button_row = QHBoxLayout()
        self.new_shot_button = QPushButton("新建 Shot")
        self.new_shot_button.setEnabled(False)
        self.new_shot_button.clicked.connect(self.new_shot_requested.emit)
        button_row.addWidget(self.new_shot_button)
        self.brief_button = QPushButton("Art Brief")
        self.brief_button.setEnabled(False)
        self.brief_button.clicked.connect(self.edit_brief_requested.emit)
        button_row.addWidget(self.brief_button)
        layout.addLayout(button_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.tree, 1)

    def clear_project(self) -> None:
        self.project_label.setText("尚未打开项目")
        self.new_shot_button.setEnabled(False)
        self.brief_button.setEnabled(False)
        self.tree.clear()

    def refresh(
        self,
        store: ProjectStore,
        active_shot_id: str | None,
        active_version_id: str | None,
    ) -> None:
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            self.project_label.setText(store.manifest.name)
            self.new_shot_button.setEnabled(not store.read_only)
            self.brief_button.setEnabled(not store.read_only)
            root = QTreeWidgetItem([store.manifest.name])
            root.setData(0, ITEM_KIND_ROLE, "project")
            root.setData(0, ITEM_ID_ROLE, store.manifest.project_id)
            self.tree.addTopLevelItem(root)
            selected: QTreeWidgetItem | None = None
            for shot in store.list_shots():
                shot_item = QTreeWidgetItem([shot.name])
                shot_item.setData(0, ITEM_KIND_ROLE, "shot")
                shot_item.setData(0, ITEM_ID_ROLE, shot.id)
                root.addChild(shot_item)
                if shot.id == active_shot_id and active_version_id is None:
                    selected = shot_item

                reference_text = (
                    "参考图"
                    if shot.reference_asset_id is not None
                    else "参考图（未导入）"
                )
                reference_item = QTreeWidgetItem([reference_text])
                reference_item.setData(0, ITEM_KIND_ROLE, "reference")
                reference_item.setData(0, ITEM_ID_ROLE, shot.reference_asset_id)
                reference_item.setData(0, ITEM_PARENT_ID_ROLE, shot.id)
                shot_item.addChild(reference_item)

                for version in store.list_versions(shot.id):
                    item = QTreeWidgetItem(
                        [f"V{version.ordinal} · {version.name}"]
                    )
                    item.setData(0, ITEM_KIND_ROLE, "version")
                    item.setData(0, ITEM_ID_ROLE, version.id)
                    item.setData(0, ITEM_PARENT_ID_ROLE, shot.id)
                    shot_item.addChild(item)
                    if version.id == active_version_id:
                        selected = item
            root.setExpanded(True)
            for index in range(root.childCount()):
                root.child(index).setExpanded(True)
            if selected is not None:
                self.tree.setCurrentItem(selected)
        finally:
            self.tree.blockSignals(False)

    def _selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            return
        item = selected[0]
        kind = item.data(0, ITEM_KIND_ROLE)
        if kind in {"shot", "reference"}:
            shot_id = (
                item.data(0, ITEM_ID_ROLE)
                if kind == "shot"
                else item.data(0, ITEM_PARENT_ID_ROLE)
            )
            if shot_id:
                self.shot_requested.emit(str(shot_id))
        elif kind == "version":
            shot_id = item.data(0, ITEM_PARENT_ID_ROLE)
            version_id = item.data(0, ITEM_ID_ROLE)
            if shot_id and version_id:
                self.version_requested.emit(str(shot_id), str(version_id))


ART_BRIEF_LABELS = {
    "scene_type": "场景类型",
    "production_stage": "当前制作阶段",
    "target_style": "目标风格",
    "time_weather": "时间和天气",
    "target_mood": "目标情绪",
    "primary_focus": "第一视觉焦点",
    "secondary_focus": "次要视觉焦点",
    "preserve_content": "希望保留的内容",
    "main_issues": "当前主要问题",
    "excluded_review": "暂不需要审阅的部分",
    "constraints": "制作条件与限制",
}

MULTILINE_FIELDS = {
    "preserve_content",
    "main_issues",
    "excluded_review",
    "constraints",
}


class ArtBriefDialog(QDialog):
    def __init__(self, brief: ArtBrief, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("项目 Art Brief")
        self.resize(680, 720)
        root_layout = QVBoxLayout(self)

        hint = QLabel(
            "Art Brief 会作为后续算法解释和审阅判断的上下文。"
            "当前 M1A 保存项目级 Brief。"
        )
        hint.setWordWrap(True)
        root_layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.editors: dict[str, QLineEdit | QTextEdit] = {}
        for field in fields(ArtBrief):
            value = getattr(brief, field.name)
            if field.name in MULTILINE_FIELDS:
                editor = QTextEdit()
                editor.setPlainText(value)
                editor.setMinimumHeight(78)
            else:
                editor = QLineEdit(value)
            self.editors[field.name] = editor
            form.addRow(f"{ART_BRIEF_LABELS[field.name]}：", editor)
        scroll.setWidget(form_widget)
        root_layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)

    def art_brief(self) -> ArtBrief:
        values: dict[str, str] = {}
        for name, editor in self.editors.items():
            if isinstance(editor, QTextEdit):
                values[name] = editor.toPlainText().strip()
            else:
                values[name] = editor.text().strip()
        return ArtBrief(**values)
