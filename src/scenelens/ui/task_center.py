from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from scenelens.core.runtime_tasks import RuntimeTaskStatus, runtime_task_center
from scenelens.providers.contracts import ProviderCapability
from scenelens.providers.credentials import WindowsCredentialStore
from scenelens.providers.factory import create_default_provider_registry


STATUS_LABELS = {
    RuntimeTaskStatus.QUEUED: "排队中",
    RuntimeTaskStatus.RUNNING: "进行中",
    RuntimeTaskStatus.COMPLETED: "已完成",
    RuntimeTaskStatus.PARTIAL: "部分完成",
    RuntimeTaskStatus.FAILED: "失败",
    RuntimeTaskStatus.CANCELLED: "已取消",
    RuntimeTaskStatus.INTERRUPTED: "上次退出时中断",
}


class TaskCenterDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GATalk 任务与供应商状态")
        self.resize(980, 650)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_tasks_tab(), "后台任务")
        tabs.addTab(self._build_providers_tab(), "AI 供应商")
        layout.addWidget(tabs)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_tasks)
        self.timer.start(1000)
        self.refresh_tasks()

    def _build_tasks_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        notice = QLabel(
            "这里记录 AI 审阅和图片生成的状态、模型、重试次数与失败原因。"
            "不会保存 API Key、图片字节或完整请求正文。"
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.task_table = QTableWidget(0, 7)
        self.task_table.setHorizontalHeaderLabels(
            ("任务", "状态", "供应商", "模型", "进度", "重试", "更新时间")
        )
        self.task_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.task_table.itemSelectionChanged.connect(self._show_task_detail)
        self.task_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.task_table, 1)
        self.task_detail = QPlainTextEdit()
        self.task_detail.setReadOnly(True)
        self.task_detail.setMaximumHeight(150)
        layout.addWidget(self.task_detail)
        row = QHBoxLayout()
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.clicked.connect(self._cancel_selected)
        row.addWidget(self.cancel_button)
        row.addStretch(1)
        clear = QPushButton("清除已结束记录")
        clear.clicked.connect(self._clear_finished)
        row.addWidget(clear)
        layout.addLayout(row)
        return panel

    def _build_providers_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        notice = QLabel(
            "“配置就绪”只表示适配器、模型清单和系统凭据可用，不代表网络、额度"
            "或远端模型当前一定可用。联网验证仍在具体任务发送前由用户主动触发。"
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(
            ("供应商", "能力", "默认模型", "凭据", "本地配置")
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        registry = create_default_provider_registry()
        credentials = WindowsCredentialStore()
        manifests = registry.manifests()
        table.setRowCount(len(manifests))
        for row, manifest in enumerate(manifests):
            capabilities = "、".join(
                {
                    ProviderCapability.VISION_REVIEW: "视觉审阅",
                    ProviderCapability.STRUCTURED_OUTPUT: "结构化文本",
                    ProviderCapability.IMAGE_EDIT: "图片生成",
                }[capability]
                for capability in manifest.capabilities
            )
            default_models = "；".join(
                f"{key}: {value}" for key, value in manifest.default_models.items()
            )
            try:
                present = bool(credentials.get(manifest.credential_target))
            except OSError:
                present = False
            values = (
                manifest.display_name,
                capabilities,
                default_models,
                "不需要" if manifest.provider_id == "mock" else ("已保存" if present else "未保存"),
                "配置就绪",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                table.setItem(row, column, cell)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        return panel

    def refresh_tasks(self) -> None:
        tasks = runtime_task_center().tasks()
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            progress = (
                f"{task.progress_current}/{task.progress_total}"
                if task.progress_total
                else "—"
            )
            values = (
                task.title,
                STATUS_LABELS[task.status],
                task.provider_id or "—",
                task.model_id or "—",
                progress,
                f"{task.attempt}/{task.max_attempts}" if task.max_attempts else "—",
                task.updated_at,
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, task.task_id)
                self.task_table.setItem(row, column, cell)
        self.task_table.resizeColumnsToContents()

    def _selected_task_id(self) -> str | None:
        rows = self.task_table.selectionModel().selectedRows()
        if not rows:
            return None
        return str(
            self.task_table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        )

    def _show_task_detail(self) -> None:
        task_id = self._selected_task_id()
        task = next(
            (item for item in runtime_task_center().tasks() if item.task_id == task_id),
            None,
        )
        if task is None:
            self.task_detail.clear()
            self.cancel_button.setEnabled(False)
            return
        lines = [
            f"任务类型：{task.task_type}",
            f"模块：{task.module_id}",
            f"输入摘要：{dict(task.input_summary or {})}",
        ]
        if task.public_error:
            lines.append(f"用户提示：{task.public_error}")
        if task.technical_error:
            lines.append(f"技术详情：{task.technical_error}")
        if task.output_location:
            lines.append(f"输出位置：{task.output_location}")
        self.task_detail.setPlainText("\n".join(lines))
        self.cancel_button.setEnabled(task.can_cancel)

    def _cancel_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            runtime_task_center().cancel(task_id)
            self.refresh_tasks()

    def _clear_finished(self) -> None:
        runtime_task_center().clear_finished()
        self.refresh_tasks()

