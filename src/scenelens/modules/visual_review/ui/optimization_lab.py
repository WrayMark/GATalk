from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scenelens.analysis.grading import RecipeHistory, SafeGradeRecipe
from scenelens.analysis.match_profile import (
    DEFAULT_MATCH_WEIGHTS,
    MatchProfile,
)
from scenelens.analysis.preview_validation import PreviewValidation
from scenelens.core.domain import AIConceptPreviewStatus
from scenelens.modules.visual_review.preview_instructions import (
    PreviewEditMode,
    change_budget_semantics,
)
from scenelens.providers.contracts import (
    ProviderCapability,
    ProviderManifest,
)


@dataclass(frozen=True)
class ConceptPreviewOptions:
    provider_id: str
    model_id: str | None
    mode: PreviewEditMode
    change_budget_percent: int
    preserve_composition: bool
    preserve_geometry: bool
    preserve_asset_identity: bool
    remove_metadata: bool
    maximum_side: int | None


_DIMENSION_NAMES = {
    "luminance_structure": "明度结构",
    "three_value_balance": "黑白灰比例",
    "palette_area": "色板和面积关系",
    "chroma_neutral": "彩度与中性色",
    "warm_cool": "冷暖关系",
    "region_relationships": "区域关系",
    "local_contrast": "局部对比",
    "visual_focus": "视觉焦点",
    "lighting_atmosphere": "灯光氛围",
    "spatial_depth": "空间层次",
}


class OptimizationLabPanel(QWidget):
    match_requested = Signal(object)
    safe_preview_requested = Signal(object)
    show_original_requested = Signal(bool)
    grade_export_requested = Signal(str)
    concept_requested = Signal(object)
    concept_cancel_requested = Signal()
    concept_tasks_requested = Signal()
    credential_save_requested = Signal(str, str)
    credential_delete_requested = Signal(str)

    def __init__(
        self,
        manifests: Sequence[ProviderManifest],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manifests = {
            item.provider_id: item for item in manifests
        }
        self._history = RecipeHistory()
        self._history_navigation_pending = False
        self._preview_available = False
        self._concept_available = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(self._build_match_group())
        layout.addWidget(self._build_grade_group())
        layout.addWidget(self._build_concept_group())
        layout.addStretch(1)
        scroll.setWidget(body)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _build_match_group(self) -> QGroupBox:
        group = QGroupBox("目标匹配画像")
        layout = QVBoxLayout(group)
        note = QLabel(
            "“估计匹配度”只表示当前算法、证据和用户权重下的目标符合程度，"
            "不是作品质量评分。缺少证据的维度不会被猜测。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.match_summary = QLabel("尚未计算")
        self.match_summary.setWordWrap(True)
        layout.addWidget(self.match_summary)
        self.match_tree = QTreeWidget()
        self.match_tree.setHeaderLabels(
            ["维度", "估计匹配", "证据来源", "权重"]
        )
        self.match_tree.setRootIsDecorated(False)
        self.match_tree.setMinimumHeight(245)
        layout.addWidget(self.match_tree)

        weights = QFormLayout()
        self.weight_controls: dict[str, QDoubleSpinBox] = {}
        for dimension_id, default in DEFAULT_MATCH_WEIGHTS.items():
            control = QDoubleSpinBox()
            control.setRange(0.0, 3.0)
            control.setSingleStep(0.1)
            control.setDecimals(1)
            control.setValue(default)
            control.setToolTip("0 表示该维度不参与汇总；原始分维度证据仍保留。")
            self.weight_controls[dimension_id] = control
            weights.addRow(_DIMENSION_NAMES[dimension_id], control)
        layout.addLayout(weights)
        refresh = QPushButton("按当前权重重新计算")
        refresh.clicked.connect(
            lambda: self.match_requested.emit(self.match_weights())
        )
        layout.addWidget(refresh)
        return group

    def _build_grade_group(self) -> QGroupBox:
        group = QGroupBox("安全调色（完全本地、严格可复现）")
        layout = QVBoxLayout(group)
        note = QLabel(
            "保持几何且不修改原图。强度是原图与处理结果在线性 sRGB 中的"
            "实际插值比例；区域模式只作用于当前选中的“当前截图”配对区域。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        self.exposure = QDoubleSpinBox()
        self.exposure.setRange(-4.0, 4.0)
        self.exposure.setSingleStep(0.1)
        self.exposure.setSuffix(" EV")
        form.addRow("曝光", self.exposure)

        self.grade_controls: dict[str, QDoubleSpinBox] = {}
        for key, label in (
            ("contrast", "对比"),
            ("temperature", "白平衡 · 色温"),
            ("tint", "白平衡 · 色调"),
            ("shadows", "阴影"),
            ("midtones", "中间调"),
            ("highlights", "亮部"),
            ("saturation", "彩度"),
        ):
            control = QDoubleSpinBox()
            control.setRange(-1.0, 1.0)
            control.setSingleStep(0.05)
            control.setDecimals(2)
            self.grade_controls[key] = control
            form.addRow(label, control)

        self.reference_transfer = QSpinBox()
        self.reference_transfer.setRange(0, 100)
        self.reference_transfer.setSingleStep(5)
        self.reference_transfer.setSuffix("%")
        self.reference_transfer.setToolTip(
            "仅执行有界 Oklab 均值偏移，不改变几何；启用后不能导出通用 LUT。"
        )
        form.addRow("有限参考色迁移", self.reference_transfer)

        self.grade_scope = QComboBox()
        self.grade_scope.addItem("全图", "full")
        self.grade_scope.addItem("当前选中配对区域", "selected_region")
        form.addRow("作用范围", self.grade_scope)
        layout.addLayout(form)

        self.grade_strength, grade_strength_row = self._strength_row(25)
        layout.addWidget(QLabel("参考影响强度"))
        layout.addWidget(grade_strength_row)

        controls = QHBoxLayout()
        self.grade_preview_button = QPushButton("生成安全预览")
        self.grade_preview_button.setProperty("primary", True)
        self.grade_original_button = QCheckBox("A/B 显示原图")
        self.grade_original_button.setEnabled(False)
        self.undo_button = QPushButton("撤销配方")
        self.redo_button = QPushButton("重做配方")
        controls.addWidget(self.grade_preview_button)
        controls.addWidget(self.grade_original_button)
        controls.addWidget(self.undo_button)
        controls.addWidget(self.redo_button)
        layout.addLayout(controls)

        exports = QHBoxLayout()
        self.export_png_button = QPushButton("导出 PNG")
        self.export_json_button = QPushButton("导出 JSON 配方")
        self.export_cube_button = QPushButton("导出 .cube")
        for button in (
            self.export_png_button,
            self.export_json_button,
            self.export_cube_button,
        ):
            button.setEnabled(False)
            exports.addWidget(button)
        layout.addLayout(exports)
        self.grade_status = QLabel("尚未生成安全调色预览。")
        self.grade_status.setWordWrap(True)
        layout.addWidget(self.grade_status)

        self.grade_preview_button.clicked.connect(self._request_grade_preview)
        self.grade_original_button.toggled.connect(
            self.show_original_requested
        )
        self.undo_button.clicked.connect(lambda: self._restore_recipe("undo"))
        self.redo_button.clicked.connect(lambda: self._restore_recipe("redo"))
        self.export_png_button.clicked.connect(
            lambda: self.grade_export_requested.emit("png")
        )
        self.export_json_button.clicked.connect(
            lambda: self.grade_export_requested.emit("json")
        )
        self.export_cube_button.clicked.connect(
            lambda: self.grade_export_requested.emit("cube")
        )
        return group

    def _build_concept_group(self) -> QGroupBox:
        group = QGroupBox("AI 优化预演")
        layout = QVBoxLayout(group)
        boundary = QLabel(
            "输出始终保存为 AIConceptPreview，不会成为真实 UE 截图 Version。"
            "AI 强度是允许的改动预算，不是数学插值比例。"
        )
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        form = QFormLayout()

        self.image_provider_combo = QComboBox()
        image_manifests = [
            item
            for item in self._manifests.values()
            if ProviderCapability.IMAGE_EDIT in item.capabilities
        ]
        image_manifests.sort(
            key=lambda item: (
                item.mainland_priority,
                item.display_name,
            )
        )
        for manifest in image_manifests:
            self.image_provider_combo.addItem(
                manifest.display_name,
                manifest.provider_id,
            )
        form.addRow("图像供应商", self.image_provider_combo)
        self.image_model_edit = QLineEdit()
        form.addRow("模型 ID", self.image_model_edit)

        credential_row = QWidget()
        credential_layout = QHBoxLayout(credential_row)
        credential_layout.setContentsMargins(0, 0, 0, 0)
        self.image_credential_edit = QLineEdit()
        self.image_credential_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.image_credential_edit.setPlaceholderText("不会写入项目或日志")
        self.image_credential_save = QPushButton("存入系统凭据")
        self.image_credential_delete = QPushButton("删除")
        credential_layout.addWidget(self.image_credential_edit, 1)
        credential_layout.addWidget(self.image_credential_save)
        credential_layout.addWidget(self.image_credential_delete)
        form.addRow("API Key", credential_row)

        self.preview_mode = QComboBox()
        self.preview_mode.addItem("只改灯光", PreviewEditMode.LIGHTING_ONLY)
        self.preview_mode.addItem("只改色彩", PreviewEditMode.COLOUR_ONLY)
        self.preview_mode.addItem(
            "只改雾与氛围",
            PreviewEditMode.FOG_ATMOSPHERE_ONLY,
        )
        form.addRow("预演模式", self.preview_mode)
        layout.addLayout(form)

        self.concept_strength, concept_strength_row = self._strength_row(25)
        self.concept_strength.valueChanged.connect(
            self._update_budget_semantics
        )
        layout.addWidget(QLabel("允许改动预算"))
        layout.addWidget(concept_strength_row)
        self.budget_semantics = QLabel()
        self.budget_semantics.setWordWrap(True)
        layout.addWidget(self.budget_semantics)

        self.preserve_composition = QCheckBox("保持构图")
        self.preserve_geometry = QCheckBox("保持几何")
        self.preserve_asset_identity = QCheckBox("保持资产身份")
        for control in (
            self.preserve_composition,
            self.preserve_geometry,
            self.preserve_asset_identity,
        ):
            control.setChecked(True)
            layout.addWidget(control)

        privacy = QHBoxLayout()
        self.preview_remove_metadata = QCheckBox("移除元数据")
        self.preview_remove_metadata.setChecked(True)
        self.preview_maximum_side = QComboBox()
        self.preview_maximum_side.addItem("最长边 1280 px", 1280)
        self.preview_maximum_side.addItem("最长边 2048 px", 2048)
        self.preview_maximum_side.addItem("最长边 4096 px", 4096)
        self.preview_maximum_side.addItem("原始尺寸", None)
        self.preview_maximum_side.setCurrentIndex(1)
        privacy.addWidget(self.preview_remove_metadata)
        privacy.addWidget(self.preview_maximum_side)
        layout.addLayout(privacy)

        buttons = QHBoxLayout()
        self.concept_run_button = QPushButton("查看发送清单并生成预演")
        self.concept_run_button.setProperty("primary", True)
        self.concept_cancel_button = QPushButton("取消")
        self.concept_cancel_button.setEnabled(False)
        self.concept_task_button = QPushButton("从预演生成任务")
        self.concept_task_button.setEnabled(False)
        buttons.addWidget(self.concept_run_button)
        buttons.addWidget(self.concept_cancel_button)
        buttons.addWidget(self.concept_task_button)
        layout.addLayout(buttons)
        self.concept_status = QLabel(
            "未运行。离线 Mock 会回传当前截图，用于验证完整隔离流程。"
        )
        self.concept_status.setWordWrap(True)
        layout.addWidget(self.concept_status)

        self.image_provider_combo.currentIndexChanged.connect(
            self._image_provider_changed
        )
        self.image_credential_save.clicked.connect(
            lambda: self.credential_save_requested.emit(
                str(self.image_provider_combo.currentData()),
                self.image_credential_edit.text(),
            )
        )
        self.image_credential_delete.clicked.connect(
            lambda: self.credential_delete_requested.emit(
                str(self.image_provider_combo.currentData())
            )
        )
        self.concept_run_button.clicked.connect(
            lambda: self.concept_requested.emit(self.concept_options())
        )
        self.concept_cancel_button.clicked.connect(
            self.concept_cancel_requested
        )
        self.concept_task_button.clicked.connect(
            self.concept_tasks_requested
        )
        self._image_provider_changed()
        self._update_budget_semantics()
        return group

    @staticmethod
    def _strength_row(initial: int) -> tuple[QSlider, QWidget]:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        slider_row = QHBoxLayout()
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setSingleStep(5)
        slider.setPageStep(5)
        slider.setValue(initial)
        label = QLabel(f"{initial}%")
        slider.valueChanged.connect(
            lambda value: (
                slider.setValue(max(0, min(100, int(round(value / 5)) * 5)))
                if value % 5
                else None
            )
        )
        slider.valueChanged.connect(lambda value: label.setText(f"{value}%"))
        slider_row.addWidget(slider, 1)
        slider_row.addWidget(label)
        layout.addLayout(slider_row)
        quick = QHBoxLayout()
        for value in (5, 10, 15, 25, 50, 75, 100):
            button = QPushButton(f"{value}%")
            button.clicked.connect(
                lambda _checked=False, target=value: slider.setValue(target)
            )
            quick.addWidget(button)
        layout.addLayout(quick)
        return slider, body

    def match_weights(self) -> dict[str, float]:
        return {
            key: control.value()
            for key, control in self.weight_controls.items()
        }

    def current_recipe(
        self,
        normalized_rect: tuple[float, float, float, float] | None = None,
    ) -> SafeGradeRecipe:
        return SafeGradeRecipe(
            exposure_stops=self.exposure.value(),
            contrast=self.grade_controls["contrast"].value(),
            temperature=self.grade_controls["temperature"].value(),
            tint=self.grade_controls["tint"].value(),
            shadows=self.grade_controls["shadows"].value(),
            midtones=self.grade_controls["midtones"].value(),
            highlights=self.grade_controls["highlights"].value(),
            saturation=self.grade_controls["saturation"].value(),
            reference_colour_transfer=(
                self.reference_transfer.value() / 100.0
            ),
            strength_percent=self.grade_strength.value(),
            normalized_rect=normalized_rect,
        )

    def concept_options(self) -> ConceptPreviewOptions:
        return ConceptPreviewOptions(
            provider_id=str(self.image_provider_combo.currentData()),
            model_id=self.image_model_edit.text().strip() or None,
            mode=PreviewEditMode(self.preview_mode.currentData()),
            change_budget_percent=self.concept_strength.value(),
            preserve_composition=self.preserve_composition.isChecked(),
            preserve_geometry=self.preserve_geometry.isChecked(),
            preserve_asset_identity=self.preserve_asset_identity.isChecked(),
            remove_metadata=self.preview_remove_metadata.isChecked(),
            maximum_side=self.preview_maximum_side.currentData(),
        )

    def show_match_profile(self, profile: MatchProfile) -> None:
        self.match_tree.clear()
        for item in profile.dimensions:
            value = (
                "证据不足"
                if item.similarity is None
                else f"{item.similarity * 100:.1f}%"
            )
            source = {
                "measurement": "测量结果",
                "algorithm_inference": "算法推断",
                "art_judgment": "需美术判断",
            }.get(item.evidence_type, item.evidence_type)
            row = QTreeWidgetItem(
                [
                    item.display_name,
                    value,
                    source,
                    f"{profile.weights[item.dimension_id]:.1f}",
                ]
            )
            row.setToolTip(0, item.explanation)
            self.match_tree.addTopLevelItem(row)
        estimated = (
            "无法汇总"
            if profile.estimated_match is None
            else f"{profile.estimated_match * 100:.1f}%"
        )
        self.match_summary.setText(
            f"估计匹配度：{estimated}　|　"
            f"证据覆盖：{profile.evidence_coverage * 100:.1f}%"
        )

    def show_grade_preview(self, recipe: SafeGradeRecipe) -> None:
        if self._history_navigation_pending:
            self._history_navigation_pending = False
        else:
            self._history.push(recipe)
        self._preview_available = True
        self.grade_original_button.setEnabled(True)
        self.grade_original_button.setChecked(False)
        self.export_png_button.setEnabled(True)
        self.export_json_button.setEnabled(True)
        self.export_cube_button.setEnabled(
            recipe.normalized_rect is None
            and recipe.reference_colour_transfer == 0.0
        )
        scope = "全图" if recipe.normalized_rect is None else "选中区域"
        self.grade_status.setText(
            f"已生成 {scope} 安全预览 · 实际插值强度 "
            f"{recipe.strength_percent}% · 原图保持只读"
        )

    def current_history_recipe(self) -> SafeGradeRecipe:
        return self._history.current

    def _request_grade_preview(self) -> None:
        self.safe_preview_requested.emit(
            {
                "scope": str(self.grade_scope.currentData()),
            }
        )

    def _restore_recipe(self, direction: str) -> None:
        recipe = (
            self._history.undo()
            if direction == "undo"
            else self._history.redo()
        )
        self._history_navigation_pending = True
        self.set_recipe_controls(recipe)
        self.safe_preview_requested.emit(
            {
                "scope": (
                    "full"
                    if recipe.normalized_rect is None
                    else "history_region"
                ),
                "recipe": recipe,
            }
        )

    def set_recipe_controls(self, recipe: SafeGradeRecipe) -> None:
        self.exposure.setValue(recipe.exposure_stops)
        for key, control in self.grade_controls.items():
            control.setValue(float(getattr(recipe, key)))
        self.reference_transfer.setValue(
            int(round(recipe.reference_colour_transfer * 100))
        )
        self.grade_strength.setValue(recipe.strength_percent)
        self.grade_scope.setCurrentIndex(
            self.grade_scope.findData(
                "full"
                if recipe.normalized_rect is None
                else "selected_region"
            )
        )

    def show_concept_running(self, running: bool) -> None:
        self.concept_run_button.setEnabled(not running)
        self.concept_cancel_button.setEnabled(running)
        if running:
            self.concept_status.setText("AI 优化预演正在后台执行…")

    def show_concept_validation(
        self,
        validation: PreviewValidation,
        *,
        provider_id: str,
        model_id: str,
    ) -> None:
        self.show_concept_running(False)
        self._concept_available = True
        self.concept_task_button.setEnabled(True)
        status = (
            "仅适合概念参考"
            if validation.status == AIConceptPreviewStatus.CONCEPT_ONLY
            else "候选预演（仍非真实 Version）"
        )
        protected = (
            "无保护区证据"
            if validation.protected_region_change is None
            else f"{validation.protected_region_change * 100:.2f}%"
        )
        reasons = (
            "；".join(validation.reasons)
            if validation.reasons
            else "未触发结构边界警告"
        )
        self.concept_status.setText(
            f"{status} · {provider_id}/{model_id}\n"
            f"结构漂移 {validation.structure_drift * 100:.2f}% · "
            f"构图偏移 {validation.composition_shift * 100:.2f}% · "
            f"保护区变化 {protected} · "
            f"色调目标改善 {validation.target_improvement * 100:+.2f} 个百分点\n"
            f"{reasons}"
        )

    def show_concept_error(self, message: str) -> None:
        self.show_concept_running(False)
        self.concept_status.setText(f"预演失败：{message}")

    def reset_transient_state(self) -> None:
        self._preview_available = False
        self._concept_available = False
        self.grade_original_button.setChecked(False)
        self.grade_original_button.setEnabled(False)
        for button in (
            self.export_png_button,
            self.export_json_button,
            self.export_cube_button,
            self.concept_task_button,
        ):
            button.setEnabled(False)
        self.grade_status.setText("尚未生成安全调色预览。")
        self.concept_status.setText(
            "未运行。离线 Mock 会回传当前截图，用于验证完整隔离流程。"
        )

    def _image_provider_changed(self, _index: int = -1) -> None:
        provider_id = str(self.image_provider_combo.currentData())
        manifest = self._manifests.get(provider_id)
        if manifest is None:
            self.image_model_edit.clear()
            return
        self.image_model_edit.setText(
            manifest.model_for(ProviderCapability.IMAGE_EDIT)
        )
        self.image_credential_edit.clear()
        is_mock = provider_id == "mock"
        self.image_credential_edit.setEnabled(not is_mock)
        self.image_credential_save.setEnabled(not is_mock)
        self.image_credential_delete.setEnabled(not is_mock)

    def _update_budget_semantics(self, _value: int = -1) -> None:
        percent = self.concept_strength.value()
        text = change_budget_semantics(percent)
        if percent > 75:
            self.budget_semantics.setStyleSheet(
                "color: #EF6C6C; font-weight: 600;"
            )
        else:
            self.budget_semantics.setStyleSheet("")
        self.budget_semantics.setText(text)
