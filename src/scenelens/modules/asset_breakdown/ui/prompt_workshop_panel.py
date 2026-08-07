from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from scenelens.modules.asset_breakdown.models import (
    AssetPromptSession,
    PromptRevision,
)


class AssetPromptWorkshopPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        intro = QLabel(
            "根据当前场景理解和拆分方案编写外部生图指令。指令可继续修订、"
            "手动编辑和复制；本页不调用图片生成服务。"
        )
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.basis_label = QLabel("运行依据：未打开项目。")
        self.basis_label.setObjectName("workflowBasis")
        self.basis_label.setWordWrap(True)
        layout.addWidget(self.basis_label)

        settings = QGroupBox("模型与会话")
        form = QFormLayout(settings)
        self.provider_combo = QComboBox()
        self.model_edit = QLineEdit()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.save_key_button = QPushButton("存入系统凭据")
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.key_edit, 1)
        key_layout.addWidget(self.save_key_button)

        self.target_tool_combo = QComboBox()
        self.target_tool_combo.setEditable(True)
        for label, value in (
            ("通用图像生成器", "generic"),
            ("Gemini / Nano Banana", "nano_banana"),
            ("Midjourney", "midjourney"),
            ("Stable Diffusion / Flux", "sd_flux"),
            ("即梦 / 可灵等中文生图工具", "cn_image_tools"),
        ):
            self.target_tool_combo.addItem(label, value)

        self.session_combo = QComboBox()
        self.new_session_button = QPushButton("新建会话")
        session_row = QWidget()
        session_layout = QHBoxLayout(session_row)
        session_layout.setContentsMargins(0, 0, 0, 0)
        session_layout.addWidget(self.session_combo, 1)
        session_layout.addWidget(self.new_session_button)

        form.addRow("AI 供应商", self.provider_combo)
        form.addRow("模型 ID", self.model_edit)
        form.addRow("API Key", key_row)
        form.addRow("目标工具", self.target_tool_combo)
        form.addRow("版本会话", session_row)

        self.initial_button = QPushButton("检查发送内容并生成初稿")
        self.initial_button.setProperty("primary", True)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addWidget(self.initial_button, 1)
        button_layout.addWidget(self.cancel_button)
        form.addRow(button_row)
        layout.addWidget(settings)

        self.status_label = QLabel("状态：未生成")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        conversation = QGroupBox("修订记录")
        conversation_layout = QVBoxLayout(conversation)
        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(100)
        conversation_layout.addWidget(self.history_list)
        splitter.addWidget(conversation)

        editor = QGroupBox("当前版本")
        editor_layout = QVBoxLayout(editor)
        self.revision_label = QLabel("未选择版本")
        editor_layout.addWidget(self.revision_label)
        self.revision_combo = QComboBox()
        self.revision_combo.currentIndexChanged.connect(
            self._revision_changed
        )
        editor_layout.addWidget(self.revision_combo)
        self.editor_tabs = QTabWidget()
        self.prompt_zh_edit = QPlainTextEdit()
        self.prompt_en_edit = QPlainTextEdit()
        self.negative_edit = QPlainTextEdit()
        self.constraints_edit = QPlainTextEdit()
        self.analysis_edit = QPlainTextEdit()
        self.analysis_edit.setReadOnly(True)
        self.asset_groups_edit = QPlainTextEdit()
        self.asset_groups_edit.setReadOnly(True)
        self.editor_tabs.addTab(self.prompt_zh_edit, "中文提示语")
        self.editor_tabs.addTab(self.prompt_en_edit, "英文提示语")
        self.editor_tabs.addTab(self.negative_edit, "负面提示")
        self.editor_tabs.addTab(self.constraints_edit, "硬约束")
        self.editor_tabs.addTab(self.analysis_edit, "图片理解")
        self.editor_tabs.addTab(self.asset_groups_edit, "资产组依据")
        editor_layout.addWidget(self.editor_tabs, 1)

        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.save_manual_button = QPushButton("保存手动修改")
        self.copy_zh_button = QPushButton("复制中文")
        self.copy_en_button = QPushButton("复制英文")
        self.copy_all_button = QPushButton("复制完整提示语")
        for button in (
            self.save_manual_button,
            self.copy_zh_button,
            self.copy_en_button,
            self.copy_all_button,
        ):
            action_layout.addWidget(button)
        editor_layout.addWidget(action_row)
        splitter.addWidget(editor)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        refine = QGroupBox("提交修订意见")
        refine_layout = QVBoxLayout(refine)
        hint = QLabel(
            "示例：减少次要道具；把建筑拆到生产套件；不补全不可见背面；"
            "按 Midjourney 的语法压缩指令。"
        )
        hint.setWordWrap(True)
        refine_layout.addWidget(hint)
        self.feedback_edit = QPlainTextEdit()
        self.feedback_edit.setMaximumHeight(92)
        refine_layout.addWidget(self.feedback_edit)
        self.resend_image_check = QCheckBox(
            "本次迭代重新附带原画（更耗流量和视觉模型额度）"
        )
        self.resend_image_check.setChecked(False)
        refine_layout.addWidget(self.resend_image_check)
        self.iterate_button = QPushButton("检查发送内容并生成新版本")
        self.iterate_button.setProperty("primary", True)
        refine_layout.addWidget(self.iterate_button)
        layout.addWidget(refine)
        self._session: AssetPromptSession | None = None
        self.set_prompt_actions_enabled(False)

    def set_busy(self, busy: bool) -> None:
        self.initial_button.setEnabled(not busy)
        self.iterate_button.setEnabled(
            not busy and self.save_manual_button.isEnabled()
        )
        self.cancel_button.setEnabled(busy)

    def set_prompt_actions_enabled(self, enabled: bool) -> None:
        for widget in (
            self.save_manual_button,
            self.copy_zh_button,
            self.copy_en_button,
            self.copy_all_button,
            self.iterate_button,
        ):
            widget.setEnabled(enabled)

    def clear_prompt(self) -> None:
        self._session = None
        self.history_list.clear()
        self.revision_combo.clear()
        for editor in (
            self.prompt_zh_edit,
            self.prompt_en_edit,
            self.negative_edit,
            self.constraints_edit,
            self.analysis_edit,
            self.asset_groups_edit,
            self.feedback_edit,
        ):
            editor.clear()
        self.revision_label.setText("未选择版本")
        self.status_label.setText("状态：未生成")
        self.set_prompt_actions_enabled(False)

    def load_session(self, session: AssetPromptSession | None) -> None:
        if session is None or session.current_revision is None:
            self.clear_prompt()
            return
        self._session = session
        self.revision_combo.blockSignals(True)
        self.revision_combo.clear()
        for index, item in enumerate(session.revisions, start=1):
            origin = "AI" if item.origin == "ai" else "手动"
            self.revision_combo.addItem(
                f"第 {index} 版｜{origin}｜{item.created_at}",
                item.revision_id,
            )
        self.revision_combo.setCurrentIndex(
            self.revision_combo.count() - 1
        )
        self.revision_combo.blockSignals(False)
        self._load_revision(
            session.current_revision,
            len(session.revisions),
        )
        self.history_list.clear()
        for message in session.messages:
            prefix = "修订要求" if message.role == "user" else "处理记录"
            self.history_list.addItem(f"{prefix}：{message.content}")
        if self.history_list.count():
            self.history_list.scrollToBottom()
        self.status_label.setText(
            f"状态：已保存 {len(session.revisions)} 个版本"
        )
        self.set_prompt_actions_enabled(True)

    def _load_revision(
        self,
        revision: PromptRevision,
        display_number: int,
    ) -> None:
        tool_index = self.target_tool_combo.findData(revision.target_tool)
        if tool_index >= 0:
            self.target_tool_combo.setCurrentIndex(tool_index)
        else:
            self.target_tool_combo.setEditText(revision.target_tool)
        self.prompt_zh_edit.setPlainText(revision.prompt_zh)
        self.prompt_en_edit.setPlainText(revision.prompt_en)
        self.negative_edit.setPlainText(revision.negative_prompt)
        self.constraints_edit.setPlainText("\n".join(revision.constraints))
        self.analysis_edit.setPlainText(revision.analysis_summary)
        self.asset_groups_edit.setPlainText(
            "\n\n".join(
                (
                    f"{index}. {item.get('name', '')}"
                    f"｜{item.get('category', '')}\n"
                    f"可见证据：{item.get('visible_evidence', '')}\n"
                    f"不确定性：{item.get('uncertainty', '')}"
                )
                for index, item in enumerate(
                    revision.asset_groups,
                    start=1,
                )
            )
        )
        origin = "模型生成" if revision.origin == "ai" else "手动修订"
        self.revision_label.setText(
            f"{revision.title}｜第 {display_number} 版｜{origin}"
        )

    def set_basis(self, text: str, *, stale: bool = False) -> None:
        self.basis_label.setText(text)
        self.basis_label.setProperty("tone", "warning" if stale else "success")
        self.basis_label.style().unpolish(self.basis_label)
        self.basis_label.style().polish(self.basis_label)

    def _revision_changed(self, index: int) -> None:
        if (
            self._session is None
            or index < 0
            or index >= len(self._session.revisions)
        ):
            return
        self._load_revision(self._session.revisions[index], index + 1)

    def selected_revision(self) -> PromptRevision | None:
        if self._session is None:
            return None
        index = self.revision_combo.currentIndex()
        if index < 0 or index >= len(self._session.revisions):
            return self._session.current_revision
        return self._session.revisions[index]

    def constraints(self) -> tuple[str, ...]:
        return tuple(
            line.strip()
            for line in self.constraints_edit.toPlainText().splitlines()
            if line.strip()
        )

    def complete_prompt_text(self) -> str:
        constraints = "\n".join(
            f"- {item}" for item in self.constraints()
        )
        return (
            "【中文提示语】\n"
            f"{self.prompt_zh_edit.toPlainText().strip()}\n\n"
            "【英文提示语】\n"
            f"{self.prompt_en_edit.toPlainText().strip()}\n\n"
            "【负面提示】\n"
            f"{self.negative_edit.toPlainText().strip()}\n\n"
            "【必须保持】\n"
            f"{constraints}"
        ).strip()
