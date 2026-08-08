from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scenelens.modules.review_control.models import (
    GATE_STATES,
    TASK_PRIORITIES,
    TASK_STATUSES,
    VERIFICATION_STATES,
)
from scenelens.modules.review_control.storage import ReviewCenterStore
from scenelens.modules.review_control.presets import (
    BUILTIN_GATE_PRESETS,
    PRODUCTION_STAGES,
    stage_label,
)


MODULE_LABELS = {
    "scenelens.visual_review": "场景美术控制",
    "scenelens.artwork_study": "作品研究",
    "scenelens.asset_breakdown": "资产拆分",
    "gatalk.review_control": "审阅中心",
}
ENTITY_LABELS = {
    "review_finding": "审阅发现",
    "confirmed_task": "已确认任务",
    "lighting_annotation": "灯光标注",
    "ai_preview_task": "优化预演任务",
    "dimension_study": "作品研究维度",
    "asset": "资产项",
    "asset_item": "资产项",
    "workbench_task": "场景审阅任务",
    "manual": "手动任务",
}
STATUS_LABELS = {
    "open": "待处理",
    "in_progress": "处理中",
    "done": "已完成",
    "dismissed": "已关闭",
}
PRIORITY_LABELS = {
    "critical": "阻塞",
    "high": "高",
    "medium": "中",
    "low": "低",
}
VERIFICATION_LABELS = {
    "improved": "已改善",
    "unchanged": "无明显变化",
    "worse": "进一步偏离",
    "resolved": "已解决",
    "insufficient_evidence": "证据不足",
}
GATE_LABELS = {
    "not_evaluated": "尚未评估",
    "pass": "通过",
    "warning": "需复核",
    "fail": "未通过",
    "insufficient_evidence": "证据不足",
}


class ReviewControlWindow(QMainWindow):
    workspace_home_requested = Signal()

    def __init__(self, store: ReviewCenterStore | None = None) -> None:
        super().__init__()
        self._owns_store = store is None
        self._store = store or ReviewCenterStore.open_default()
        self._current_task_id = ""
        self._current_gate_id = ""
        self.setWindowTitle("GATalk — 审阅任务与质量门禁中心")
        self.resize(1500, 900)
        self.setMinimumSize(1080, 700)
        self._build_ui()
        self.refresh()
        if self._store.read_only:
            self.setWindowTitle(self.windowTitle() + "（只读）")
            for button in self.findChildren(QPushButton):
                button.setEnabled(False)
            self.statusBar().showMessage(
                "审阅中心已被另一个 GATalk 进程占用写权限；当前可查看和导出。"
            )

    def _build_ui(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        home = QAction("工作台首页", self)
        home.setShortcut(QKeySequence("Ctrl+Shift+H"))
        home.triggered.connect(self.workspace_home_requested)
        file_menu.addAction(home)
        export = QAction("导出审阅中心 JSON…", self)
        export.triggered.connect(self._export)
        file_menu.addAction(export)
        backup = QAction("立即备份", self)
        backup.triggered.connect(self._backup)
        file_menu.addAction(backup)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("审阅任务与质量门禁中心")
        title.setObjectName("heroTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.summary = QLabel()
        self.summary.setProperty("role", "muted")
        header.addWidget(self.summary)
        outer.addLayout(header)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tasks_tab(), "审阅任务")
        self.tabs.addTab(self._build_gates_tab(), "质量门禁")
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage(
            "任务和门禁保存在本机审阅中心；来源项目不会被反向自动修改。"
        )

    def _build_tasks_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索任务、项目或标签…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._refresh_tasks)
        filters.addWidget(self.search_edit, 1)
        self.status_filter = QComboBox()
        self.status_filter.addItem("全部状态", "")
        for value in TASK_STATUSES:
            self.status_filter.addItem(STATUS_LABELS[value], value)
        self.status_filter.currentIndexChanged.connect(self._refresh_tasks)
        filters.addWidget(self.status_filter)
        self.stage_filter = QComboBox()
        self.stage_filter.addItem("全部阶段", "")
        for value, label in PRODUCTION_STAGES:
            self.stage_filter.addItem(label, value)
        self.stage_filter.currentIndexChanged.connect(self._refresh_tasks)
        filters.addWidget(self.stage_filter)
        left_layout.addLayout(filters)
        self.task_tree = QTreeWidget()
        self.task_tree.setHeaderLabels(
            ["任务", "项目", "阶段", "来源", "优先级", "状态", "前置"]
        )
        self.task_tree.setRootIsDecorated(False)
        self.task_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.task_tree.currentItemChanged.connect(self._show_task)
        left_layout.addWidget(self.task_tree, 1)
        task_actions = QHBoxLayout()
        add = QPushButton("新建审阅任务")
        add.clicked.connect(self._new_task)
        task_actions.addWidget(add)
        start = QPushButton("批量开始")
        start.clicked.connect(lambda: self._batch_task_status("in_progress"))
        task_actions.addWidget(start)
        complete = QPushButton("批量完成")
        complete.clicked.connect(lambda: self._batch_task_status("done"))
        task_actions.addWidget(complete)
        left_layout.addLayout(task_actions)
        splitter.addWidget(left)
        splitter.addWidget(self._build_task_details())
        splitter.setSizes([760, 570])
        return splitter

    def _build_task_details(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 8, 8, 16)
        self.task_source = QLabel("选择任务查看来源")
        self.task_source.setWordWrap(True)
        self.task_source.setProperty("role", "muted")
        layout.addWidget(self.task_source)
        form = QFormLayout()
        self.task_title = QLineEdit()
        self.task_priority = QComboBox()
        for value in TASK_PRIORITIES:
            self.task_priority.addItem(PRIORITY_LABELS[value], value)
        self.task_status = QComboBox()
        for value in TASK_STATUSES:
            self.task_status.addItem(STATUS_LABELS[value], value)
        self.task_labels = QLineEdit()
        self.task_labels.setPlaceholderText("用逗号分隔")
        self.task_stage = QComboBox()
        self.task_stage.addItem("未指定", "")
        for value, label in PRODUCTION_STAGES:
            self.task_stage.addItem(label, value)
        self.task_due = QLineEdit()
        self.task_due.setPlaceholderText("YYYY-MM-DD（可选）")
        dependency_row = QWidget()
        dependency_layout = QHBoxLayout(dependency_row)
        dependency_layout.setContentsMargins(0, 0, 0, 0)
        self.task_dependencies = QLabel("无")
        self.task_dependencies.setWordWrap(True)
        dependency_layout.addWidget(self.task_dependencies, 1)
        dependency_button = QPushButton("设置…")
        dependency_button.clicked.connect(self._edit_dependencies)
        dependency_layout.addWidget(dependency_button)
        self._task_dependency_ids: tuple[str, ...] = ()
        form.addRow("任务", self.task_title)
        form.addRow("优先级", self.task_priority)
        form.addRow("状态", self.task_status)
        form.addRow("制作阶段", self.task_stage)
        form.addRow("计划日期", self.task_due)
        form.addRow("前置任务", dependency_row)
        form.addRow("标签", self.task_labels)
        layout.addLayout(form)
        layout.addWidget(QLabel("处理说明"))
        self.task_description = QPlainTextEdit()
        self.task_description.setMaximumHeight(120)
        layout.addWidget(self.task_description)
        layout.addWidget(QLabel("验收条件"))
        self.task_acceptance = QPlainTextEdit()
        self.task_acceptance.setMaximumHeight(100)
        layout.addWidget(self.task_acceptance)
        actions = QHBoxLayout()
        save = QPushButton("保存任务")
        save.setProperty("primary", True)
        save.clicked.connect(self._save_task)
        actions.addWidget(save)
        delete = QPushButton("删除")
        delete.clicked.connect(self._delete_task)
        actions.addWidget(delete)
        layout.addLayout(actions)
        layout.addWidget(QLabel("版本复查记录"))
        self.verification_tree = QTreeWidget()
        self.verification_tree.setHeaderLabels(["版本", "结果", "证据", "时间"])
        self.verification_tree.setMinimumHeight(190)
        layout.addWidget(self.verification_tree)
        verify = QPushButton("记录新版本复查…")
        verify.clicked.connect(self._add_verification)
        layout.addWidget(verify)
        layout.addStretch(1)
        scroll.setWidget(body)
        return scroll

    def _build_gates_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        notice = QLabel(
            "门禁由用户定义验收条件。系统只记录结果和证据，不用总分替代判断。"
        )
        notice.setWordWrap(True)
        notice.setProperty("role", "muted")
        left_layout.addWidget(notice)
        template_group = QWidget()
        template_layout = QFormLayout(template_group)
        template_layout.setContentsMargins(0, 4, 0, 6)
        self.template_project = QLineEdit()
        self.template_project.setPlaceholderText("例如：中世纪村庄")
        self.template_stage = QComboBox()
        for preset in BUILTIN_GATE_PRESETS:
            self.template_stage.addItem(preset.label, preset.stage_id)
        apply_template = QPushButton("建立该阶段门禁")
        apply_template.clicked.connect(self._apply_gate_template)
        template_layout.addRow("项目", self.template_project)
        template_layout.addRow("制作阶段", self.template_stage)
        template_layout.addRow(apply_template)
        left_layout.addWidget(template_group)
        self.gate_tree = QTreeWidget()
        self.gate_tree.setHeaderLabels(
            ["门禁", "项目", "阶段", "维度", "状态", "必需"]
        )
        self.gate_tree.setRootIsDecorated(False)
        self.gate_tree.currentItemChanged.connect(self._show_gate)
        left_layout.addWidget(self.gate_tree, 1)
        add = QPushButton("新建质量门禁")
        add.clicked.connect(self._new_gate)
        left_layout.addWidget(add)
        splitter.addWidget(left)
        splitter.addWidget(self._build_gate_details())
        splitter.setSizes([760, 570])
        return splitter

    def _build_gate_details(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 8, 8, 16)
        form = QFormLayout()
        self.gate_name = QLineEdit()
        self.gate_dimension = QLineEdit()
        self.gate_project = QLineEdit()
        self.gate_stage = QComboBox()
        self.gate_stage.addItem("未指定", "")
        for value, label in PRODUCTION_STAGES:
            self.gate_stage.addItem(label, value)
        self.gate_required = QCheckBox("阻塞发布或交付")
        self.gate_state = QLabel("尚未评估")
        form.addRow("门禁", self.gate_name)
        form.addRow("维度", self.gate_dimension)
        form.addRow("项目", self.gate_project)
        form.addRow("制作阶段", self.gate_stage)
        form.addRow("性质", self.gate_required)
        form.addRow("当前状态", self.gate_state)
        layout.addLayout(form)
        layout.addWidget(QLabel("通过条件"))
        self.gate_criteria = QPlainTextEdit()
        self.gate_criteria.setMaximumHeight(130)
        layout.addWidget(self.gate_criteria)
        actions = QHBoxLayout()
        save = QPushButton("保存门禁")
        save.setProperty("primary", True)
        save.clicked.connect(self._save_gate)
        actions.addWidget(save)
        delete = QPushButton("删除")
        delete.clicked.connect(self._delete_gate)
        actions.addWidget(delete)
        layout.addLayout(actions)
        layout.addWidget(QLabel("版本评估记录"))
        self.gate_history = QTreeWidget()
        self.gate_history.setHeaderLabels(["版本", "结果", "证据", "时间"])
        layout.addWidget(self.gate_history, 1)
        evaluate = QPushButton("评估当前版本…")
        evaluate.clicked.connect(self._evaluate_gate)
        layout.addWidget(evaluate)
        return body

    def refresh(self) -> None:
        try:
            self._store.reload()
        except (OSError, ValueError):
            pass
        self._refresh_tasks()
        self._refresh_gates()
        tasks = self._store.state.tasks
        blockers = sum(
            item.required and item.state == "fail" for item in self._store.state.gates
        )
        blocked_tasks = sum(
            bool(self._store.unresolved_blockers(item.task_id))
            and item.status not in {"done", "dismissed"}
            for item in tasks
        )
        self.summary.setText(
            f"待处理 {sum(item.status == 'open' for item in tasks)}  ·  "
            f"处理中 {sum(item.status == 'in_progress' for item in tasks)}  ·  "
            f"受阻 {blocked_tasks}  ·  "
            f"未通过必需门禁 {blockers}"
        )

    def receive_handoff(self, payload: object):
        values = payload if isinstance(payload, (list, tuple)) else (payload,)
        added = 0
        received = []
        for value in values:
            if isinstance(value, dict):
                before = len(self._store.state.tasks)
                received.append(self._store.add_task_from_handoff(value))
                added += len(self._store.state.tasks) - before
        self.refresh()
        self.statusBar().showMessage(
            f"已接收 {added} 项新任务；重复来源不会重复建立。", 5000
        )
        if not received:
            return None
        return received[0] if len(received) == 1 else tuple(received)

    def focus_entity(self, entity_type: str, entity_id: str) -> None:
        task_mode = entity_type == "review_task"
        self.tabs.setCurrentIndex(0 if task_mode else 1)
        tree = self.task_tree if task_mode else self.gate_tree
        for index in range(tree.topLevelItemCount()):
            row = tree.topLevelItem(index)
            if str(row.data(0, Qt.ItemDataRole.UserRole)) == entity_id:
                tree.setCurrentItem(row)
                return

    def _refresh_tasks(self, *_args) -> None:
        self.task_tree.clear()
        query = self.search_edit.text().strip().casefold()
        status = str(self.status_filter.currentData() or "")
        stage = str(self.stage_filter.currentData() or "")
        for task in sorted(
            self._store.state.tasks,
            key=lambda item: (TASK_PRIORITIES.index(item.priority), item.created_at),
        ):
            if status and task.status != status:
                continue
            if stage and task.production_stage != stage:
                continue
            haystack = " ".join(
                (task.title, task.source_project_title, task.description, *task.labels)
            ).casefold()
            if query and query not in haystack:
                continue
            row = QTreeWidgetItem(
                [
                    task.title,
                    task.source_project_title or "未指定",
                    stage_label(task.production_stage),
                    MODULE_LABELS.get(task.source_module_id, task.source_module_id or "手动"),
                    PRIORITY_LABELS[task.priority],
                    STATUS_LABELS[task.status],
                    str(len(self._store.unresolved_blockers(task.task_id))) or "0",
                ]
            )
            row.setData(0, Qt.ItemDataRole.UserRole, task.task_id)
            self.task_tree.addTopLevelItem(row)
        if self.task_tree.topLevelItemCount():
            self.task_tree.setCurrentItem(self.task_tree.topLevelItem(0))

    def _show_task(self, row: QTreeWidgetItem | None, _previous=None) -> None:
        if row is None:
            return
        task_id = str(row.data(0, Qt.ItemDataRole.UserRole))
        task = next(item for item in self._store.state.tasks if item.task_id == task_id)
        self._current_task_id = task_id
        self.task_title.setText(task.title)
        self._set_combo(self.task_priority, task.priority)
        self._set_combo(self.task_status, task.status)
        self._set_combo(self.task_stage, task.production_stage)
        self.task_due.setText(task.due_date)
        self._task_dependency_ids = task.blocked_by_task_ids
        self._refresh_dependency_label()
        self.task_labels.setText("，".join(task.labels))
        self.task_description.setPlainText(task.description)
        self.task_acceptance.setPlainText(task.acceptance_criteria)
        self.task_source.setText(
            f"来源：{MODULE_LABELS.get(task.source_module_id, task.source_module_id or '手动')}"
            f"  ·  项目：{task.source_project_title or '未指定'}\n"
            f"对象：{ENTITY_LABELS.get(task.source_entity_type, task.source_entity_type or '未指定')}"
            f"  ·  标识：{task.source_entity_id or '无'}"
            f"  ·  版本：{task.source_version_id or '未指定'}\n"
            f"路径：{task.source_project_path or '未记录'}"
        )
        self.verification_tree.clear()
        for item in self._store.state.verifications:
            if item.task_id != task_id:
                continue
            self.verification_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        item.version_label,
                        VERIFICATION_LABELS[item.state],
                        item.evidence_summary,
                        item.created_at,
                    ]
                )
            )

    def _new_task(self) -> None:
        task = self._store.add_task_from_handoff(
            {
                "task_id": "",
                "title": "新建审阅任务",
                "source_module_id": "gatalk.review_control",
                "source_entity_type": "manual",
                "source_entity_id": str(id(self)) + str(len(self._store.state.tasks)),
            }
        )
        self._current_task_id = task.task_id
        self.refresh()

    def _save_task(self) -> None:
        task = self._task()
        if task is None:
            return
        labels = tuple(
            dict.fromkeys(
                value.strip()
                for value in self.task_labels.text().replace("，", ",").split(",")
                if value.strip()
            )
        )
        self._store.update_task(
            replace(
                task,
                title=self.task_title.text().strip() or task.title,
                description=self.task_description.toPlainText().strip(),
                acceptance_criteria=self.task_acceptance.toPlainText().strip(),
                priority=str(self.task_priority.currentData()),
                status=str(self.task_status.currentData()),
                production_stage=str(self.task_stage.currentData() or ""),
                due_date=self.task_due.text().strip(),
                blocked_by_task_ids=self._task_dependency_ids,
                labels=labels,
            )
        )
        self.refresh()

    def _batch_task_status(self, status: str) -> None:
        task_ids = tuple(
            str(row.data(0, Qt.ItemDataRole.UserRole))
            for row in self.task_tree.selectedItems()
        )
        if not task_ids:
            QMessageBox.information(self, "未选择任务", "请先选择一个或多个任务。")
            return
        self._store.batch_update_tasks(task_ids, status=status)
        self.refresh()

    def _edit_dependencies(self) -> None:
        task = self._task()
        if task is None:
            return
        dialog = DependencyDialog(
            self._store.state.tasks,
            task.task_id,
            self._task_dependency_ids,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._task_dependency_ids = dialog.selected_ids()
        self._refresh_dependency_label()

    def _refresh_dependency_label(self) -> None:
        names = {
            item.task_id: item.title for item in self._store.state.tasks
        }
        labels = [
            names.get(item, "已删除任务")
            for item in self._task_dependency_ids
        ]
        self.task_dependencies.setText("；".join(labels) if labels else "无")

    def _delete_task(self) -> None:
        if not self._current_task_id:
            return
        if QMessageBox.question(self, "删除任务", "删除任务及其全部复查记录？") != QMessageBox.StandardButton.Yes:
            return
        self._store.delete_task(self._current_task_id)
        self._current_task_id = ""
        self.refresh()

    def _add_verification(self) -> None:
        task = self._task()
        if task is None:
            return
        value = VerificationDialog("记录新版本复查", False, self)
        if value.exec() != QDialog.DialogCode.Accepted:
            return
        self._store.add_verification(
            task.task_id,
            version_label=value.version_label(),
            version_id=value.version_id(),
            state=value.state(),
            evidence_summary=value.evidence(),
            notes=value.notes(),
        )
        if value.state() in {"resolved", "improved"} and task.status == "open":
            self._store.update_task(replace(task, status="in_progress"))
        self.refresh()

    def _refresh_gates(self) -> None:
        self.gate_tree.clear()
        for gate in self._store.state.gates:
            row = QTreeWidgetItem(
                [
                    gate.name,
                    gate.source_project_title or "跨项目",
                    stage_label(gate.production_stage),
                    gate.dimension,
                    GATE_LABELS[gate.state],
                    "是" if gate.required else "否",
                ]
            )
            row.setData(0, Qt.ItemDataRole.UserRole, gate.gate_id)
            self.gate_tree.addTopLevelItem(row)
        if self.gate_tree.topLevelItemCount():
            self.gate_tree.setCurrentItem(self.gate_tree.topLevelItem(0))

    def _show_gate(self, row: QTreeWidgetItem | None, _previous=None) -> None:
        if row is None:
            return
        gate_id = str(row.data(0, Qt.ItemDataRole.UserRole))
        gate = next(item for item in self._store.state.gates if item.gate_id == gate_id)
        self._current_gate_id = gate_id
        self.gate_name.setText(gate.name)
        self.gate_dimension.setText(gate.dimension)
        self.gate_project.setText(gate.source_project_title)
        self._set_combo(self.gate_stage, gate.production_stage)
        self.gate_required.setChecked(gate.required)
        self.gate_state.setText(GATE_LABELS[gate.state])
        self.gate_criteria.setPlainText(gate.acceptance_criteria)
        self.gate_history.clear()
        for item in self._store.state.gate_evaluations:
            if item.gate_id == gate_id:
                self.gate_history.addTopLevelItem(
                    QTreeWidgetItem(
                        [
                            item.version_label,
                            GATE_LABELS[item.state],
                            item.evidence_summary,
                            item.created_at,
                        ]
                    )
                )

    def _new_gate(self) -> None:
        gate = self._store.add_gate(
            name="新建质量门禁",
            dimension="综合",
            acceptance_criteria="请写明可复核的通过条件。",
            required=True,
        )
        self._current_gate_id = gate.gate_id
        self.refresh()

    def _save_gate(self) -> None:
        gate = self._gate()
        if gate is None:
            return
        self._store.update_gate(
            replace(
                gate,
                name=self.gate_name.text().strip() or gate.name,
                dimension=self.gate_dimension.text().strip() or "综合",
                source_project_title=self.gate_project.text().strip(),
                production_stage=str(self.gate_stage.currentData() or ""),
                acceptance_criteria=self.gate_criteria.toPlainText().strip(),
                required=self.gate_required.isChecked(),
            )
        )
        self.refresh()

    def _apply_gate_template(self) -> None:
        project_title = self.template_project.text().strip()
        if not project_title:
            QMessageBox.information(self, "请填写项目", "门禁需要绑定一个项目名称。")
            return
        stage = str(self.template_stage.currentData())
        project_id = "manual:" + project_title.casefold()
        try:
            added = self._store.apply_gate_template(
                stage,
                source_project_id=project_id,
                source_project_title=project_title,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法建立门禁", str(exc))
            return
        self.refresh()
        self.statusBar().showMessage(
            f"已建立 {len(added)} 项门禁；已有同模板门禁不会重复添加。",
            5000,
        )

    def _delete_gate(self) -> None:
        if not self._current_gate_id:
            return
        if QMessageBox.question(self, "删除门禁", "删除门禁及其全部评估记录？") != QMessageBox.StandardButton.Yes:
            return
        self._store.delete_gate(self._current_gate_id)
        self._current_gate_id = ""
        self.refresh()

    def _evaluate_gate(self) -> None:
        gate = self._gate()
        if gate is None:
            return
        value = VerificationDialog("评估质量门禁", True, self)
        if value.exec() != QDialog.DialogCode.Accepted:
            return
        self._store.evaluate_gate(
            gate.gate_id,
            version_label=value.version_label(),
            version_id=value.version_id(),
            state=value.state(),
            evidence_summary=value.evidence(),
        )
        self.refresh()

    def _task(self):
        return next(
            (item for item in self._store.state.tasks if item.task_id == self._current_task_id),
            None,
        )

    def _gate(self):
        return next(
            (item for item in self._store.state.gates if item.gate_id == self._current_gate_id),
            None,
        )

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出审阅中心", "GATalk_审阅中心.json", "JSON (*.json)"
        )
        if path:
            self._store.export(path)
            self.statusBar().showMessage("审阅中心已导出。", 4000)

    def _backup(self) -> None:
        path = self._store.backup()
        self.statusBar().showMessage(f"备份已保存：{path}", 5000)

    def closeEvent(self, event) -> None:
        if self._owns_store:
            self._store.close()
        super().closeEvent(event)

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))


class DependencyDialog(QDialog):
    def __init__(
        self,
        tasks,
        current_task_id: str,
        selected_ids: tuple[str, ...],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置前置任务")
        self.resize(620, 480)
        layout = QVBoxLayout(self)
        note = QLabel(
            "当前任务在所选前置任务完成前保持“受阻”。依赖只表达执行顺序，"
            "不会自动修改任务状态。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list = QListWidget()
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        selected = set(selected_ids)
        for task in tasks:
            if task.task_id == current_task_id:
                continue
            row = QListWidgetItem(
                f"{task.title}  ·  {STATUS_LABELS.get(task.status, task.status)}"
            )
            row.setData(Qt.ItemDataRole.UserRole, task.task_id)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(
                Qt.CheckState.Checked
                if task.task_id in selected
                else Qt.CheckState.Unchecked
            )
            self.list.addItem(row)
        layout.addWidget(self.list, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_ids(self) -> tuple[str, ...]:
        return tuple(
            str(row.data(Qt.ItemDataRole.UserRole))
            for row in (
                self.list.item(index) for index in range(self.list.count())
            )
            if row.checkState() == Qt.CheckState.Checked
        )


class VerificationDialog(QDialog):
    def __init__(self, title: str, gate_mode: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.version = QLineEdit()
        self.version.setPlaceholderText("例如：UE 截图 v07")
        self.identifier = QLineEdit()
        self.state_combo = QComboBox()
        values = GATE_STATES[1:] if gate_mode else VERIFICATION_STATES
        labels = GATE_LABELS if gate_mode else VERIFICATION_LABELS
        for value in values:
            self.state_combo.addItem(labels[value], value)
        form.addRow("版本", self.version)
        form.addRow("版本 ID（可选）", self.identifier)
        form.addRow("结果", self.state_combo)
        layout.addLayout(form)
        layout.addWidget(QLabel("复查证据"))
        self.evidence_edit = QPlainTextEdit()
        self.evidence_edit.setPlaceholderText("记录画面、测量或人工检查依据。")
        layout.addWidget(self.evidence_edit)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("补充说明（可选）")
        self.notes_edit.setMaximumHeight(80)
        if not gate_mode:
            layout.addWidget(self.notes_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if not self.version.text().strip() or not self.evidence_edit.toPlainText().strip():
            self.setWindowTitle(self.windowTitle().split(" — ")[0] + " — 请填写版本和证据")
            return
        self.accept()

    def version_label(self) -> str:
        return self.version.text().strip()

    def version_id(self) -> str:
        return self.identifier.text().strip()

    def state(self) -> str:
        return str(self.state_combo.currentData())

    def evidence(self) -> str:
        return self.evidence_edit.toPlainText().strip()

    def notes(self) -> str:
        return self.notes_edit.toPlainText().strip()
