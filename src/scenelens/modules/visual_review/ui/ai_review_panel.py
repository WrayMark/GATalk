from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scenelens.modules.visual_review.review_coordinator import (
    ReviewRunOptions,
    ReviewRunOutcome,
)
from scenelens.providers.contracts import (
    DataDisclosurePreview,
    ProviderCapability,
    ProviderManifest,
)


@dataclass(frozen=True)
class ReviewPanelOptions:
    run: ReviewRunOptions
    remove_metadata: bool
    maximum_side: int | None


class DataDisclosureDialog(QDialog):
    def __init__(
        self,
        preview: DataDisclosurePreview,
        *,
        second_opinion: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("确认发送数据")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        warning = QLabel(
            "SceneLens 不会自动上传。继续后，下列数据将发送给所选供应商；"
            "商业保密内容是否允许上传由你的团队政策决定。"
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        layout.addWidget(
            QLabel(
                f"供应商：{preview.provider_id}\n模型：{preview.model_id}\n"
                f"结构化字段：{', '.join(preview.payload_fields)}"
            )
        )
        images = QListWidget()
        for image in preview.images:
            images.addItem(
                f"{image.role} · {image.media_type} · "
                f"{image.byte_size / 1024:.1f} KiB · "
                f"SHA-256 {image.sha256[:12]}…"
            )
        layout.addWidget(images)
        if second_opinion:
            cost = QLabel("第二意见已开启：会产生一次额外模型调用和费用。")
            cost.setStyleSheet("color: #E6B450; font-weight: 600;")
            layout.addWidget(cost)
        if preview.provider_id == "google_gemini":
            repair_notice = QLabel(
                "Gemini 若首次返回的 JSON 语法损坏、被截断或结构不完整，"
                "SceneLens 最多会自动执行一次结构纠错；可能再次发送同一"
                "审阅副本并增加少量费用。"
            )
            repair_notice.setWordWrap(True)
            repair_notice.setStyleSheet("color: #E6B450;")
            layout.addWidget(repair_notice)
        retry_notice = QLabel(
            "临时断线、超时或服务繁忙时最多自动尝试 3 次。极少数情况下，"
            "重复提交可能产生额外调用费用。"
        )
        retry_notice.setWordWrap(True)
        retry_notice.setStyleSheet("color: #E6B450;")
        layout.addWidget(retry_notice)
        if preview.fallback_model_ids:
            fallback_notice = QLabel(
                "若当前模型重试后仍返回 503 容量不足，将在同一供应商内"
                f"改用备用模型 {preview.fallback_model_ids[0]} 再发送一次。"
                "不会跨供应商；结果会记录实际模型，可能增加一次调用费用。"
            )
            fallback_notice.setWordWrap(True)
            fallback_notice.setStyleSheet("color: #E6B450;")
            layout.addWidget(fallback_notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "确认并发送"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AIReviewPanel(QWidget):
    review_requested = Signal(object)
    cancel_requested = Signal()
    credential_save_requested = Signal(str, str)
    credential_delete_requested = Signal(str)
    task_requested = Signal(object)
    annotations_selected = Signal(object)
    annotation_tasks_requested = Signal(object)
    offline_export_requested = Signal()

    def __init__(
        self,
        manifests: Sequence[ProviderManifest],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manifests = {
            manifest.provider_id: manifest for manifest in manifests
        }
        self._findings: list[Mapping[str, Any]] = []
        self._dimension_reviews: list[Mapping[str, Any]] = []
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)

        provider_group = QGroupBox("专项审阅")
        form = QFormLayout(provider_group)
        self.reviewer_combo = QComboBox()
        self.reviewer_combo.addItem(
            "深度主美审阅（八维）",
            "deep_art_director_review",
        )
        self.reviewer_combo.addItem("主美专项审阅", "art_director_review")
        self.reviewer_combo.addItem("灯光专项审阅", "lighting_review")
        form.addRow("审阅器", self.reviewer_combo)

        self.provider_combo = QComboBox()
        self.second_provider_combo = QComboBox()
        vision = [
            manifest
            for manifest in manifests
            if ProviderCapability.VISION_REVIEW in manifest.capabilities
        ]
        vision.sort(
            key=lambda item: (
                item.mainland_priority,
                item.display_name,
            )
        )
        for manifest in vision:
            self.provider_combo.addItem(
                manifest.display_name, manifest.provider_id
            )
            self.second_provider_combo.addItem(
                manifest.display_name, manifest.provider_id
            )
        form.addRow("主供应商", self.provider_combo)

        self.model_edit = QLineEdit()
        form.addRow("模型 ID", self.model_edit)

        credential_row = QWidget()
        credential_layout = QHBoxLayout(credential_row)
        credential_layout.setContentsMargins(0, 0, 0, 0)
        self.credential_edit = QLineEdit()
        self.credential_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.credential_edit.setPlaceholderText("不会写入项目或日志")
        credential_layout.addWidget(self.credential_edit, 1)
        self.save_credential_button = QPushButton("存入系统凭据")
        self.delete_credential_button = QPushButton("删除")
        credential_layout.addWidget(self.save_credential_button)
        credential_layout.addWidget(self.delete_credential_button)
        form.addRow("API Key", credential_row)

        self.second_opinion_checkbox = QCheckBox(
            "第二意见（额外调用，只审查证据与遗漏）"
        )
        form.addRow("", self.second_opinion_checkbox)
        self.second_provider_combo.setEnabled(False)
        form.addRow("第二供应商", self.second_provider_combo)
        self.cost_warning = QLabel("开启后会产生额外费用。")
        self.cost_warning.setStyleSheet("color: #E6B450;")
        self.cost_warning.hide()
        form.addRow("", self.cost_warning)
        layout.addWidget(provider_group)

        privacy_group = QGroupBox("发送副本")
        privacy_layout = QFormLayout(privacy_group)
        self.remove_metadata_checkbox = QCheckBox(
            "移除 EXIF、ICC 和其他元数据"
        )
        self.remove_metadata_checkbox.setChecked(True)
        privacy_layout.addRow("", self.remove_metadata_checkbox)
        self.maximum_side_combo = QComboBox()
        self.maximum_side_combo.addItem("最长边 1280 px", 1280)
        self.maximum_side_combo.addItem("最长边 2048 px", 2048)
        self.maximum_side_combo.addItem("最长边 4096 px", 4096)
        self.maximum_side_combo.addItem("原始尺寸", None)
        self.maximum_side_combo.setCurrentIndex(1)
        privacy_layout.addRow("分辨率", self.maximum_side_combo)
        layout.addWidget(privacy_group)

        buttons = QHBoxLayout()
        self.run_button = QPushButton("查看发送清单并审阅")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        self.export_button = QPushButton("导出离线审阅包")
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.export_button)
        layout.addLayout(buttons)

        self.status_label = QLabel("未运行。Mock 可在无 API Key 时离线验证流程。")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        result_group = QGroupBox("审阅结果")
        result_layout = QVBoxLayout(result_group)
        self.summary_label = QLabel("尚无结果")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(
            self.summary_label.textInteractionFlags()
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        result_layout.addWidget(self.summary_label)
        self.target_readback_label = QLabel()
        self.target_readback_label.setWordWrap(True)
        self.target_readback_label.hide()
        result_layout.addWidget(self.target_readback_label)

        self.dimension_tree = QTreeWidget()
        self.dimension_tree.setHeaderLabels(
            ["审阅维度", "状态", "证据摘要", "可信度"]
        )
        self.dimension_tree.setRootIsDecorated(False)
        self.dimension_tree.setMinimumHeight(190)
        self.dimension_tree.hide()
        result_layout.addWidget(self.dimension_tree)
        self.dimension_detail = QLabel("选择一个维度查看制作目标、参考呈现和当前效果。")
        self.dimension_detail.setWordWrap(True)
        self.dimension_detail.setTextInteractionFlags(
            self.dimension_detail.textInteractionFlags()
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        result_layout.addWidget(self.dimension_detail)

        self.findings_tree = QTreeWidget()
        self.findings_tree.setHeaderLabels(
            ["优先级", "核心问题", "第二意见", "关联维度", "本地证据"]
        )
        self.findings_tree.setRootIsDecorated(False)
        result_layout.addWidget(self.findings_tree)
        self.validation_list = QListWidget()
        self.validation_list.setToolTip(
            "AI 可测量结论与本地像素测量的校验结果；冲突不会被隐藏。"
        )
        result_layout.addWidget(self.validation_list)

        self.action_plan_list = QListWidget()
        self.action_plan_list.setToolTip("按依赖关系排序的执行计划")
        self.action_plan_list.hide()
        self.action_plan_heading = QLabel("执行顺序")
        self.action_plan_heading.hide()
        result_layout.addWidget(self.action_plan_heading)
        result_layout.addWidget(self.action_plan_list)
        self.preserve_list = QListWidget()
        self.preserve_list.setToolTip("修改时应避免破坏的现有优点")
        self.preserve_list.hide()
        self.preserve_heading = QLabel("需要保留")
        self.preserve_heading.hide()
        result_layout.addWidget(self.preserve_heading)
        result_layout.addWidget(self.preserve_list)
        self.confidence_list = QListWidget()
        self.confidence_list.setToolTip("证据不足、输入限制和可信度说明")
        self.confidence_list.hide()
        self.confidence_heading = QLabel("可信度与限制")
        self.confidence_heading.hide()
        result_layout.addWidget(self.confidence_heading)
        result_layout.addWidget(self.confidence_list)
        self.create_task_button = QPushButton("将选中问题确认为修改任务")
        self.create_task_button.setEnabled(False)
        result_layout.addWidget(self.create_task_button)
        self.scheme_combo = QComboBox()
        self.scheme_combo.setPlaceholderText("灯光方案标注")
        result_layout.addWidget(self.scheme_combo)
        self.annotation_task_button = QPushButton(
            "将当前方案标注确认为任务"
        )
        self.annotation_task_button.setEnabled(False)
        result_layout.addWidget(self.annotation_task_button)
        layout.addWidget(result_group)

        scroll.setWidget(body)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self.provider_combo.currentIndexChanged.connect(
            self._provider_changed
        )
        self.second_opinion_checkbox.toggled.connect(
            self._second_opinion_toggled
        )
        self.save_credential_button.clicked.connect(
            self._save_credential
        )
        self.delete_credential_button.clicked.connect(
            lambda: self.credential_delete_requested.emit(
                str(self.provider_combo.currentData())
            )
        )
        self.run_button.clicked.connect(
            lambda: self.review_requested.emit(self.options())
        )
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.export_button.clicked.connect(self.offline_export_requested)
        self.findings_tree.currentItemChanged.connect(
            lambda *_: self.create_task_button.setEnabled(
                self.findings_tree.currentIndex().isValid()
            )
        )
        self.dimension_tree.currentItemChanged.connect(
            self._dimension_selected
        )
        self.create_task_button.clicked.connect(self._request_task)
        self.scheme_combo.currentIndexChanged.connect(
            self._scheme_changed
        )
        self.annotation_task_button.clicked.connect(
            self._request_annotation_tasks
        )
        self._provider_changed()

    def options(self) -> ReviewPanelOptions:
        second_provider = (
            str(self.second_provider_combo.currentData())
            if self.second_opinion_checkbox.isChecked()
            else None
        )
        return ReviewPanelOptions(
            run=ReviewRunOptions(
                reviewer_id=str(self.reviewer_combo.currentData()),
                provider_id=str(self.provider_combo.currentData()),
                model_id=self.model_edit.text().strip() or None,
                second_opinion_provider_id=second_provider,
            ),
            remove_metadata=self.remove_metadata_checkbox.isChecked(),
            maximum_side=self.maximum_side_combo.currentData(),
        )

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.status_label.setText(
            "正在后台执行审阅…" if running else self.status_label.text()
        )

    def show_outcome(self, outcome: ReviewRunOutcome) -> None:
        self.set_running(False)
        self._findings = [
            dict(item.finding) for item in outcome.merged_findings
        ]
        summary = outcome.output.get(
            "executive_summary",
            outcome.output.get("summary", ""),
        )
        self.summary_label.setText(str(summary))
        target_value = outcome.output.get("target_readback", "")
        if isinstance(target_value, Mapping):
            target = "；".join(
                f"{label}：{target_value.get(key, '')}"
                for key, label in (
                    ("production_stage", "阶段"),
                    ("target_style", "风格"),
                    ("target_mood", "情绪"),
                    ("primary_focus", "第一焦点"),
                )
                if target_value.get(key)
            )
        else:
            target = str(target_value).strip()
        self.target_readback_label.setText(
            f"本次目标：{target}" if target else ""
        )
        self.target_readback_label.setVisible(bool(target))

        self._dimension_reviews = [
            dict(item)
            for item in outcome.output.get("dimension_reviews", [])
        ]
        self.dimension_tree.clear()
        dimension_labels = {
            "composition": "构图结构",
            "visual_guidance": "视觉引导",
            "focus_hierarchy": "焦点层级",
            "colour_design": "色彩设计",
            "value_structure": "明度结构",
            "lighting_atmosphere": "灯光与氛围",
            "material_readability": "材质可读性",
            "world_design_narrative": "世界设计与叙事",
        }
        status_labels = {
            "meets_target": "符合目标",
            "partially_meets": "部分符合",
            "deviates": "偏离目标",
            "insufficient_evidence": "证据不足",
        }
        for index, dimension in enumerate(self._dimension_reviews):
            item = QTreeWidgetItem(
                [
                    dimension_labels.get(
                        str(dimension.get("dimension_id", "")),
                        str(dimension.get("dimension_id", "")),
                    ),
                    status_labels.get(
                        str(dimension.get("status", "")),
                        str(dimension.get("status", "")),
                    ),
                    "；".join(
                        str(value)
                        for value in dimension.get(
                            "evidence_summary",
                            [],
                        )
                    ),
                    f"{float(dimension.get('confidence', 0.0)):.2f}",
                ]
            )
            item.setData(0, 0x0100, index)
            self.dimension_tree.addTopLevelItem(item)
        for column in (0, 1, 3):
            self.dimension_tree.resizeColumnToContents(column)
        self.dimension_detail.setVisible(bool(self._dimension_reviews))
        self.dimension_tree.setVisible(bool(self._dimension_reviews))
        if self._dimension_reviews:
            self.dimension_tree.setCurrentItem(
                self.dimension_tree.topLevelItem(0)
            )

        validations_by_id = {
            item.claim_id: item for item in outcome.component_validations
        }
        evidence_status_labels = {
            "supported": "测量支持",
            "partially_supported": "部分支持",
            "conflict": "存在冲突",
            "unverifiable": "无法验证",
        }
        severity = {
            "conflict": 3,
            "partially_supported": 2,
            "unverifiable": 1,
            "supported": 0,
        }
        self.findings_tree.clear()
        for index, merged in enumerate(outcome.merged_findings):
            finding = merged.finding
            finding_validations = [
                validations_by_id[str(claim.get("claim_id", ""))]
                for claim in finding.get("evidence_claims", [])
                if str(claim.get("claim_id", "")) in validations_by_id
            ]
            worst_validation = (
                max(
                    finding_validations,
                    key=lambda item: severity.get(item.status.value, 0),
                )
                if finding_validations
                else None
            )
            item = QTreeWidgetItem(
                [
                    str(finding.get("priority", "")),
                    str(finding.get("observation", "")),
                    merged.second_opinion_status or "未启用",
                    "、".join(
                        dimension_labels.get(str(value), str(value))
                        for value in finding.get("dimension_ids", [])
                    ),
                    (
                        evidence_status_labels.get(
                            worst_validation.status.value,
                            worst_validation.status.value,
                        )
                        if worst_validation is not None
                        else "未声明可测结论"
                    ),
                ]
            )
            item.setData(0, 0x0100, index)
            if merged.disagreement:
                item.setToolTip(2, merged.disagreement)
            if worst_validation is not None:
                item.setToolTip(4, worst_validation.reason)
            self.findings_tree.addTopLevelItem(item)
        self.findings_tree.resizeColumnToContents(0)
        self.validation_list.clear()
        for validation in outcome.component_validations:
            value = (
                "无"
                if validation.measured_value is None
                else f"{validation.measured_value:.4f}"
            )
            self.validation_list.addItem(
                f"{validation.claim_id} · {validation.status.value} · "
                f"测量 {value} · 可信度 "
                f"{validation.adjusted_confidence:.2f} · "
                f"{validation.reason}"
            )
        for omission in outcome.omissions:
            self.validation_list.addItem(f"第二意见遗漏提示：{omission}")
        for warning in outcome.normalization_warnings:
            self.validation_list.addItem(f"结构修复：{warning}")

        self.action_plan_list.clear()
        for action in sorted(
            outcome.output.get("action_plan", []),
            key=lambda value: int(value.get("order", 0)),
        ):
            ue_steps = "；".join(
                str(value) for value in action.get("ue5_steps", [])
            )
            text = (
                f"{action.get('order', '-')}．{action.get('action', '')}"
            )
            if ue_steps:
                text += f"｜UE：{ue_steps}"
            self.action_plan_list.addItem(text)
        has_actions = self.action_plan_list.count() > 0
        self.action_plan_list.setVisible(has_actions)
        self.action_plan_heading.setVisible(has_actions)

        self.preserve_list.clear()
        for value in outcome.output.get("preserve_items", []):
            self.preserve_list.addItem(str(value))
        has_preserve = self.preserve_list.count() > 0
        self.preserve_list.setVisible(has_preserve)
        self.preserve_heading.setVisible(has_preserve)

        self.confidence_list.clear()
        for value in outcome.output.get("confidence_notes", []):
            self.confidence_list.addItem(str(value))
        has_confidence = self.confidence_list.count() > 0
        self.confidence_list.setVisible(has_confidence)
        self.confidence_heading.setVisible(has_confidence)
        self.scheme_combo.blockSignals(True)
        self.scheme_combo.clear()
        labels = {
            "faithful_to_reference": "忠于参考",
            "heightened_drama": "强化戏剧性",
            "gameplay_readability": "优先游戏可读性",
        }
        for scheme in outcome.output.get("target_schemes", []):
            self.scheme_combo.addItem(
                labels.get(
                    str(scheme.get("strategy", "")),
                    str(scheme.get("strategy", "")),
                ),
                dict(scheme),
            )
        if self.scheme_combo.count():
            self.scheme_combo.setCurrentIndex(0)
        self.scheme_combo.blockSignals(False)
        self.annotation_task_button.setEnabled(
            self.scheme_combo.count() > 0
        )
        self._scheme_changed(self.scheme_combo.currentIndex())
        fallback_note = (
            f"（原模型 {outcome.requested_model_id} 容量不足，"
            "已自动回退）"
            if outcome.model_fallback_used
            else ""
        )
        self.status_label.setText(
            f"完成：{outcome.provider_id} / {outcome.model_id}"
            f"{fallback_note}。"
        )

    def show_error(self, message: str) -> None:
        self.set_running(False)
        self.status_label.setText(f"审阅失败：{message}")

    def show_tasks(self, tasks: Sequence[Any]) -> None:
        suffix = f" · 已保存任务 {len(tasks)} 项" if tasks else ""
        if suffix and suffix not in self.status_label.text():
            self.status_label.setText(self.status_label.text() + suffix)

    def _provider_changed(self, _index: int = -1) -> None:
        provider_id = str(self.provider_combo.currentData() or "")
        manifest = self._manifests.get(provider_id)
        if manifest is None:
            return
        self.model_edit.setText(
            manifest.default_models.get("vision_review", "")
        )
        is_mock = provider_id == "mock"
        self.credential_edit.setEnabled(not is_mock)
        self.save_credential_button.setEnabled(not is_mock)
        self.delete_credential_button.setEnabled(not is_mock)

    def _second_opinion_toggled(self, checked: bool) -> None:
        self.second_provider_combo.setEnabled(checked)
        self.cost_warning.setVisible(checked)

    def _save_credential(self) -> None:
        secret = self.credential_edit.text()
        if not secret:
            QMessageBox.information(self, "API Key", "请输入 API Key。")
            return
        self.credential_save_requested.emit(
            str(self.provider_combo.currentData()),
            secret,
        )
        self.credential_edit.clear()

    def _request_task(self) -> None:
        item = self.findings_tree.currentItem()
        if item is None:
            return
        index = int(item.data(0, 0x0100))
        if 0 <= index < len(self._findings):
            self.task_requested.emit(dict(self._findings[index]))

    def _dimension_selected(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is None:
            return
        index = current.data(0, 0x0100)
        if not isinstance(index, int) or not (
            0 <= index < len(self._dimension_reviews)
        ):
            return
        value = self._dimension_reviews[index]
        strengths = "；".join(
            str(item) for item in value.get("strengths", [])
        ) or "未识别"
        risks = "；".join(
            str(item) for item in value.get("risks", [])
        ) or "未识别"
        self.dimension_detail.setText(
            "制作目标："
            f"{value.get('intent_target', '')}\n"
            "参考呈现："
            f"{value.get('reference_read', '')}\n"
            "当前效果："
            f"{value.get('current_read', '')}\n"
            f"已有优点：{strengths}\n"
            f"风险：{risks}\n"
            "不确定性："
            f"{value.get('uncertainty', '')}"
        )

    def _scheme_changed(self, index: int) -> None:
        scheme = self.scheme_combo.itemData(index)
        if isinstance(scheme, dict):
            self.annotations_selected.emit(dict(scheme))
        else:
            self.annotations_selected.emit({})

    def _request_annotation_tasks(self) -> None:
        scheme = self.scheme_combo.currentData()
        if isinstance(scheme, dict):
            self.annotation_tasks_requested.emit(dict(scheme))
