from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import logging
from pathlib import Path
import uuid

import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, QThreadPool, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QKeySequence,
    QPixmap,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scenelens.analysis.asset_masks import (
    normalized_rect_to_pixels,
    visible_asset_mask,
)
from scenelens.imaging.loader import LoadedImage, load_image
from scenelens.imaging.provider_export import (
    ProviderImageExportOptions,
    prepare_provider_image,
)
from scenelens.imaging.qt import numpy_to_qimage
from scenelens.modules.asset_breakdown.artifacts import (
    asset_crop_png,
    make_asset_board_pages,
    write_asset_manifest,
)
from scenelens.modules.asset_breakdown.advisory import (
    AssetBreakdownAdvisoryContext,
    AssetBreakdownAdvisoryReview,
)
from scenelens.modules.asset_breakdown.automatic import (
    AutomaticPipelineResult,
    is_systemic_provider_error,
    provider_error_message,
    run_automatic_pipeline,
)
from scenelens.modules.asset_breakdown.models import (
    ASSET_CATEGORIES,
    AssetPromptSession,
    AutomaticAssetRun,
    AssetBoardPage,
    AssetBreakdownState,
    AssetItem,
    AssetProductionSpec,
    BreakdownPlan,
    GenerationRecord,
    PromptMessage,
    PromptRevision,
    StudyHandoffSnapshot,
)
from scenelens.modules.asset_breakdown.planning import (
    confirm_plan,
    create_plan_from_preset,
    load_breakdown_plan_presets,
    plan_fingerprint,
    plan_from_ai,
    understanding_from_ai,
)
from scenelens.modules.asset_breakdown.production_handoff import (
    STATUS_LABELS as PRODUCTION_STATUS_LABELS,
    build_handoff_payload,
    export_handoff_csv,
    export_handoff_json,
    synchronize_production_specs,
    validate_production_specs,
)
from scenelens.modules.asset_breakdown.prompt_workshop import (
    AssetPromptContext,
    AssetPromptWorkshopReview,
)
from scenelens.modules.asset_breakdown.presets import load_scene_profiles
from scenelens.modules.asset_breakdown.reviews import (
    AssetBreakdownContext,
    AssetBreakdownReview,
    asset_generation_instruction,
)
from scenelens.modules.asset_breakdown.service import (
    asset_from_ai,
    create_manual_asset,
    merge_ai_assets,
    merge_assets,
    split_asset,
)
from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.asset_breakdown.ui.prompt_workshop_panel import (
    AssetPromptWorkshopPanel,
)
from scenelens.modules.asset_breakdown.ui.workspace_style import (
    asset_workspace_stylesheet,
)
from scenelens.providers.contracts import (
    CancellationToken,
    DataDisclosurePreview,
    ImageEditRequest,
    ProviderCapability,
    ProviderError,
    ProviderImage,
    disclosure_preview,
)
from scenelens.providers.credentials import (
    MemoryCredentialStore,
    WindowsCredentialStore,
)
from scenelens.providers.execution import ProviderExecutionService
from scenelens.providers.factory import create_default_provider_registry
from scenelens.storage.project_store import utc_now
from scenelens.storage.workspace_catalog import WorkspaceCatalogStore
from scenelens.core.handoffs import WorkspaceHandoff
from scenelens.ui.image_canvas import ImageCanvas, RegionOverlaySpec
from scenelens.ui.workers import FunctionWorker


LOGGER = logging.getLogger(__name__)
PROJECT_SUFFIX = ".scenelens-assets"
CATEGORY_LABELS = {
    "building": "建筑",
    "modular_piece": "模块构件",
    "prop": "道具",
    "vegetation": "植被",
    "terrain": "地形",
    "material": "材质",
    "decal": "贴花／标识",
    "background": "远景／纯视觉元素",
    "lighting_vfx": "灯光／特效代理",
    "character_vehicle": "角色／载具",
    "unknown": "待分类",
}
SOURCE_LABELS = {
    "visible_evidence": "原画可见证据",
    "ai_inference": "AI 推断",
    "user_added": "用户补充／修订",
    "ai_generated_completion": "AI 生成补全",
}
PRIORITY_LABELS = {
    "critical": "关键",
    "high": "高",
    "medium": "中",
    "low": "低",
}
GENERATION_KIND_LABELS = {
    "isolated_concept": "独立资产概念图",
    "occlusion_completion": "保守遮挡补全图",
    "presentation": "资产评审展示图",
}
ASSET_COLOURS = (
    "#4FC3F7",
    "#FFD166",
    "#80CBC4",
    "#FF8A80",
    "#B39DDB",
    "#AED581",
    "#FFB74D",
    "#90CAF9",
)


class SendDisclosureDialog(QDialog):
    def __init__(
        self,
        preview: DataDisclosurePreview,
        *,
        purpose: str,
        extra_notice: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"确认发送{purpose}数据")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "GATalk 不会自动上传。继续后，下面列出的图片副本和结构化"
            "字段会发送给所选服务；项目路径、原图 EXIF 和 ICC 不会发送。"
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        layout.addWidget(
            QLabel(
                f"供应商：{preview.provider_id}\n"
                f"模型：{preview.model_id}\n"
                f"字段：{', '.join(preview.payload_fields)}"
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
        warning = QLabel(
            "商业保密内容是否允许上传由所属团队政策决定。AI 识别、分类、"
            "模块关系和不可见结构均为推断；生成补全不是原画事实。"
        )
        warning.setWordWrap(True)
        warning.setProperty("tone", "warning")
        layout.addWidget(warning)
        if preview.fallback_model_ids:
            fallback_chain = " → ".join(preview.fallback_model_ids)
            fallback = QLabel(
                "若当前模型持续繁忙或已经下线，将在同一供应商内依次尝试"
                f"备用模型：{fallback_chain}。不会跨供应商；每次尝试都可能"
                "产生调用费用。"
            )
            fallback.setWordWrap(True)
            fallback.setProperty("tone", "warning")
            layout.addWidget(fallback)
        if extra_notice:
            extra = QLabel(extra_notice)
            extra.setWordWrap(True)
            extra.setProperty("tone", "warning")
            layout.addWidget(extra)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认并发送")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class _AssetStateCommand(QUndoCommand):
    def __init__(
        self,
        window: "AssetBreakdownWindow",
        *,
        before_assets: tuple[AssetItem, ...],
        before_generations: tuple[GenerationRecord, ...],
        after_assets: tuple[AssetItem, ...],
        after_generations: tuple[GenerationRecord, ...],
        select_id: str,
        text: str,
    ) -> None:
        super().__init__(text)
        self._window = window
        self._before = (before_assets, before_generations)
        self._after = (after_assets, after_generations)
        self._select_id = select_id

    def undo(self) -> None:
        self._window._restore_asset_state(*self._before)

    def redo(self) -> None:
        self._window._restore_asset_state(
            *self._after,
            select_id=self._select_id,
        )


class AssetBreakdownWindow(QMainWindow):
    workspace_home_requested = Signal()
    review_task_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GATalk — 资产拆分工作台")
        self.resize(1580, 940)
        self.setMinimumSize(1100, 720)

        self._store: AssetBreakdownStore | None = None
        self._state: AssetBreakdownState | None = None
        self._loaded: LoadedImage | None = None
        self._workers: set[FunctionWorker] = set()
        self._callbacks: dict[tuple[str, int], object] = {}
        self._generation_counter: dict[str, int] = {}
        self._ai_cancellation: CancellationToken | None = None
        self._image_cancellation: CancellationToken | None = None
        self._automatic_cancellation: CancellationToken | None = None
        self._prompt_cancellation: CancellationToken | None = None
        self._restoring = False
        self._syncing_ai_controls = False
        self._undo_stack = QUndoStack(self)

        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(
            min(4, max(2, QThread.idealThreadCount()))
        )
        self._provider_registry = create_default_provider_registry()
        self._execution = ProviderExecutionService()
        self._reviewer = AssetBreakdownReview()
        self._advisor = AssetBreakdownAdvisoryReview()
        self._prompt_reviewer = AssetPromptWorkshopReview()
        self._profiles = load_scene_profiles()
        self._plan_config = load_breakdown_plan_presets()
        try:
            self._credential_store = WindowsCredentialStore()
        except OSError:
            self._credential_store = MemoryCredentialStore()

        self._build_actions()
        self._build_toolbar()
        self._build_project_dock()
        self._build_central_ui()
        self.setStyleSheet(asset_workspace_stylesheet())
        self._connect_signals()
        self.statusBar().showMessage(
            "新建或打开资产拆分项目，然后导入一张场景原画。"
        )

    def _build_actions(self) -> None:
        self.home_action = QAction("工作台首页", self)
        self.home_action.triggered.connect(
            lambda _checked=False: self.workspace_home_requested.emit()
        )
        self.new_action = QAction("新建资产项目…", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self._new_project)
        self.open_action = QAction("打开资产项目…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._open_project)
        self.save_action = QAction("保存", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._save_fields)
        self.import_main_action = QAction("导入主原画…", self)
        self.import_main_action.triggered.connect(self._choose_main_image)
        self.import_reference_action = QAction("补充参考…", self)
        self.import_reference_action.triggered.connect(
            self._choose_reference_image
        )
        self.region_mode_action = QAction("框选资产", self)
        self.region_mode_action.setCheckable(True)
        self.hide_regions_action = QAction("隐藏框", self)
        self.hide_regions_action.setCheckable(True)
        self.reset_view_action = QAction("重置视图", self)
        self.undo_action = QAction("撤销", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self._undo_requested)
        self.redo_action = QAction("重做", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self._redo_requested)
        self.delete_action = QAction("删除选中资产", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.triggered.connect(self._delete_shortcut_requested)

        menu = self.menuBar().addMenu("文件")
        menu.addActions(
            [
                self.new_action,
                self.open_action,
                self.save_action,
                self.import_main_action,
                self.import_reference_action,
            ]
        )
        edit_menu = self.menuBar().addMenu("编辑")
        edit_menu.addActions(
            [
                self.undo_action,
                self.redo_action,
                self.delete_action,
            ]
        )

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("资产拆分", self)
        toolbar.setObjectName("assetBreakdownToolbar")
        toolbar.setMovable(False)
        toolbar.addActions(
            [
                self.home_action,
                self.new_action,
                self.open_action,
                self.save_action,
            ]
        )
        toolbar.addSeparator()
        toolbar.addActions([self.undo_action, self.redo_action])
        toolbar.addSeparator()
        toolbar.addActions(
            [
                self.import_main_action,
                self.import_reference_action,
            ]
        )
        toolbar.addSeparator()
        toolbar.addActions(
            [
                self.region_mode_action,
                self.hide_regions_action,
                self.reset_view_action,
            ]
        )
        self.addToolBar(toolbar)

    def _build_project_dock(self) -> None:
        dock = QDockWidget("项目与场景", self)
        dock.setObjectName("assetBreakdownProjectDock")
        dock.setMinimumWidth(280)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(14)
        form = QFormLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.title_edit = QLineEdit()
        self.scene_type_combo = QComboBox()
        self.scene_type_combo.setEditable(True)
        for item in self._profiles["scene_types"]:
            self.scene_type_combo.addItem(item["label"], item["id"])
        self.goal_edit = QPlainTextEdit()
        self.goal_edit.setPlaceholderText(
            "例如：规划可复用的中世纪村庄建筑套件与街道道具。"
        )
        self.goal_edit.setMaximumHeight(92)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("用户校正、制作约束或待确认信息。")
        self.notes_edit.setMaximumHeight(100)
        form.addRow("项目名称", self.title_edit)
        form.addRow("场景类型", self.scene_type_combo)
        form.addRow("制作目标", self.goal_edit)
        form.addRow("备注", self.notes_edit)
        layout.addLayout(form)
        references = QGroupBox("补充参考")
        reference_layout = QVBoxLayout(references)
        self.reference_list = QListWidget()
        self.reference_list.setMinimumHeight(120)
        reference_layout.addWidget(self.reference_list)
        add_reference = QPushButton("导入补充参考")
        add_reference.clicked.connect(self._choose_reference_image)
        reference_layout.addWidget(add_reference)
        layout.addWidget(references)
        legend = QLabel(
            "信息来源：\n"
            "蓝色＝原画可见证据\n"
            "黄色＝AI 推断\n"
            "绿色＝用户补充／修订\n"
            "紫色＝AI 生成补全"
        )
        legend.setWordWrap(True)
        legend.setProperty("role", "muted")
        layout.addWidget(legend)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setObjectName("assetProjectScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setWidget(panel)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_central_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)
        self.canvas = ImageCanvas(
            "拖入场景原画，或选择“导入原画”"
        )
        splitter.addWidget(self.canvas)
        self.workflow_tabs = QTabWidget()
        self.workflow_tabs.setObjectName("assetWorkflowTabs")
        self.workflow_tabs.setDocumentMode(True)
        self.workflow_tabs.setMinimumWidth(560)
        manual = QTabWidget()
        manual.setObjectName("manualWorkflowTabs")
        self.manual_tabs = manual
        manual.setDocumentMode(True)
        inventory = self._build_inventory_tab()
        manual.addTab(self._build_plan_tab(), "拆分依据")
        manual.addTab(inventory, "资产清单")
        manual.addTab(self._build_detail_tab(), "资产详情")
        manual.addTab(self._build_production_tab(), "生产交接")
        manual.addTab(self._build_generation_tab(), "生成与导出")
        self.workflow_tabs.addTab(manual, "清单与校正")
        self.workflow_tabs.addTab(
            self._build_automatic_tab(),
            "自动资产板",
        )
        self.prompt_panel = AssetPromptWorkshopPanel()
        self.workflow_tabs.addTab(
            self.prompt_panel,
            "生成提示语",
        )
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self._build_workflow_context_bar())
        right_layout.addWidget(self.workflow_tabs, 1)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([980, 520])
        self.setCentralWidget(splitter)

    def _build_workflow_context_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("workflowContextBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        title = QLabel("当前拆分依据")
        title.setProperty("role", "muted")
        layout.addWidget(title)
        self.context_plan_combo = QComboBox()
        self.context_plan_combo.setMinimumWidth(210)
        self.context_plan_combo.setMaximumWidth(300)
        layout.addWidget(self.context_plan_combo, 1)
        self.context_plan_status = QLabel("未打开项目")
        self.context_plan_status.setWordWrap(False)
        self.context_plan_status.setFixedWidth(180)
        layout.addWidget(self.context_plan_status)
        self.edit_plan_button = QPushButton("编辑方案")
        layout.addWidget(self.edit_plan_button)
        return bar

    def _build_inventory_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(14)
        provider_group = QGroupBox("清单分析")
        provider_group.setObjectName("workflowSection")
        provider_form = QFormLayout(provider_group)
        provider_form.setContentsMargins(14, 12, 14, 14)
        provider_form.setHorizontalSpacing(12)
        provider_form.setVerticalSpacing(10)
        self.vision_provider_combo = QComboBox()
        for provider in self._provider_registry.for_capability(
            ProviderCapability.VISION_REVIEW
        ):
            self.vision_provider_combo.addItem(
                provider.manifest.display_name,
                provider.manifest.provider_id,
            )
        self.vision_model_edit = QLineEdit()
        self.vision_key_edit = QLineEdit()
        self.vision_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        save_key = QPushButton("存入系统凭据")
        save_key.clicked.connect(
            lambda: self._save_provider_key(
                self.vision_provider_combo,
                self.vision_key_edit,
            )
        )
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.vision_key_edit, 1)
        key_layout.addWidget(save_key)
        provider_form.addRow("供应商", self.vision_provider_combo)
        provider_form.addRow("模型 ID", self.vision_model_edit)
        provider_form.addRow("API Key", key_row)
        provider_note = QLabel(
            "视觉模型依据当前拆分方案生成结构化清单。图片模型在“生成与导出”"
            "中使用；相同供应商凭据在各工作方式间同步。"
        )
        provider_note.setWordWrap(True)
        provider_form.addRow(provider_note)
        buttons = QWidget()
        button_layout = QHBoxLayout(buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.analyze_button = QPushButton("检查发送内容并生成清单")
        self.analyze_button.setProperty("primary", True)
        self.cancel_analysis_button = QPushButton("取消")
        self.cancel_analysis_button.setEnabled(False)
        self.analyze_button.clicked.connect(self._start_ai_breakdown)
        self.cancel_analysis_button.clicked.connect(self._cancel_analysis)
        button_layout.addWidget(self.analyze_button, 1)
        button_layout.addWidget(self.cancel_analysis_button)
        provider_form.addRow(buttons)
        layout.addWidget(provider_group)

        actions = QWidget()
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.add_asset_button = QPushButton("新增")
        self.split_asset_button = QPushButton("拆分")
        self.merge_asset_button = QPushButton("合并")
        self.delete_asset_button = QPushButton("删除")
        self.mask_button = QPushButton("可见遮罩")
        for button in (
            self.add_asset_button,
            self.split_asset_button,
            self.merge_asset_button,
            self.delete_asset_button,
            self.mask_button,
        ):
            action_layout.addWidget(button)
        layout.addWidget(actions)

        self.asset_tree = QTreeWidget()
        self.asset_tree.setHeaderLabels(
            ["生成", "资产", "分类", "层级", "来源", "优先级"]
        )
        self.asset_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.asset_tree.setColumnWidth(0, 48)
        self.asset_tree.setColumnWidth(1, 160)
        self.asset_tree.setColumnWidth(2, 95)
        self.asset_tree.setColumnWidth(3, 50)
        self.asset_tree.setColumnWidth(4, 105)
        self.asset_tree.setMinimumHeight(280)
        layout.addWidget(self.asset_tree, 1)
        self.asset_task_button = QPushButton("将所选资产加入审阅中心")
        self.asset_task_button.setEnabled(False)
        self.asset_task_button.clicked.connect(
            self._send_selected_assets_to_review_center
        )
        layout.addWidget(self.asset_task_button)
        self.inventory_summary = QLabel("状态：未生成清单")
        self.inventory_summary.setWordWrap(True)
        layout.addWidget(self.inventory_summary)
        return root

    def _build_plan_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 14, 16, 24)
        layout.setSpacing(14)
        intro = QLabel(
            "先确认场景结构和生产目标，再确定拆分深度。同一原画可保存多套"
            "独立方案，例如“完整装配体”和“建筑生产套件”。分析建议不会"
            "自动覆盖已确认方案。"
        )
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        handoff_group = QGroupBox("作品研究交接（可选）")
        handoff_layout = QVBoxLayout(handoff_group)
        self.handoff_summary = QLabel(
            "当前项目独立开始；也可在“作品研究”中点击“交给资产拆分”。"
        )
        self.handoff_summary.setWordWrap(True)
        handoff_layout.addWidget(self.handoff_summary)
        self.handoff_adjustments = QPlainTextEdit()
        self.handoff_adjustments.setPlaceholderText(
            "只写这次拆分需要修正或补充的上下文；原研究快照保持不变。"
        )
        self.handoff_adjustments.setMaximumHeight(72)
        handoff_layout.addWidget(self.handoff_adjustments)
        layout.addWidget(handoff_group)

        understanding_group = QGroupBox("1  场景结构")
        understanding_layout = QVBoxLayout(understanding_group)
        self.understanding_text = QPlainTextEdit()
        self.understanding_text.setReadOnly(True)
        self.understanding_text.setPlaceholderText(
            "尚无场景结构记录。可执行分析，也可直接采用预设方案。"
        )
        self.understanding_text.setMinimumHeight(150)
        understanding_layout.addWidget(self.understanding_text)
        self.understanding_corrections = QPlainTextEdit()
        self.understanding_corrections.setPlaceholderText(
            "用户校正：例如“左侧与中央其实属于同一建筑族；远景只做卡片”。"
        )
        self.understanding_corrections.setMaximumHeight(76)
        understanding_layout.addWidget(self.understanding_corrections)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.understand_button = QPushButton("检查发送内容并分析场景结构")
        self.understand_button.setProperty("primary", True)
        self.cancel_understanding_button = QPushButton("取消")
        self.cancel_understanding_button.setEnabled(False)
        row_layout.addWidget(self.understand_button, 1)
        row_layout.addWidget(self.cancel_understanding_button)
        understanding_layout.addWidget(row)
        layout.addWidget(understanding_group)

        plan_group = QGroupBox("2  拆分方案")
        plan_layout = QVBoxLayout(plan_group)
        top_form = QFormLayout()
        self.plan_combo = QComboBox()
        self.plan_preset_combo = QComboBox()
        for preset in self._plan_config["presets"]:
            self.plan_preset_combo.addItem(preset["name"], preset["id"])
        self.plan_name_edit = QLineEdit()
        self.plan_purpose_edit = QPlainTextEdit()
        self.plan_purpose_edit.setMaximumHeight(68)
        self.plan_grouping_combo = QComboBox()
        for label, value in (
            ("按资产族／复用组", "asset_family"),
            ("按父子层级", "hierarchy"),
            ("按场景空间系统", "spatial_system"),
            ("按资产类别", "category"),
        ):
            self.plan_grouping_combo.addItem(label, value)
        self.plan_page_limit = QSpinBox()
        self.plan_page_limit.setRange(4, 16)
        self.plan_page_limit.setValue(9)
        top_form.addRow("当前方案", self.plan_combo)
        top_form.addRow("从预设新建", self.plan_preset_combo)
        top_form.addRow("方案名称", self.plan_name_edit)
        top_form.addRow("用途", self.plan_purpose_edit)
        top_form.addRow("资产板分组", self.plan_grouping_combo)
        top_form.addRow("每页最多项目", self.plan_page_limit)
        plan_layout.addLayout(top_form)

        depth_group = QGroupBox("类别深度（0 不纳入，4 细节组件）")
        depth_form = QFormLayout(depth_group)
        self.plan_depth_combos: dict[str, QComboBox] = {}
        for category in ASSET_CATEGORIES:
            combo = QComboBox()
            for item in self._plan_config["depth_levels"]:
                combo.addItem(
                    f"{item['value']} · {item['label']}",
                    int(item["value"]),
                )
                combo.setItemData(
                    combo.count() - 1,
                    item["description"],
                    Qt.ItemDataRole.ToolTipRole,
                )
            self.plan_depth_combos[category] = combo
            depth_form.addRow(CATEGORY_LABELS[category], combo)
        plan_layout.addWidget(depth_group)
        self.plan_notes_edit = QPlainTextEdit()
        self.plan_notes_edit.setPlaceholderText(
            "本方案的人工约束，例如“塔楼整体保留，门窗拆到变体；人物不纳入”。"
        )
        self.plan_notes_edit.setMaximumHeight(72)
        plan_layout.addWidget(self.plan_notes_edit)
        actions = QWidget()
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.new_plan_button = QPushButton("按预设新建")
        self.save_plan_button = QPushButton("保存方案")
        self.delete_plan_button = QPushButton("删除方案")
        action_layout.addWidget(self.new_plan_button)
        action_layout.addWidget(self.save_plan_button, 1)
        action_layout.addWidget(self.delete_plan_button)
        plan_layout.addWidget(actions)
        self.plan_status = QLabel("状态：未选择方案")
        self.plan_status.setWordWrap(True)
        plan_layout.addWidget(self.plan_status)
        layout.addWidget(plan_group)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(scroll)
        return root

    def _build_detail_tab(self) -> QWidget:
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(16, 14, 16, 24)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.detail_name = QLineEdit()
        self.detail_category = QComboBox()
        self.detail_category.setEditable(True)
        for category in ASSET_CATEGORIES:
            self.detail_category.addItem(CATEGORY_LABELS[category], category)
        self.detail_semantic = QLineEdit()
        self.detail_parent = QLineEdit()
        self.detail_reuse = QLineEdit()
        self.detail_priority = QComboBox()
        for value, label in (
            ("critical", "关键"),
            ("high", "高"),
            ("medium", "中"),
            ("low", "低"),
        ):
            self.detail_priority.addItem(label, value)
        self.detail_source = QLabel("—")
        self.detail_rect = QLabel("—")
        self.detail_evidence = QPlainTextEdit()
        self.detail_inference = QPlainTextEdit()
        self.detail_uncertainty = QPlainTextEdit()
        self.detail_strategy = QPlainTextEdit()
        self.detail_material = QPlainTextEdit()
        for editor in (
            self.detail_evidence,
            self.detail_inference,
            self.detail_uncertainty,
            self.detail_strategy,
            self.detail_material,
        ):
            editor.setMaximumHeight(84)
        form.addRow("名称", self.detail_name)
        form.addRow("分类", self.detail_category)
        form.addRow("语义", self.detail_semantic)
        form.addRow("父资产 ID", self.detail_parent)
        form.addRow("复用组", self.detail_reuse)
        form.addRow("制作优先级", self.detail_priority)
        form.addRow("信息来源", self.detail_source)
        form.addRow("归一化区域", self.detail_rect)
        form.addRow("原画可见证据", self.detail_evidence)
        form.addRow("AI 推断", self.detail_inference)
        form.addRow("不确定性", self.detail_uncertainty)
        form.addRow("制作策略", self.detail_strategy)
        form.addRow("材质说明", self.detail_material)
        self.apply_detail_button = QPushButton("保存用户修订")
        form.addRow(self.apply_detail_button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        return wrapper

    def _build_production_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 14, 16, 24)
        layout.setSpacing(14)
        intro = QLabel(
            "把当前拆分方案整理为可交接的生产规格。自动建立的内容是规划起点，"
            "尺寸、轴心、碰撞、Nanite 和目录仍需由制作人员确认。"
        )
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        layout.addWidget(intro)
        toolbar = QHBoxLayout()
        self.production_sync_button = QPushButton("同步当前方案")
        self.production_sync_button.setProperty("primary", True)
        toolbar.addWidget(self.production_sync_button)
        self.production_export_csv = QPushButton("导出 CSV…")
        toolbar.addWidget(self.production_export_csv)
        self.production_export_json = QPushButton("导出 UE 交接 JSON…")
        toolbar.addWidget(self.production_export_json)
        layout.addLayout(toolbar)
        self.production_tree = QTreeWidget()
        self.production_tree.setHeaderLabels(
            ["编码", "资产", "状态", "优先级", "复用组", "UE 目录"]
        )
        self.production_tree.setRootIsDecorated(False)
        self.production_tree.setAlternatingRowColors(True)
        self.production_tree.setMinimumHeight(220)
        self.production_tree.setColumnWidth(0, 120)
        self.production_tree.setColumnWidth(1, 180)
        layout.addWidget(self.production_tree, 1)

        details = QGroupBox("生产规格")
        form = QFormLayout(details)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
        self.production_code = QLineEdit()
        self.production_status = QComboBox()
        for value, label in PRODUCTION_STATUS_LABELS.items():
            self.production_status.addItem(label, value)
        self.production_dimensions = QLineEdit()
        self.production_dimensions.setPlaceholderText("例如：400 × 300 × 650 cm")
        self.production_pivot = QLineEdit()
        self.production_geometry = QPlainTextEdit()
        self.production_materials = QLineEdit()
        self.production_materials.setPlaceholderText("用逗号分隔")
        self.production_textures = QLineEdit()
        self.production_textures.setPlaceholderText("BaseColor, Normal, ORM")
        self.production_lod = QLineEdit()
        self.production_collision = QLineEdit()
        self.production_nanite = QComboBox()
        for label, value in (
            ("待评估", "evaluate"),
            ("启用", "enabled"),
            ("禁用", "disabled"),
            ("不适用", "not_applicable"),
        ):
            self.production_nanite.addItem(label, value)
        self.production_destination = QLineEdit()
        self.production_dependencies = QLineEdit()
        self.production_dependencies.setPlaceholderText("前置资产 ID，用逗号分隔")
        self.production_deliverables = QLineEdit()
        self.production_deliverables.setPlaceholderText("模型, 材质实例, 碰撞检查")
        self.production_notes = QPlainTextEdit()
        for editor in (self.production_geometry, self.production_notes):
            editor.setMaximumHeight(72)
        form.addRow("资产编码", self.production_code)
        form.addRow("制作状态", self.production_status)
        form.addRow("目标尺寸", self.production_dimensions)
        form.addRow("轴心与装配基准", self.production_pivot)
        form.addRow("几何策略", self.production_geometry)
        form.addRow("材质槽", self.production_materials)
        form.addRow("纹理集合", self.production_textures)
        form.addRow("LOD 策略", self.production_lod)
        form.addRow("碰撞策略", self.production_collision)
        form.addRow("Nanite", self.production_nanite)
        form.addRow("UE 目录", self.production_destination)
        form.addRow("前置资产", self.production_dependencies)
        form.addRow("交付内容", self.production_deliverables)
        form.addRow("制作备注", self.production_notes)
        self.production_save_button = QPushButton("保存生产规格")
        form.addRow(self.production_save_button)
        layout.addWidget(details)
        self.production_summary = QLabel("尚未建立生产规格。")
        self.production_summary.setWordWrap(True)
        layout.addWidget(self.production_summary)

        self.production_sync_button.clicked.connect(self._sync_production_specs)
        self.production_tree.currentItemChanged.connect(self._show_production_spec)
        self.production_save_button.clicked.connect(self._save_production_spec)
        self.production_export_csv.clicked.connect(
            lambda: self._export_production_handoff("csv")
        )
        self.production_export_json.clicked.connect(
            lambda: self._export_production_handoff("json")
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(scroll)
        return root

    def _build_generation_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 14, 16, 24)
        layout.setSpacing(14)
        group = QGroupBox("图片生成：仅处理勾选资产")
        group.setObjectName("workflowSection")
        form = QFormLayout(group)
        form.setContentsMargins(14, 12, 14, 14)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.image_provider_combo = QComboBox()
        for provider in self._provider_registry.for_capability(
            ProviderCapability.IMAGE_EDIT
        ):
            self.image_provider_combo.addItem(
                provider.manifest.display_name,
                provider.manifest.provider_id,
            )
        self.image_model_combo = QComboBox()
        self.image_model_combo.setEditable(True)
        self.image_model_edit = self.image_model_combo.lineEdit()
        self.image_key_edit = QLineEdit()
        self.image_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        image_save_key = QPushButton("存入系统凭据")
        image_save_key.clicked.connect(
            lambda: self._save_provider_key(
                self.image_provider_combo,
                self.image_key_edit,
            )
        )
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.image_key_edit, 1)
        key_layout.addWidget(image_save_key)
        self.generation_kind_combo = QComboBox()
        self.generation_kind_combo.addItem("独立资产概念图", "isolated_concept")
        self.generation_kind_combo.addItem(
            "保守遮挡补全图",
            "occlusion_completion",
        )
        self.generation_kind_combo.addItem("资产评审展示图", "presentation")
        self.image_resolution_combo = QComboBox()
        for label, value in (
            ("1K（推荐，成本较低）", "1K"),
            ("2K", "2K"),
            ("4K（成本和耗时较高）", "4K"),
        ):
            self.image_resolution_combo.addItem(label, value)
        form.addRow("图片供应商", self.image_provider_combo)
        form.addRow("模型", self.image_model_combo)
        form.addRow("API Key", key_row)
        form.addRow("生成类型", self.generation_kind_combo)
        form.addRow("输出分辨率", self.image_resolution_combo)
        warning = QLabel(
            "生成结果是概念辅助，不是原画中不可见结构的事实，也不会自动成为"
            "生产资产。每项结果会保留模型、参数、来源区域和输入哈希。"
        )
        warning.setWordWrap(True)
        warning.setProperty("tone", "warning")
        form.addRow(warning)
        generation_buttons = QWidget()
        button_layout = QHBoxLayout(generation_buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.generate_button = QPushButton("确认发送并生成勾选项")
        self.generate_button.setProperty("primary", True)
        self.cancel_generation_button = QPushButton("取消")
        self.cancel_generation_button.setEnabled(False)
        button_layout.addWidget(self.generate_button, 1)
        button_layout.addWidget(self.cancel_generation_button)
        form.addRow(generation_buttons)
        layout.addWidget(group)
        export_group = QGroupBox("本地导出")
        export_layout = QVBoxLayout(export_group)
        self.export_manifest_button = QPushButton(
            "导出清单、已生成图片和资产展示板…"
        )
        export_layout.addWidget(self.export_manifest_button)
        layout.addWidget(export_group)
        self.generation_list = QListWidget()
        self.generation_list.setMinimumHeight(240)
        layout.addWidget(self.generation_list)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setObjectName("generationPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setWidget(body)
        return scroll

    def _build_automatic_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 14, 16, 24)
        layout.setSpacing(14)
        intro = QLabel(
            "按当前拆分方案批量生成资产清单、单项概念图和分页展示板。"
            "运行结果独立保存，不写入“清单与校正”中的资产清单。"
        )
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        shared_note = QLabel(
            "模型、凭据与输出分辨率在“清单与校正”和“自动资产板”之间同步。"
            "开始前将显示调用次数上限和发送内容。"
        )
        shared_note.setWordWrap(True)
        layout.addWidget(shared_note)

        group = QGroupBox("批量生成设置")
        group.setObjectName("workflowSection")
        form = QFormLayout(group)
        form.setContentsMargins(14, 12, 14, 14)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.auto_vision_provider_combo = QComboBox()
        for provider in self._provider_registry.for_capability(
            ProviderCapability.VISION_REVIEW
        ):
            self.auto_vision_provider_combo.addItem(
                provider.manifest.display_name,
                provider.manifest.provider_id,
            )
        self.auto_vision_model_edit = QLineEdit()
        self.auto_vision_key_edit = QLineEdit()
        self.auto_vision_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.auto_image_provider_combo = QComboBox()
        for provider in self._provider_registry.for_capability(
            ProviderCapability.IMAGE_EDIT
        ):
            self.auto_image_provider_combo.addItem(
                provider.manifest.display_name,
                provider.manifest.provider_id,
            )
        self.auto_image_model_combo = QComboBox()
        self.auto_image_model_combo.setEditable(True)
        self.auto_image_model_edit = self.auto_image_model_combo.lineEdit()
        self.auto_image_key_edit = QLineEdit()
        self.auto_image_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.auto_asset_limit = QSpinBox()
        self.auto_asset_limit.setRange(1, 48)
        self.auto_asset_limit.setValue(16)
        self.auto_asset_limit.setToolTip(
            "一次最多生成的资产数量。每项通常会产生一次图片调用。"
        )
        self.auto_resolution_combo = QComboBox()
        for label, value in (
            ("1K（推荐）", "1K"),
            ("2K", "2K"),
            ("4K", "4K"),
        ):
            self.auto_resolution_combo.addItem(label, value)
        form.addRow("清单供应商", self.auto_vision_provider_combo)
        form.addRow("清单模型 ID", self.auto_vision_model_edit)
        form.addRow("清单 API Key", self.auto_vision_key_edit)
        form.addRow("图片供应商", self.auto_image_provider_combo)
        form.addRow("图片模型", self.auto_image_model_combo)
        form.addRow("图片 API Key", self.auto_image_key_edit)
        form.addRow("资产数量上限", self.auto_asset_limit)
        form.addRow("输出分辨率", self.auto_resolution_combo)
        self.auto_start_button = QPushButton(
            "检查发送内容并生成资产板"
        )
        self.auto_start_button.setProperty("primary", True)
        self.auto_cancel_button = QPushButton("取消")
        self.auto_cancel_button.setEnabled(False)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.auto_start_button, 1)
        row_layout.addWidget(self.auto_cancel_button)
        form.addRow(row)
        layout.addWidget(group)

        self.auto_status = QLabel("状态：未运行")
        self.auto_status.setWordWrap(True)
        layout.addWidget(self.auto_status)
        self.auto_run_list = QListWidget()
        self.auto_run_list.setMinimumHeight(132)
        self.auto_run_list.setMaximumHeight(180)
        layout.addWidget(self.auto_run_list)
        self.auto_board_preview = QLabel("资产板预览")
        self.auto_board_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.auto_board_preview.setMinimumHeight(260)
        self.auto_board_preview.setScaledContents(False)
        scroll = QScrollArea()
        scroll.setObjectName("assetBoardPreviewScroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.auto_board_preview)
        scroll.setMinimumHeight(340)
        layout.addWidget(scroll)
        self.auto_export_button = QPushButton("导出当前运行")
        self.auto_export_button.setEnabled(False)
        layout.addWidget(self.auto_export_button)
        layout.addStretch(1)
        page_scroll = QScrollArea()
        page_scroll.setObjectName("automaticPageScroll")
        page_scroll.setWidgetResizable(True)
        page_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        page_scroll.setWidget(body)
        return page_scroll

    def _connect_signals(self) -> None:
        self.canvas.file_dropped.connect(self._import_main_path)
        self.canvas.region_created.connect(self._manual_region_created)
        self.canvas.region_selected.connect(self._select_asset_by_id)
        self.canvas.regions_selected.connect(self._select_assets_by_ids)
        self.canvas.region_geometry_changed.connect(
            self._asset_geometry_changed
        )
        self.canvas.view_state_changed.connect(self._view_state_changed)
        self.region_mode_action.toggled.connect(self.canvas.set_region_mode)
        self.hide_regions_action.toggled.connect(
            lambda hidden: self._set_regions_visible(not hidden)
        )
        self.reset_view_action.triggered.connect(self.canvas.reset_view)
        self.vision_provider_combo.currentIndexChanged.connect(
            lambda _index: self._provider_changed(
                self.vision_provider_combo,
                self.vision_model_edit,
                self.vision_key_edit,
                ProviderCapability.VISION_REVIEW,
            )
        )
        self.image_provider_combo.currentIndexChanged.connect(
            lambda _index: self._provider_changed(
                self.image_provider_combo,
                self.image_model_edit,
                self.image_key_edit,
                ProviderCapability.IMAGE_EDIT,
                model_combo=self.image_model_combo,
            )
        )
        self.auto_vision_provider_combo.currentIndexChanged.connect(
            lambda _index: self._provider_changed(
                self.auto_vision_provider_combo,
                self.auto_vision_model_edit,
                self.auto_vision_key_edit,
                ProviderCapability.VISION_REVIEW,
            )
        )
        self.auto_image_provider_combo.currentIndexChanged.connect(
            lambda _index: self._provider_changed(
                self.auto_image_provider_combo,
                self.auto_image_model_edit,
                self.auto_image_key_edit,
                ProviderCapability.IMAGE_EDIT,
                model_combo=self.auto_image_model_combo,
            )
        )
        self._provider_changed(
            self.vision_provider_combo,
            self.vision_model_edit,
            self.vision_key_edit,
            ProviderCapability.VISION_REVIEW,
        )
        self._provider_changed(
            self.image_provider_combo,
            self.image_model_edit,
            self.image_key_edit,
            ProviderCapability.IMAGE_EDIT,
            model_combo=self.image_model_combo,
        )
        self._provider_changed(
            self.auto_vision_provider_combo,
            self.auto_vision_model_edit,
            self.auto_vision_key_edit,
            ProviderCapability.VISION_REVIEW,
        )
        self._provider_changed(
            self.auto_image_provider_combo,
            self.auto_image_model_edit,
            self.auto_image_key_edit,
            ProviderCapability.IMAGE_EDIT,
            model_combo=self.auto_image_model_combo,
        )
        for provider in self._provider_registry.for_capability(
            ProviderCapability.VISION_REVIEW
        ):
            self.prompt_panel.provider_combo.addItem(
                provider.manifest.display_name,
                provider.manifest.provider_id,
            )
        self.prompt_panel.provider_combo.currentIndexChanged.connect(
            lambda _index: self._provider_changed(
                self.prompt_panel.provider_combo,
                self.prompt_panel.model_edit,
                self.prompt_panel.key_edit,
                ProviderCapability.VISION_REVIEW,
            )
        )
        self._provider_changed(
            self.prompt_panel.provider_combo,
            self.prompt_panel.model_edit,
            self.prompt_panel.key_edit,
            ProviderCapability.VISION_REVIEW,
        )
        self.vision_provider_combo.currentIndexChanged.connect(
            lambda _index: self._sync_ai_controls("manual_vision")
        )
        self.auto_vision_provider_combo.currentIndexChanged.connect(
            lambda _index: self._sync_ai_controls("automatic_vision")
        )
        self.vision_model_edit.textChanged.connect(
            lambda _text: self._sync_ai_controls("manual_vision")
        )
        self.auto_vision_model_edit.textChanged.connect(
            lambda _text: self._sync_ai_controls("automatic_vision")
        )
        self.vision_key_edit.textChanged.connect(
            lambda _text: self._sync_ai_controls("manual_vision")
        )
        self.auto_vision_key_edit.textChanged.connect(
            lambda _text: self._sync_ai_controls("automatic_vision")
        )
        self.prompt_panel.provider_combo.currentIndexChanged.connect(
            lambda _index: self._sync_ai_controls("prompt_vision")
        )
        self.prompt_panel.model_edit.textChanged.connect(
            lambda _text: self._sync_ai_controls("prompt_vision")
        )
        self.prompt_panel.key_edit.textChanged.connect(
            lambda _text: self._sync_ai_controls("prompt_vision")
        )
        self.image_provider_combo.currentIndexChanged.connect(
            lambda _index: self._sync_ai_controls("manual_image")
        )
        self.auto_image_provider_combo.currentIndexChanged.connect(
            lambda _index: self._sync_ai_controls("automatic_image")
        )
        self.image_model_combo.currentTextChanged.connect(
            lambda _text: self._sync_ai_controls("manual_image")
        )
        self.auto_image_model_combo.currentTextChanged.connect(
            lambda _text: self._sync_ai_controls("automatic_image")
        )
        self.image_key_edit.textChanged.connect(
            lambda _text: self._sync_ai_controls("manual_image")
        )
        self.auto_image_key_edit.textChanged.connect(
            lambda _text: self._sync_ai_controls("automatic_image")
        )
        self.image_resolution_combo.currentIndexChanged.connect(
            lambda _index: self._sync_ai_controls("manual_image")
        )
        self.auto_resolution_combo.currentIndexChanged.connect(
            lambda _index: self._sync_ai_controls("automatic_image")
        )
        self._sync_ai_controls("manual_vision")
        self._sync_ai_controls("manual_image")
        self.title_edit.editingFinished.connect(self._save_fields)
        self.scene_type_combo.currentTextChanged.connect(
            lambda _value: self._save_fields()
        )
        self.goal_edit.textChanged.connect(self._mark_unsaved)
        self.notes_edit.textChanged.connect(self._mark_unsaved)
        self.asset_tree.itemSelectionChanged.connect(
            self._asset_selection_changed
        )
        self.understand_button.clicked.connect(
            self._start_scene_understanding
        )
        self.cancel_understanding_button.clicked.connect(
            self._cancel_analysis
        )
        self.plan_combo.currentIndexChanged.connect(
            lambda _index: self._plan_selection_changed(self.plan_combo)
        )
        self.context_plan_combo.currentIndexChanged.connect(
            lambda _index: self._plan_selection_changed(
                self.context_plan_combo
            )
        )
        self.edit_plan_button.clicked.connect(self._open_plan_editor)
        self.new_plan_button.clicked.connect(self._new_plan_from_preset)
        self.save_plan_button.clicked.connect(self._save_current_plan)
        self.delete_plan_button.clicked.connect(self._delete_current_plan)
        self.asset_tree.itemChanged.connect(self._asset_check_changed)
        self.add_asset_button.clicked.connect(self._enter_add_mode)
        self.split_asset_button.clicked.connect(self._split_selected)
        self.merge_asset_button.clicked.connect(self._merge_selected)
        self.delete_asset_button.clicked.connect(self._delete_selected)
        self.mask_button.clicked.connect(self._show_selected_mask)
        self.apply_detail_button.clicked.connect(self._apply_detail_edits)
        self.generate_button.clicked.connect(self._start_generation)
        self.cancel_generation_button.clicked.connect(
            self._cancel_generation
        )
        self.export_manifest_button.clicked.connect(self._export_package)
        self.auto_start_button.clicked.connect(
            self._start_automatic_pipeline
        )
        self.auto_cancel_button.clicked.connect(
            self._cancel_automatic_pipeline
        )
        self.auto_export_button.clicked.connect(
            self._export_automatic_run
        )
        self.auto_run_list.itemSelectionChanged.connect(
            lambda: (
                self._show_automatic_run(
                    str(
                        self.auto_run_list.currentItem().data(
                            Qt.ItemDataRole.UserRole
                        )
                    )
                )
                if self.auto_run_list.currentItem() is not None
                else None
            )
        )
        self.prompt_panel.save_key_button.clicked.connect(
            lambda: self._save_provider_key(
                self.prompt_panel.provider_combo,
                self.prompt_panel.key_edit,
            )
        )
        self.prompt_panel.initial_button.clicked.connect(
            self._start_prompt_initial
        )
        self.prompt_panel.iterate_button.clicked.connect(
            self._start_prompt_iteration
        )
        self.prompt_panel.cancel_button.clicked.connect(
            self._cancel_prompt_request
        )
        self.prompt_panel.new_session_button.clicked.connect(
            self._new_prompt_session
        )
        self.prompt_panel.session_combo.currentIndexChanged.connect(
            self._prompt_session_changed
        )
        self.prompt_panel.save_manual_button.clicked.connect(
            self._save_manual_prompt_revision
        )
        self.prompt_panel.copy_zh_button.clicked.connect(
            lambda: self._copy_prompt_text(
                self.prompt_panel.prompt_zh_edit.toPlainText(),
                "中文提示语已复制。",
            )
        )
        self.prompt_panel.copy_en_button.clicked.connect(
            lambda: self._copy_prompt_text(
                self.prompt_panel.prompt_en_edit.toPlainText(),
                "英文提示语已复制。",
            )
        )
        self.prompt_panel.copy_all_button.clicked.connect(
            lambda: self._copy_prompt_text(
                self.prompt_panel.complete_prompt_text(),
                "完整提示语已复制。",
            )
        )

    def _new_project(self) -> None:
        base = QFileDialog.getExistingDirectory(
            self,
            "选择资产拆分项目保存位置",
        )
        if not base:
            return
        title, accepted = QInputDialog.getText(
            self,
            "新建资产拆分项目",
            "项目名称：",
        )
        if not accepted:
            return
        folder_name = _safe_folder_name(title.strip() or "未命名资产拆分")
        root = Path(base) / f"{folder_name}{PROJECT_SUFFIX}"
        try:
            store = AssetBreakdownStore.create(root, title)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法新建项目", str(exc))
            return
        self._attach_store(store)

    def _open_project(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "打开 GATalk 资产拆分项目",
        )
        if not folder:
            return
        try:
            store = AssetBreakdownStore.open(folder)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法打开项目", str(exc))
            return
        self._attach_store(store)

    def open_path(self, path: str | Path) -> bool:
        try:
            store = AssetBreakdownStore.open(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法打开项目", str(exc))
            return False
        self._attach_store(store)
        return True

    def _attach_store(self, store: AssetBreakdownStore) -> None:
        if self._store is not None:
            self._store.close()
        self._store = store
        try:
            WorkspaceCatalogStore().remember(store.root)
        except (OSError, ValueError):
            pass
        self._state = store.state
        self._undo_stack.clear()
        self._restoring = True
        try:
            self.title_edit.setText(self._state.title)
            index = self.scene_type_combo.findData(self._state.scene_type)
            if index >= 0:
                self.scene_type_combo.setCurrentIndex(index)
            else:
                self.scene_type_combo.setEditText(self._state.scene_type)
            self.goal_edit.setPlainText(self._state.production_goal)
            self.notes_edit.setPlainText(self._state.notes)
            self.hide_regions_action.setChecked(
                not self._state.regions_visible
            )
            self._refresh_reference_list()
            self._refresh_handoff()
            self._refresh_understanding()
            self._refresh_plans()
            self._refresh_asset_tree()
            self._refresh_production_specs()
            self._refresh_generation_list()
            self._refresh_automatic_runs()
            self._refresh_prompt_sessions()
        finally:
            self._restoring = False
        self._load_main_image()
        self.statusBar().showMessage(f"已打开：{store.root}")

    def receive_workspace_handoff(
        self,
        handoff: object,
        *,
        target_root: Path | None = None,
    ) -> bool:
        if not isinstance(handoff, WorkspaceHandoff):
            QMessageBox.warning(self, "交接失败", "收到的工作台交接格式无效。")
            return False
        if handoff.content_type != "artwork_study_to_asset_breakdown":
            QMessageBox.warning(self, "交接失败", "该内容不能交给资产拆分工作台。")
            return False
        if target_root is None:
            base = QFileDialog.getExistingDirectory(
                self,
                "选择新资产拆分项目保存位置",
            )
            if not base:
                return False
            folder_name = _safe_folder_name(
                f"{handoff.source_project_title} 资产拆分"
            )
            target_root = Path(base) / f"{folder_name}{PROJECT_SUFFIX}"
        try:
            store = AssetBreakdownStore.create(
                target_root,
                f"{handoff.source_project_title} 资产拆分",
            )
            imported = store.import_image(handoff.primary_image_path, "main")
            if imported.sha256 != handoff.primary_image_sha256:
                store.close()
                raise ValueError("作品研究图片在交接期间发生了变化，请重新交接。")
            payload = dict(handoff.payload)
            snapshot = StudyHandoffSnapshot(
                handoff_id=str(uuid.uuid4()),
                source_module_id=handoff.source_module_id,
                source_project_id=handoff.source_project_id,
                source_project_title=handoff.source_project_title,
                source_project_path=str(
                    Path(handoff.primary_image_path).parent.parent
                ),
                source_image_sha256=handoff.primary_image_sha256,
                work_type=str(payload.get("work_type", "")),
                study_goal=str(payload.get("study_goal", "")),
                known_context=str(payload.get("known_context", "")),
                personal_notes=str(payload.get("personal_notes", "")),
                local_analysis=dict(payload.get("local_analysis", {})),
                ai_review=dict(payload.get("ai_review", {})),
                imported_at=utc_now(),
            )
            store.add_or_replace_handoff(snapshot)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法创建资产拆分项目", str(exc))
            return False
        self._attach_store(store)
        self.manual_tabs.setCurrentIndex(0)
        self.statusBar().showMessage(
            "作品研究已作为可编辑快照交接；原研究不会被资产拆分修改。",
            6000,
        )
        return True

    def _refresh_handoff(self) -> None:
        if self._state is None or not self._state.study_handoffs:
            self.handoff_summary.setText(
                "当前项目独立开始；也可在“作品研究”中点击“交给资产拆分”。"
            )
            self.handoff_adjustments.clear()
            return
        handoff = next(
            (
                item for item in self._state.study_handoffs
                if item.handoff_id == self._state.selected_handoff_id
            ),
            self._state.study_handoffs[-1],
        )
        current = (
            self._state.main_image is not None
            and handoff.source_image_sha256 == self._state.main_image.sha256
        )
        self.handoff_summary.setText(
            f"来源：{handoff.source_project_title} · {handoff.work_type or '未分类'}\n"
            f"研究目标：{handoff.study_goal or '未填写'}\n"
            f"图片哈希：{handoff.source_image_sha256[:12]}… · "
            f"{'当前有效' if current else '图片已变化，交接仅供参考'}"
        )
        self.handoff_adjustments.setPlainText(handoff.user_adjustments)

    def _refresh_understanding(self) -> None:
        if self._state is None or not self._state.scene_understandings:
            self.understanding_text.clear()
            self.understanding_corrections.clear()
            return
        item = next(
            (
                value for value in self._state.scene_understandings
                if value.understanding_id
                == self._state.selected_understanding_id
            ),
            self._state.scene_understandings[-1],
        )
        families = "\n".join(
            f"• {value.get('name', '')}：{value.get('role', '')}；"
            f"复用依据 {value.get('reuse_signal', '')}"
            for value in item.asset_families
        )
        self.understanding_text.setPlainText(
            f"场景原型\n{item.scene_archetype}\n\n"
            f"整体理解\n{item.summary}\n\n"
            f"空间结构\n{'；'.join(item.spatial_structure)}\n\n"
            f"生产系统\n{'；'.join(item.production_systems)}\n\n"
            f"资产族\n{families}\n\n"
            f"可见证据\n{'；'.join(item.visible_evidence)}\n\n"
            f"不确定性\n{'；'.join(item.uncertainties) or '无'}"
        )
        self.understanding_corrections.setPlainText(item.user_corrections)

    def _refresh_plans(self, select_id: str = "") -> None:
        combos = (self.plan_combo, self.context_plan_combo)
        for combo in combos:
            combo.blockSignals(True)
        try:
            for combo in combos:
                combo.clear()
            if self._state is None:
                return
            for plan in self._state.breakdown_plans:
                suffix = " · 已确认" if plan.status == "confirmed" else " · 草稿"
                for combo in combos:
                    combo.addItem(f"{plan.name}{suffix}", plan.plan_id)
            target = select_id or self._state.selected_plan_id
            for combo in combos:
                index = combo.findData(target)
                combo.setCurrentIndex(max(0, index))
        finally:
            for combo in combos:
                combo.blockSignals(False)
        plan = self._selected_plan()
        self._populate_plan_fields(plan)
        self._update_basis_views(plan)

    def _selected_plan(self) -> BreakdownPlan | None:
        if self._state is None:
            return None
        plan_id = self._state.selected_plan_id
        return next(
            (item for item in self._state.breakdown_plans if item.plan_id == plan_id),
            None,
        )

    def _plan_depth_summary(self, plan: BreakdownPlan) -> str:
        values = [
            f"{CATEGORY_LABELS[category]} {depth}"
            for category, depth in plan.category_depths.items()
            if depth > 0
        ]
        if len(values) > 4:
            return "、".join(values[:4]) + f" 等 {len(values)} 类"
        return "、".join(values) or "未纳入任何类别"

    def _update_basis_views(self, plan: BreakdownPlan | None) -> None:
        if plan is None:
            self.context_plan_status.setText("未选择方案")
            self.context_plan_status.setProperty("tone", "warning")
            if hasattr(self, "prompt_panel"):
                self.prompt_panel.set_basis(
                    "运行依据：未选择拆分方案。",
                    stale=True,
                )
            return
        understanding = (
            "已关联场景结构"
            if plan.source_understanding_id
            else "未关联场景结构"
        )
        self.context_plan_status.setText(
            f"{understanding} · "
            f"{'已确认' if plan.status == 'confirmed' else '草稿'}"
        )
        self.context_plan_status.setToolTip(
            f"类别深度：{self._plan_depth_summary(plan)}"
        )
        self.context_plan_status.setProperty(
            "tone",
            "success" if plan.status == "confirmed" else "warning",
        )
        self.context_plan_status.style().unpolish(self.context_plan_status)
        self.context_plan_status.style().polish(self.context_plan_status)
        if hasattr(self, "prompt_panel"):
            self.prompt_panel.set_basis(
                f"运行依据：{plan.name} · {self._plan_depth_summary(plan)}"
                f" · {'已确认' if plan.status == 'confirmed' else '草稿'}",
                stale=plan.status != "confirmed",
            )

    def _open_plan_editor(self) -> None:
        self.workflow_tabs.setCurrentIndex(0)
        self.manual_tabs.setCurrentIndex(0)

    def _populate_plan_fields(self, plan: BreakdownPlan | None) -> None:
        if plan is None:
            self.plan_status.setText("状态：未选择方案")
            return
        self.plan_name_edit.setText(plan.name)
        self.plan_purpose_edit.setPlainText(plan.purpose)
        self.plan_notes_edit.setPlainText(plan.user_notes)
        preset_index = self.plan_preset_combo.findData(plan.preset_id)
        if preset_index >= 0:
            self.plan_preset_combo.setCurrentIndex(preset_index)
        grouping_index = self.plan_grouping_combo.findData(
            plan.grouping_strategy
        )
        self.plan_grouping_combo.setCurrentIndex(max(0, grouping_index))
        self.plan_page_limit.setValue(plan.max_items_per_page)
        for category, combo in self.plan_depth_combos.items():
            index = combo.findData(int(plan.category_depths.get(category, 0)))
            combo.setCurrentIndex(max(0, index))
        included = "、".join(
            CATEGORY_LABELS[item] for item in plan.included_categories
        )
        self.plan_status.setText(
            f"状态：{('已确认' if plan.status == 'confirmed' else '草稿')} · "
            f"纳入 {included or '无'}。新清单、资产板和提示语均采用此方案。"
        )

    def _plan_selection_changed(self, source: QComboBox) -> None:
        if self._restoring or self._store is None:
            return
        plan_id = str(source.currentData() or "")
        plan = next(
            (
                item
                for item in self._store.state.breakdown_plans
                if item.plan_id == plan_id
            ),
            None,
        )
        if plan is None:
            return
        self._store.select_plan(plan.plan_id)
        self._state = self._store.state
        for combo in (self.plan_combo, self.context_plan_combo):
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(plan.plan_id)))
            combo.blockSignals(False)
        self._populate_plan_fields(plan)
        self._update_basis_views(plan)
        self._refresh_asset_tree()
        self._refresh_overlays()
        self._refresh_generation_list()
        self._refresh_automatic_runs()
        self._refresh_prompt_sessions()

    def _new_plan_from_preset(self) -> None:
        if self._store is None:
            QMessageBox.information(self, "请先新建项目", "请先新建或打开项目。")
            return
        preset_id = str(self.plan_preset_combo.currentData())
        understanding_id = (
            self._state.selected_understanding_id if self._state else ""
        )
        plan = create_plan_from_preset(
            preset_id,
            understanding_id=understanding_id,
        )
        self._store.add_or_replace_plan(plan)
        self._state = self._store.state
        self._refresh_plans(plan.plan_id)
        self._refresh_asset_tree()

    def _save_current_plan(self) -> None:
        if self._store is None or self._state is None:
            return
        plan = self._selected_plan()
        if plan is None:
            return
        depths = {
            category: int(combo.currentData())
            for category, combo in self.plan_depth_combos.items()
        }
        plan = replace(
            plan,
            name=self.plan_name_edit.text().strip() or "未命名拆分方案",
            purpose=self.plan_purpose_edit.toPlainText().strip(),
            preset_id=str(self.plan_preset_combo.currentData() or "custom_mixed"),
            category_depths=depths,
            grouping_strategy=str(self.plan_grouping_combo.currentData()),
            max_items_per_page=self.plan_page_limit.value(),
            source_understanding_id=self._state.selected_understanding_id,
        )
        plan = confirm_plan(
            plan,
            notes=self.plan_notes_edit.toPlainText().strip(),
        )
        self._store.add_or_replace_plan(plan)
        if self._state.selected_understanding_id:
            understanding = next(
                (
                    item for item in self._store.state.scene_understandings
                    if item.understanding_id
                    == self._state.selected_understanding_id
                ),
                None,
            )
            if understanding is not None:
                self._store.add_or_replace_scene_understanding(
                    replace(
                        understanding,
                        user_corrections=(
                            self.understanding_corrections
                            .toPlainText()
                            .strip()
                        ),
                        user_confirmed=True,
                    )
                )
        if self._state.selected_handoff_id:
            handoff = next(
                (
                    item for item in self._store.state.study_handoffs
                    if item.handoff_id == self._state.selected_handoff_id
                ),
                None,
            )
            if handoff is not None:
                self._store.add_or_replace_handoff(
                    replace(
                        handoff,
                        user_adjustments=(
                            self.handoff_adjustments.toPlainText().strip()
                        ),
                    )
                )
        self._state = self._store.state
        self._refresh_plans(plan.plan_id)
        self.plan_status.setText(
            "状态：方案已保存。清单、自动资产板和新提示语将采用此版本。"
        )

    def _delete_current_plan(self) -> None:
        if self._store is None:
            return
        plan = self._selected_plan()
        if plan is None:
            return
        if QMessageBox.question(
            self,
            "删除拆分方案",
            "将同时删除该方案的资产清单、生成记录和展示板记录。继续吗？",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._store.delete_plan(plan.plan_id)
        except ValueError as exc:
            QMessageBox.information(self, "不能删除", str(exc))
            return
        self._state = self._store.state
        self._refresh_plans()
        self._refresh_asset_tree()
        self._refresh_overlays()

    def _save_fields(self) -> None:
        if self._store is None or self._state is None or self._restoring:
            return
        scene_type = self.scene_type_combo.currentData()
        if scene_type is None:
            scene_type = self.scene_type_combo.currentText().strip()
        self._state = replace(
            self._state,
            title=self.title_edit.text().strip() or "未命名资产拆分项目",
            scene_type=str(scene_type or "general_environment"),
            production_goal=self.goal_edit.toPlainText().strip(),
            notes=self.notes_edit.toPlainText().strip(),
        )
        self._store.save(self._state)
        self._state = self._store.state
        self.statusBar().showMessage("资产拆分项目已保存。", 2500)

    def _mark_unsaved(self) -> None:
        if not self._restoring and self._store is not None:
            self.statusBar().showMessage("有未保存的文字修改；按 Ctrl+S 保存。")

    def _choose_main_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "导入场景原画",
            filter="图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if path:
            self._import_main_path(path)

    def _choose_reference_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "导入补充参考",
            filter="图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        if self._store is None:
            QMessageBox.information(self, "请先新建项目", "请先新建或打开项目。")
            return
        try:
            self._store.import_image(path, "reference")
            self._state = self._store.state
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self._refresh_reference_list()
        self.statusBar().showMessage("补充参考已导入，原始字节未被修改。", 3000)

    def _import_main_path(self, path: str) -> None:
        if self._store is None:
            QMessageBox.information(self, "请先新建项目", "请先新建或打开项目。")
            return
        if self._state and self._state.main_image is not None:
            result = QMessageBox.question(
                self,
                "替换主原画",
                "替换主原画会清空当前 AI 清单和生成记录，但不会修改原文件。继续吗？",
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        try:
            self._store.import_image(path, "main")
            self._state = self._store.state
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self._refresh_asset_tree()
        self._refresh_generation_list()
        self._refresh_automatic_runs()
        self._refresh_prompt_sessions()
        self._undo_stack.clear()
        self._load_main_image()

    def _load_main_image(self) -> None:
        if (
            self._store is None
            or self._state is None
            or self._state.main_image is None
        ):
            self._loaded = None
            self.canvas.clear_image()
            return
        path = self._store.image_path(self._state.main_image)
        self._start_worker(
            "load",
            lambda: load_image(path),
            self._main_loaded,
        )
        self.statusBar().showMessage("正在读取主原画…")

    def _main_loaded(self, result: object) -> None:
        loaded = result
        if not isinstance(loaded, LoadedImage):
            return
        self._loaded = loaded
        self.canvas.set_image(numpy_to_qimage(loaded.rgb), reset_view=True)
        if self._state is not None:
            self.canvas.apply_external_view_state(
                self._state.zoom_factor,
                self._state.center_x,
                self._state.center_y,
            )
        self._refresh_overlays()
        self.statusBar().showMessage(
            f"主原画已加载：{loaded.working_size[0]} × "
            f"{loaded.working_size[1]}；原文件只读。",
            3500,
        )

    def _review_material(
        self,
    ) -> tuple[tuple[ProviderImage, ...], tuple[dict, ...], dict]:
        if self._loaded is None or self._state is None:
            raise ValueError("请先导入一张场景原画。")
        images = [
            prepare_provider_image(
                self._loaded,
                "main_concept",
                ProviderImageExportOptions(maximum_side=2048),
            )
        ]
        supplemental = []
        if self._store is not None:
            references = [
                image
                for image in self._state.source_images
                if image.role == "reference"
            ][:3]
            for index, reference in enumerate(references, start=1):
                loaded = load_image(self._store.image_path(reference))
                role = f"supplemental_reference_{index}"
                images.append(
                    prepare_provider_image(
                        loaded,
                        role,
                        ProviderImageExportOptions(maximum_side=1536),
                    )
                )
                supplemental.append(
                    {
                        "role": role,
                        "sha256": reference.sha256,
                        "filename_hidden": True,
                    }
                )
        metadata = {
            "width": self._loaded.working_size[0],
            "height": self._loaded.working_size[1],
            "exif_orientation_applied": (
                self._loaded.exif_orientation_applied
            ),
            "icc_converted_to_srgb": self._loaded.icc_converted_to_srgb,
            "assumed_srgb": self._loaded.assumed_srgb,
        }
        return tuple(images), tuple(supplemental), metadata

    def _study_handoff_for_ai(self) -> dict:
        if self._state is None or not self._state.study_handoffs:
            return {}
        handoff = next(
            (
                item for item in self._state.study_handoffs
                if item.handoff_id == self._state.selected_handoff_id
            ),
            self._state.study_handoffs[-1],
        )
        dimensions = []
        for item in handoff.ai_review.get("dimension_studies", ())[:12]:
            if isinstance(item, dict):
                dimensions.append(
                    {
                        "dimension_id": item.get("dimension_id", ""),
                        "observation": item.get("observation", ""),
                        "visual_evidence": list(
                            item.get("visual_evidence", ())
                        )[:3],
                        "learning_points": list(
                            item.get("learning_points", ())
                        )[:3],
                    }
                )
        return {
            "source_project_title": handoff.source_project_title,
            "source_image_sha256": handoff.source_image_sha256,
            "work_type": handoff.work_type,
            "study_goal": handoff.study_goal,
            "known_context": handoff.known_context,
            "personal_notes": handoff.personal_notes,
            "user_adjustments": self.handoff_adjustments.toPlainText().strip(),
            "overall_reading": handoff.ai_review.get("overall_reading", ""),
            "dimension_studies": dimensions,
            "local_analysis_summary": handoff.local_analysis.get("summary", ""),
        }

    def _start_scene_understanding(self) -> None:
        if self._loaded is None or self._state is None:
            QMessageBox.information(self, "缺少主原画", "请先导入一张场景原画。")
            return
        self._save_fields()
        provider_id = str(self.vision_provider_combo.currentData())
        provider = self._provider_registry.get(provider_id)
        credential = self.vision_key_edit.text().strip()
        if provider_id != "mock" and not credential:
            QMessageBox.information(
                self,
                "缺少 API Key",
                "请输入 API Key，或选择“离线 Mock”只验证流程。",
            )
            return
        try:
            images, supplemental, metadata = self._review_material()
        except ValueError as exc:
            QMessageBox.information(self, "无法理解场景", str(exc))
            return
        profile = self._current_profile()
        context = AssetBreakdownAdvisoryContext(
            project_id=self._state.project_id,
            title=self._state.title,
            scene_type=self._state.scene_type,
            production_goal=self._state.production_goal,
            image_metadata=metadata,
            scene_focus=tuple(profile.get("focus", ())),
            supplemental_references=supplemental,
            study_handoff=self._study_handoff_for_ai(),
            user_corrections=(
                self.understanding_corrections.toPlainText().strip()
            ),
        )
        request = self._advisor.create_request(
            context,
            images,
            model_id=self.vision_model_edit.text().strip() or None,
            user_initiated=True,
            disclosure_confirmed=True,
        )
        preview = disclosure_preview(provider.manifest, request)
        dialog = SendDisclosureDialog(
            preview,
            purpose="场景理解与拆分建议",
            extra_notice=(
                "本次只生成场景理解和拆分方案，不生成图片，也不直接改写资产清单。"
                "作品研究的本地路径不会发送。"
            ),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cancellation = CancellationToken()
        self._ai_cancellation = cancellation
        self.understand_button.setEnabled(False)
        self.cancel_understanding_button.setEnabled(True)
        self.statusBar().showMessage("正在分析场景结构与拆分策略…")
        project_id = self._state.project_id
        source_hash = self._state.main_image.sha256

        def operation():
            execution = self._execution.run_review_with_model_fallback(
                provider,
                request,
                credential,
                cancellation,
                provider.manifest.fallback_models_for(
                    ProviderCapability.VISION_REVIEW,
                    request.model_id,
                ),
            )
            output = self._advisor.validate_output(
                execution.response.output
            )
            return {
                "project_id": project_id,
                "source_hash": source_hash,
                "output": output,
                "execution": execution,
            }

        self._start_worker(
            "advisory",
            operation,
            self._scene_understanding_finished,
        )

    def _scene_understanding_finished(self, result: object) -> None:
        self._ai_cancellation = None
        self.understand_button.setEnabled(True)
        self.cancel_understanding_button.setEnabled(False)
        if (
            not isinstance(result, dict)
            or self._store is None
            or self._state is None
            or self._state.main_image is None
        ):
            return
        if (
            result["project_id"] != self._state.project_id
            or result["source_hash"] != self._state.main_image.sha256
        ):
            self.statusBar().showMessage(
                "项目或主原画已经切换，旧的场景理解结果已忽略。",
                5000,
            )
            return
        output = result["output"]
        execution = result["execution"]
        understanding = understanding_from_ai(
            output["scene_understanding"],
            source_image_sha256=self._state.main_image.sha256,
            provider_id=execution.response.provider_id,
            model_id=execution.response.model_id,
            analyzer_version=self._advisor.descriptor.version,
        )
        self._store.add_scene_understanding(understanding)
        plans = tuple(
            plan_from_ai(
                item,
                understanding_id=understanding.understanding_id,
            )
            for item in output["recommended_plans"]
        )
        for plan in plans:
            self._store.add_or_replace_plan(plan)
        if plans:
            self._store.select_plan(plans[0].plan_id)
        self._store.append_ai_run(
            {
                "run_id": str(uuid.uuid4()),
                "module_id": "scenelens.asset_breakdown",
                "reviewer_id": "asset_breakdown_advisory",
                "reviewer_version": self._advisor.descriptor.version,
                "provider_id": execution.response.provider_id,
                "model_id": execution.response.model_id,
                "input_hashes": {"main": self._state.main_image.sha256},
                "parameters": {
                    "scene_type": self._state.scene_type,
                    "handoff_used": bool(self._study_handoff_for_ai()),
                },
                "result_summary": {
                    "understanding_id": understanding.understanding_id,
                    "recommended_plan_ids": [item.plan_id for item in plans],
                },
                "created_at": utc_now(),
            }
        )
        self._state = self._store.state
        self._refresh_understanding()
        self._refresh_plans(plans[0].plan_id if plans else "")
        self.statusBar().showMessage(
            f"场景理解完成；已生成 {len(plans)} 套可编辑建议。",
            6000,
        )

    def _start_ai_breakdown(self) -> None:
        if self._loaded is None or self._state is None:
            QMessageBox.information(self, "缺少主原画", "请先导入一张场景原画。")
            return
        self._save_fields()
        plan = self._selected_plan()
        if plan is None:
            QMessageBox.information(
                self,
                "缺少拆分方案",
                "请先在“拆分依据”中建立方案。",
            )
            return
        if plan.status != "confirmed":
            QMessageBox.information(
                self,
                "方案尚未确认",
                "请先检查各类别拆分深度，然后选择“保存方案”。",
            )
            return
        provider_id = str(self.vision_provider_combo.currentData())
        provider = self._provider_registry.get(provider_id)
        credential = self.vision_key_edit.text().strip()
        if provider_id != "mock" and not credential:
            QMessageBox.information(
                self,
                "缺少 API Key",
                "请输入 API Key，或选择“离线 Mock”只验证流程。",
            )
            return
        main = prepare_provider_image(
            self._loaded,
            "main_concept",
            ProviderImageExportOptions(maximum_side=2048),
        )
        images = [main]
        supplemental = []
        if self._store is not None:
            references = [
                image
                for image in self._state.source_images
                if image.role == "reference"
            ][:3]
            for index, reference in enumerate(references, start=1):
                loaded = load_image(self._store.image_path(reference))
                images.append(
                    prepare_provider_image(
                        loaded,
                        f"supplemental_reference_{index}",
                        ProviderImageExportOptions(maximum_side=1536),
                    )
                )
                supplemental.append(
                    {
                        "role": f"supplemental_reference_{index}",
                        "sha256": reference.sha256,
                        "filename_hidden": True,
                    }
                )
        profile = self._current_profile()
        context = AssetBreakdownContext(
            project_id=self._state.project_id,
            title=self._state.title,
            scene_type=self._state.scene_type,
            scene_focus=tuple(profile.get("focus", ())),
            production_goal=self._state.production_goal,
            image_metadata={
                "width": self._loaded.working_size[0],
                "height": self._loaded.working_size[1],
                "exif_orientation_applied": (
                    self._loaded.exif_orientation_applied
                ),
                "icc_converted_to_srgb": self._loaded.icc_converted_to_srgb,
                "assumed_srgb": self._loaded.assumed_srgb,
            },
            supplemental_references=tuple(supplemental),
            scene_understanding=(
                next(
                    (
                        item.to_dict()
                        for item in self._state.scene_understandings
                        if item.understanding_id
                        == plan.source_understanding_id
                    ),
                    {},
                )
            ),
            breakdown_plan=plan.to_dict(),
            study_handoff=self._study_handoff_for_ai(),
        )
        request = self._reviewer.create_request(
            context,
            tuple(images),
            model_id=self.vision_model_edit.text().strip() or None,
            user_initiated=True,
            disclosure_confirmed=True,
        )
        preview = disclosure_preview(provider.manifest, request)
        dialog = SendDisclosureDialog(
            preview,
            purpose="资产拆分",
            extra_notice=(
                "临时断线、超时或服务繁忙时最多重试 3 次；Gemini JSON"
                " 截断时最多进行一次结构修复，可能产生额外调用费用。"
            ),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cancellation = CancellationToken()
        self._ai_cancellation = cancellation
        self.analyze_button.setEnabled(False)
        self.cancel_analysis_button.setEnabled(True)
        self.statusBar().showMessage("正在生成结构化资产清单…")
        project_id = self._state.project_id
        source_hash = self._state.main_image.sha256
        plan_snapshot = plan

        def operation():
            execution = self._execution.run_review_with_model_fallback(
                provider,
                request,
                credential,
                cancellation,
                provider.manifest.fallback_models_for(
                    ProviderCapability.VISION_REVIEW,
                    request.model_id,
                ),
            )
            output, repair_notes = self._reviewer.normalize_output(
                execution.response.output
            )
            return {
                "project_id": project_id,
                "source_hash": source_hash,
                "plan": plan_snapshot,
                "output": output,
                "repair_notes": repair_notes,
                "execution": execution,
            }

        self._start_worker("ai", operation, self._ai_breakdown_finished)

    def _ai_breakdown_finished(self, result: object) -> None:
        self._ai_cancellation = None
        self.analyze_button.setEnabled(True)
        self.cancel_analysis_button.setEnabled(False)
        if (
            not isinstance(result, dict)
            or self._store is None
            or self._state is None
        ):
            return
        main = self._state.main_image
        if main is None:
            return
        if (
            result["project_id"] != self._state.project_id
            or result["source_hash"] != main.sha256
            or result["plan"].plan_id != self._state.selected_plan_id
        ):
            self.statusBar().showMessage(
                "项目、原画或拆分方案已经切换，旧的后台清单结果已忽略。",
                6000,
            )
            return
        output = result["output"]
        repair_notes = result["repair_notes"]
        execution = result["execution"]
        plan = result["plan"]
        incoming = tuple(
            asset_from_ai(
                item,
                source_image_id=main.image_id,
                plan_id=plan.plan_id,
            )
            for item in output["assets"]
            if int(
                plan.category_depths.get(
                    str(item.get("category", "unknown")),
                    0,
                )
            ) > 0
            and int(item.get("level", 0)) <= int(
                plan.category_depths.get(
                    str(item.get("category", "unknown")),
                    0,
                )
            )
        )
        assets = merge_ai_assets(
            self._state.assets,
            incoming,
            active_plan_id=plan.plan_id,
        )
        self._store.replace_assets(assets)
        self._store.append_ai_run(
            {
                "run_id": str(uuid.uuid4()),
                "module_id": "scenelens.asset_breakdown",
                "reviewer_id": "asset_breakdown_review",
                "reviewer_version": self._reviewer.descriptor.version,
                "provider_id": execution.response.provider_id,
                "model_id": execution.response.model_id,
                "input_hashes": {
                    "main": main.sha256,
                    "references": [
                        image.sha256
                        for image in self._state.source_images
                        if image.role == "reference"
                    ],
                },
                "parameters": {
                    "scene_type": self._state.scene_type,
                    "max_output_tokens": self._reviewer.max_output_tokens,
                    "breakdown_plan": plan.to_dict(),
                },
                "result_summary": {
                    "scene_understanding": output["scene_understanding"],
                    "production_strategy": output["production_strategy"],
                    "relationships": output["relationships"],
                    "uncertainties": output["uncertainties"],
                    "structure_repairs": list(repair_notes),
                },
                "created_at": utc_now(),
            }
        )
        self._state = self._store.state
        self._refresh_asset_tree()
        self._refresh_overlays()
        if repair_notes:
            repair_text = "；".join(repair_notes)
            self.statusBar().showMessage(
                f"资产拆分完成：{len(incoming)} 项；已安全修复返回结构。",
                8000,
            )
            QMessageBox.information(
                self,
                "资产清单已完成结构修复",
                "资产内容已经保留。GATalk 只修复了无法成立的结构引用：\n"
                f"{repair_text}\n\n"
                "请检查资产树的父子层级；修复记录已写入本次分析记录。",
            )
        else:
            self.statusBar().showMessage(
                f"资产清单已生成：{len(incoming)} 项；推断内容待人工确认。",
                5000,
            )

    def _cancel_analysis(self) -> None:
        if self._ai_cancellation is not None:
            self._ai_cancellation.cancel()
            self.statusBar().showMessage("正在取消分析请求…")

    def _enter_add_mode(self) -> None:
        if self._loaded is None:
            QMessageBox.information(self, "缺少主原画", "请先导入主原画。")
            return
        self.region_mode_action.setChecked(True)
        self.statusBar().showMessage("在原画上拖出矩形以新增资产；按 Esc 退出。")

    def _manual_region_created(self, rect: object) -> None:
        if self._store is None or self._state is None:
            return
        main = self._state.main_image
        if main is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            "新增资产",
            "资产名称：",
        )
        if not accepted:
            return
        asset = create_manual_asset(
            name=name,
            category="unknown",
            rect=tuple(float(value) for value in rect),
            source_image_id=main.image_id,
            plan_id=self._state.selected_plan_id,
        )
        self._push_asset_state(
            (*self._state.assets, asset),
            self._state.generations,
            select_id=asset.asset_id,
            text="新增资产",
        )

    def _split_selected(self) -> None:
        asset = self._selected_asset()
        if asset is None or self._store is None or self._state is None:
            return
        children = split_asset(asset)
        assets = tuple(
            item for item in self._state.assets if item.asset_id != asset.asset_id
        ) + children
        self._push_asset_state(
            assets,
            self._state.generations,
            select_id=children[0].asset_id,
            text="拆分资产",
        )

    def _merge_selected(self) -> None:
        selected = self._selected_assets()
        if len(selected) < 2 or self._store is None or self._state is None:
            QMessageBox.information(
                self,
                "选择不足",
                "请在清单中选择至少两个资产后再合并。",
            )
            return
        name, accepted = QInputDialog.getText(
            self,
            "合并资产",
            "合并后的名称：",
        )
        if not accepted:
            return
        merged = merge_assets(
            tuple(selected),
            name=name,
            category=selected[0].category,
        )
        selected_ids = {item.asset_id for item in selected}
        assets = tuple(
            item for item in self._state.assets if item.asset_id not in selected_ids
        ) + (merged,)
        retained_generations = tuple(
            item
            for item in self._state.generations
            if item.asset_id not in selected_ids
        )
        self._push_asset_state(
            assets,
            retained_generations,
            select_id=merged.asset_id,
            text="合并资产",
        )

    def _delete_selected(self) -> None:
        selected = self._selected_assets()
        if not selected or self._store is None:
            return
        result = QMessageBox.question(
            self,
            "删除资产",
            f"删除选中的 {len(selected)} 项资产及其生成记录吗？原图不会受影响。",
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        selected_ids = {asset.asset_id for asset in selected}
        assets = tuple(
            replace(asset, parent_asset_id="")
            if asset.parent_asset_id in selected_ids
            else asset
            for asset in self._state.assets
            if asset.asset_id not in selected_ids
        )
        generations = tuple(
            item
            for item in self._state.generations
            if item.asset_id not in selected_ids
        )
        self._push_asset_state(
            assets,
            generations,
            text="删除资产",
        )

    def _apply_detail_edits(self) -> None:
        asset = self._selected_asset()
        if asset is None or self._store is None:
            return
        category = self.detail_category.currentData()
        if category is None:
            category = self.detail_category.currentText().strip()
        updated = asset.user_edit(
            updated_at=utc_now(),
            name=self.detail_name.text().strip() or asset.name,
            category=str(category or "unknown"),
            semantic_type=self.detail_semantic.text().strip(),
            parent_asset_id=self.detail_parent.text().strip(),
            reuse_group=self.detail_reuse.text().strip(),
            production_priority=str(
                self.detail_priority.currentData() or "medium"
            ),
            visible_evidence=self.detail_evidence.toPlainText().strip(),
            inferred_details=self.detail_inference.toPlainText().strip(),
            uncertainty=self.detail_uncertainty.toPlainText().strip(),
            production_strategy=self.detail_strategy.toPlainText().strip(),
            material_notes=self.detail_material.toPlainText().strip(),
            evidence_kind="user_added",
        )
        assets = tuple(
            updated if item.asset_id == updated.asset_id else item
            for item in self._state.assets
        )
        self._push_asset_state(
            assets,
            self._state.generations,
            select_id=updated.asset_id,
            text="修改资产",
        )
        self.statusBar().showMessage("人工修订已保存，后续分析不会覆盖。", 3000)

    def _asset_geometry_changed(self, asset_id: str, rect: object) -> None:
        if self._store is None or self._state is None:
            return
        asset = self._asset_by_id(asset_id)
        if asset is None:
            return
        updated = asset.user_edit(
            updated_at=utc_now(),
            normalized_rect=tuple(float(value) for value in rect),
            evidence_kind="user_added",
            mask_relative_path="",
            mask_method="",
        )
        assets = tuple(
            updated if item.asset_id == asset_id else item
            for item in self._state.assets
        )
        self._push_asset_state(
            assets,
            self._state.generations,
            select_id=asset_id,
            text="移动或缩放资产框",
        )

    def _show_selected_mask(self) -> None:
        asset = self._selected_asset()
        if asset is None or self._loaded is None:
            return
        self.statusBar().showMessage("正在生成可见像素遮罩…")
        self._start_worker(
            "mask",
            lambda: visible_asset_mask(
                self._loaded.rgb,
                asset.normalized_rect,
            ),
            lambda result: self._mask_finished(asset.asset_id, result),
        )

    def _mask_finished(self, asset_id: str, result: object) -> None:
        if (
            self._store is None
            or self._state is None
            or self._loaded is None
        ):
            return
        mask, method = result
        asset = self._asset_by_id(asset_id)
        if asset is None:
            return
        buffer = BytesIO()
        Image.fromarray(mask, mode="L").save(buffer, format="PNG")
        relative = f"artifacts/masks/{asset_id}.png"
        self._store.save_artifact(relative, buffer.getvalue())
        updated = replace(
            asset,
            mask_relative_path=relative,
            mask_method=method,
            updated_at=utc_now(),
        )
        self._store.add_or_replace_asset(updated)
        self._state = self._store.state
        dimmed = (self._loaded.rgb.astype(np.float32) * 0.22).astype(np.uint8)
        display = np.where(mask[:, :, None] > 0, self._loaded.rgb, dimmed)
        self.canvas.set_overlay(numpy_to_qimage(display))
        self.statusBar().showMessage(
            "已显示可见像素遮罩。它是算法近似，不包含被遮挡部分；按 Esc 退出。",
            5000,
        )

    def _start_generation(self) -> None:
        if (
            self._store is None
            or self._state is None
            or self._loaded is None
            or self._state.main_image is None
        ):
            QMessageBox.information(self, "缺少项目图片", "请先导入主原画。")
            return
        selected = tuple(
            asset
            for asset in self._state.assets
            if asset.selected_for_generation
            and asset.plan_id == self._state.selected_plan_id
        )
        if not selected:
            QMessageBox.information(
                self,
                "未勾选资产",
                "请在资产清单第一列勾选需要生成的资产。",
            )
            return
        provider_id = str(self.image_provider_combo.currentData())
        provider = self._provider_registry.get(provider_id)
        credential = self.image_key_edit.text().strip()
        if provider_id != "mock" and not credential:
            QMessageBox.information(
                self,
                "缺少 API Key",
                "请输入图片供应商 API Key，或选择离线 Mock 验证流程。",
            )
            return
        output_kind = str(self.generation_kind_combo.currentData())
        first_asset = selected[0]
        first_mask = np.zeros(self._loaded.rgb.shape[:2], dtype=np.uint8)
        left, top, width, height = normalized_rect_to_pixels(
            first_asset.normalized_rect,
            self._loaded.rgb.shape,
        )
        first_mask[top : top + height, left : left + width] = 255
        first_crop = asset_crop_png(self._loaded.rgb, first_asset, first_mask)
        preview_instruction = asset_generation_instruction(
            first_asset.to_dict(),
            output_kind=output_kind,
            scene_type=self._state.scene_type,
        )
        preview_instruction["output_resolution"] = str(
            self.image_resolution_combo.currentData() or "1K"
        )
        preview_request = ImageEditRequest(
            instruction=preview_instruction,
            images=(
                prepare_provider_image(
                    self._loaded,
                    "full_scene_context",
                    ProviderImageExportOptions(maximum_side=2048),
                ),
                ProviderImage(
                    "asset_visible_crop",
                    "image/png",
                    first_crop,
                ),
            ),
            model_id=_combo_model_id(self.image_model_combo),
            change_budget=35,
            user_initiated=True,
            disclosure_confirmed=True,
            timeout_seconds=240.0,
        )
        preview = disclosure_preview(provider.manifest, preview_request)
        dialog = SendDisclosureDialog(
            preview,
            purpose="资产图片生成",
            extra_notice=(
                f"本次共 {len(selected)} 个资产，将按顺序分别调用；已完成项会"
                "立即保留，单项失败不会丢失其他成功结果。生成会产生费用。"
            ),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cancellation = CancellationToken()
        self._image_cancellation = cancellation
        self.generate_button.setEnabled(False)
        self.cancel_generation_button.setEnabled(True)
        full_scene = preview_request.images[0]
        source_hash = self._state.main_image.sha256
        scene_type = self._state.scene_type
        model_id = _combo_model_id(self.image_model_combo)
        image_resolution = str(
            self.image_resolution_combo.currentData() or "1K"
        )
        self.statusBar().showMessage(
            f"正在生成 {len(selected)} 个资产；可以取消，已完成项会保留…"
        )

        def operation():
            successes = []
            failures = []
            for asset in selected:
                if cancellation.cancelled:
                    break
                mask, method = visible_asset_mask(
                    self._loaded.rgb,
                    asset.normalized_rect,
                )
                crop = asset_crop_png(self._loaded.rgb, asset, mask)
                instruction = asset_generation_instruction(
                    asset.to_dict(),
                    output_kind=output_kind,
                    scene_type=scene_type,
                )
                instruction["output_resolution"] = image_resolution
                request = ImageEditRequest(
                    instruction=instruction,
                    images=(
                        full_scene,
                        ProviderImage(
                            "asset_visible_crop",
                            "image/png",
                            crop,
                        ),
                    ),
                    model_id=model_id,
                    change_budget=35,
                    user_initiated=True,
                    disclosure_confirmed=True,
                    timeout_seconds=240.0,
                )
                try:
                    response = self._execution.run_image_edit(
                        provider,
                        request,
                        credential,
                        cancellation,
                    )
                except Exception as exc:
                    if cancellation.cancelled:
                        break
                    failures.append(
                        (asset.asset_id, provider_error_message(exc))
                    )
                    if is_systemic_provider_error(exc):
                        break
                    continue
                successes.append(
                    (
                        asset.asset_id,
                        response,
                        crop,
                        mask,
                        method,
                        request.instruction,
                    )
                )
            processed = len(successes) + len(failures)
            skipped = max(0, len(selected) - processed)
            return (
                successes,
                failures,
                output_kind,
                source_hash,
                cancellation.cancelled,
                skipped,
            )

        self._start_worker(
            "generate",
            operation,
            self._generation_finished,
        )

    def _generation_finished(self, result: object) -> None:
        self._image_cancellation = None
        self.generate_button.setEnabled(True)
        self.cancel_generation_button.setEnabled(False)
        if self._store is None or self._state is None:
            return
        if len(result) == 5:
            successes, failures, output_kind, source_hash, cancelled = result
            skipped = 0
        else:
            (
                successes,
                failures,
                output_kind,
                source_hash,
                cancelled,
                skipped,
            ) = result
        for (
            asset_id,
            response,
            crop,
            mask,
            method,
            instruction,
        ) in successes:
            generation_id = str(uuid.uuid4())
            relative = (
                f"artifacts/generated/{asset_id}_{generation_id[:8]}.png"
            )
            self._store.save_artifact(relative, response.image_bytes)
            self._store.save_artifact(
                f"artifacts/masks/{asset_id}.png",
                _mask_png(mask),
            )
            asset = next(
                (
                    item
                    for item in self._store.state.assets
                    if item.asset_id == asset_id
                ),
                None,
            )
            if asset is not None:
                self._store.add_or_replace_asset(
                    replace(
                        asset,
                        mask_relative_path=f"artifacts/masks/{asset_id}.png",
                        mask_method=method,
                        updated_at=utc_now(),
                    )
                )
            self._store.append_generation(
                GenerationRecord(
                    generation_id=generation_id,
                    asset_id=asset_id,
                    output_kind=output_kind,
                    source_image_sha256=source_hash,
                    source_rect=asset.normalized_rect if asset else (0, 0, 1, 1),
                    provider_id=response.provider_id,
                    model_id=response.model_id,
                    parameters=dict(instruction),
                    relative_path=relative,
                    status="completed",
                    created_at=utc_now(),
                )
            )
        for asset_id, message in failures:
            asset = next(
                (
                    item
                    for item in self._store.state.assets
                    if item.asset_id == asset_id
                ),
                None,
            )
            self._store.append_generation(
                GenerationRecord(
                    generation_id=str(uuid.uuid4()),
                    asset_id=asset_id,
                    output_kind=output_kind,
                    source_image_sha256=source_hash,
                    source_rect=asset.normalized_rect if asset else (0, 0, 1, 1),
                    provider_id=str(self.image_provider_combo.currentData()),
                    model_id=_combo_model_id(self.image_model_combo) or "",
                    parameters={},
                    relative_path="",
                    status="failed",
                    error_message=message[:500],
                    created_at=utc_now(),
                )
            )
        self._state = self._store.state
        self._refresh_generation_list()
        suffix = "；任务已取消" if cancelled else ""
        self.statusBar().showMessage(
            f"生成结束：成功 {len(successes)}，失败 {len(failures)}，"
            f"未发送 {skipped}{suffix}。",
            6000,
        )
        if failures and self.isVisible():
            first_error = failures[0][1]
            extra = (
                f"\n\n已停止后续 {skipped} 项，避免重复无效调用。"
                if skipped
                else ""
            )
            QMessageBox.warning(
                self,
                "部分资产生成失败",
                f"{first_error}{extra}\n\n"
                "失败记录已保存；在生成列表悬停可再次查看。",
            )

    def _cancel_generation(self) -> None:
        if self._image_cancellation is not None:
            self._image_cancellation.cancel()
            self.statusBar().showMessage("正在取消；已完成的资产图片会保留…")

    def _start_automatic_pipeline(self) -> None:
        if (
            self._store is None
            or self._state is None
            or self._loaded is None
            or self._state.main_image is None
        ):
            QMessageBox.information(
                self,
                "缺少主原画",
                "请先新建或打开项目并导入主原画。",
            )
            return
        self._save_fields()
        vision_provider_id = str(
            self.auto_vision_provider_combo.currentData()
        )
        image_provider_id = str(
            self.auto_image_provider_combo.currentData()
        )
        vision_provider = self._provider_registry.get(vision_provider_id)
        image_provider = self._provider_registry.get(image_provider_id)
        vision_key = self.auto_vision_key_edit.text().strip()
        image_key = self.auto_image_key_edit.text().strip()
        if vision_provider_id != "mock" and not vision_key:
            QMessageBox.information(
                self,
                "缺少清单 API Key",
                "请输入视觉分析供应商的 API Key。",
            )
            return
        if image_provider_id != "mock" and not image_key:
            QMessageBox.information(
                self,
                "缺少图片 API Key",
                "请输入图片生成供应商的 API Key。",
            )
            return

        main_image = prepare_provider_image(
            self._loaded,
            "main_concept",
            ProviderImageExportOptions(maximum_side=2048),
        )
        images = [main_image]
        supplemental = []
        for index, reference in enumerate(
            (
                image
                for image in self._state.source_images
                if image.role == "reference"
            ),
            start=1,
        ):
            if index > 3:
                break
            loaded = load_image(self._store.image_path(reference))
            images.append(
                prepare_provider_image(
                    loaded,
                    f"supplemental_reference_{index}",
                    ProviderImageExportOptions(maximum_side=1536),
                )
            )
            supplemental.append(
                {
                    "role": f"supplemental_reference_{index}",
                    "sha256": reference.sha256,
                    "filename_hidden": True,
                }
            )
        profile = self._current_profile()
        plan = self._selected_plan()
        context = AssetBreakdownContext(
            project_id=self._state.project_id,
            title=self._state.title,
            scene_type=self._state.scene_type,
            scene_focus=tuple(profile.get("focus", ())),
            production_goal=self._state.production_goal,
            image_metadata={
                "width": self._loaded.working_size[0],
                "height": self._loaded.working_size[1],
                "exif_orientation_applied": (
                    self._loaded.exif_orientation_applied
                ),
                "icc_converted_to_srgb": (
                    self._loaded.icc_converted_to_srgb
                ),
                "assumed_srgb": self._loaded.assumed_srgb,
                "automatic_asset_limit": self.auto_asset_limit.value(),
            },
            supplemental_references=tuple(supplemental),
            scene_understanding=(
                next(
                    (
                        item.to_dict()
                        for item in self._state.scene_understandings
                        if plan is not None
                        and item.understanding_id
                        == plan.source_understanding_id
                    ),
                    {},
                )
            ),
            breakdown_plan=plan.to_dict() if plan else {},
            study_handoff=self._study_handoff_for_ai(),
        )
        vision_model_id = (
            self.auto_vision_model_edit.text().strip() or None
        )
        image_model_id = _combo_model_id(self.auto_image_model_combo)
        request = self._reviewer.create_request(
            context,
            tuple(images),
            model_id=vision_model_id,
            user_initiated=True,
            disclosure_confirmed=True,
        )
        limit = self.auto_asset_limit.value()
        image_resolution = str(
            self.auto_resolution_combo.currentData() or "1K"
        )
        preview = disclosure_preview(vision_provider.manifest, request)
        dialog = SendDisclosureDialog(
            preview,
            purpose="自动资产板",
            extra_notice=(
                f"确认后会先进行 1 次场景资产分析，再对最多 {limit} 项资产"
                "分别调用图片生成，最后在本地合成资产板。"
                "这是可能产生较高费用的批量操作；遇到供应商级错误会立即停止"
                "后续调用。人工校正清单不会被修改。"
                f"\n图片供应商：{image_provider.manifest.display_name}；"
                f"模型：{image_provider.manifest.model_for(ProviderCapability.IMAGE_EDIT, image_model_id)}；"
                f"分辨率：{image_resolution}。"
                f"\n拆分方案：{plan.name if plan else '未选择'}。"
            ),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        cancellation = CancellationToken()
        self._automatic_cancellation = cancellation
        self.auto_start_button.setEnabled(False)
        self.auto_cancel_button.setEnabled(True)
        run_id = str(uuid.uuid4())
        source = self._state.main_image
        scene_type = self._state.scene_type
        source_image_id = source.image_id
        self.auto_status.setText(
            "状态：正在生成 · 可取消，已完成项目将保留"
        )

        def operation():
            return run_automatic_pipeline(
                reviewer=self._reviewer,
                review_provider=vision_provider,
                review_request=request,
                review_credential=vision_key,
                image_provider=image_provider,
                image_credential=image_key,
                image_model_id=image_model_id,
                image_resolution=image_resolution,
                full_scene=main_image,
                rgb=self._loaded.rgb,
                source_image_id=source_image_id,
                scene_type=scene_type,
                output_kind="isolated_concept",
                asset_limit=limit,
                execution=self._execution,
                cancellation=cancellation,
            )

        config = {
            "run_id": run_id,
            "source_hash": source.sha256,
            "vision_provider_id": vision_provider_id,
            "vision_model_id": vision_model_id or "",
            "image_provider_id": image_provider_id,
            "image_model_id": image_model_id or "",
            "image_resolution": image_resolution,
            "asset_limit": limit,
            "plan_id": plan.plan_id if plan else "",
            "plan_fingerprint": plan_fingerprint(plan),
            "plan_name": plan.name if plan else "",
            "source_understanding_id": (
                plan.source_understanding_id if plan else ""
            ),
            "breakdown_plan": plan.to_dict() if plan else {},
        }
        self._start_worker(
            "automatic",
            operation,
            lambda result: self._automatic_pipeline_finished(
                result,
                config,
            ),
        )

    def _automatic_pipeline_finished(
        self,
        result: AutomaticPipelineResult,
        config: dict,
    ) -> None:
        self._automatic_cancellation = None
        self.auto_start_button.setEnabled(True)
        self.auto_cancel_button.setEnabled(False)
        if self._store is None or self._state is None:
            return
        run_id = str(config["run_id"])
        root_relative = f"artifacts/automatic/{run_id}"
        generations: list[GenerationRecord] = []
        board_entries = []
        saved_assets: dict[str, AssetItem] = {}
        for generated in result.generated:
            relative = (
                f"{root_relative}/assets/"
                f"{generated.asset.asset_id}.png"
            )
            mask_relative = (
                f"{root_relative}/masks/"
                f"{generated.asset.asset_id}.png"
            )
            output_path = self._store.save_artifact(
                relative,
                generated.image_bytes,
            )
            self._store.save_artifact(
                mask_relative,
                _mask_png(generated.mask),
            )
            asset = replace(
                generated.asset,
                mask_relative_path=mask_relative,
                mask_method=generated.mask_method,
            )
            saved_assets[asset.asset_id] = asset
            board_entries.append((asset, output_path))
            generations.append(
                GenerationRecord(
                    generation_id=str(uuid.uuid4()),
                    asset_id=asset.asset_id,
                    output_kind="isolated_concept",
                    source_image_sha256=str(config["source_hash"]),
                    source_rect=asset.normalized_rect,
                    provider_id=generated.provider_id,
                    model_id=generated.model_id,
                    parameters=dict(generated.instruction),
                    relative_path=relative,
                    status="completed",
                    created_at=utc_now(),
                )
            )
        assets_by_id = {asset.asset_id: asset for asset in result.assets}
        for asset_id, message in result.failures:
            asset = assets_by_id.get(asset_id)
            generations.append(
                GenerationRecord(
                    generation_id=str(uuid.uuid4()),
                    asset_id=asset_id,
                    output_kind="isolated_concept",
                    source_image_sha256=str(config["source_hash"]),
                    source_rect=(
                        asset.normalized_rect
                        if asset is not None
                        else (0.0, 0.0, 1.0, 1.0)
                    ),
                    provider_id=str(config["image_provider_id"]),
                    model_id=str(config["image_model_id"]),
                    parameters={
                        "output_resolution": config["image_resolution"]
                    },
                    relative_path="",
                    status="failed",
                    error_message=message[:1200],
                    created_at=utc_now(),
                )
            )

        board_relatives: list[str] = []
        if board_entries:
            plan_value = dict(config.get("breakdown_plan", {}))
            pages = make_asset_board_pages(
                board_entries,
                title=f"{self._state.title} — 自动资产板",
                grouping_strategy=str(
                    plan_value.get("grouping_strategy", "asset_family")
                ),
                max_items_per_page=int(
                    plan_value.get("max_items_per_page", 9)
                ),
            )
            for index, page in enumerate(pages, start=1):
                relative = f"{root_relative}/asset_board_{index:02d}.png"
                self._store.save_artifact(relative, page.png_bytes)
                board_relatives.append(relative)
        manifest_relative = f"{root_relative}/asset_manifest.json"
        run_assets = tuple(
            saved_assets.get(asset.asset_id, asset)
            for asset in result.assets
        )
        write_asset_manifest(
            self._store.artifact_path(manifest_relative),
            project={
                "project_id": self._state.project_id,
                "title": self._state.title,
                "mode": "automatic_asset_board",
                "run_id": run_id,
                "main_image_sha256": config["source_hash"],
                "plan_id": config.get("plan_id", ""),
                "plan_fingerprint": config.get("plan_fingerprint", ""),
                "plan_name": config.get("plan_name", ""),
            },
            assets=run_assets,
            generations=(item.to_dict() for item in generations),
        )
        if result.cancelled:
            status = "cancelled"
        elif result.failures and result.generated:
            status = "partial"
        elif result.failures:
            status = "failed"
        else:
            status = "completed"
        error_summary = (
            result.failures[0][1] if result.failures else ""
        )
        run = AutomaticAssetRun(
            run_id=run_id,
            status=status,
            source_image_sha256=str(config["source_hash"]),
            vision_provider_id=result.review_execution.response.provider_id,
            vision_model_id=result.review_execution.response.model_id,
            image_provider_id=str(config["image_provider_id"]),
            image_model_id=str(config["image_model_id"]),
            output_kind="isolated_concept",
            asset_limit=int(config["asset_limit"]),
            plan_id=str(config.get("plan_id", "")),
            plan_fingerprint=str(config.get("plan_fingerprint", "")),
            plan_name=str(config.get("plan_name", "")),
            source_understanding_id=str(
                config.get("source_understanding_id", "")
            ),
            assets=run_assets,
            generations=tuple(generations),
            board_relative_path=(
                board_relatives[0] if board_relatives else ""
            ),
            board_relative_paths=tuple(board_relatives),
            manifest_relative_path=manifest_relative,
            repair_notes=result.repair_notes,
            error_summary=error_summary,
            created_at=utc_now(),
        )
        self._store.append_automatic_run(run)
        self._state = self._store.state
        self._refresh_automatic_runs(select_run_id=run_id)
        skipped = max(
            0,
            len(result.assets)
            - len(result.generated)
            - len(result.failures),
        )
        self.auto_status.setText(
            f"状态：运行结束 · 识别 {len(result.assets)} 项，"
            f"生成 {len(result.generated)} 项，失败 {len(result.failures)} 项，"
            f"未发送 {skipped} 项；资产板 {len(board_relatives)} 页。"
        )
        if result.failures and self.isVisible():
            suffix = (
                f"\n\n已停止后续 {skipped} 项，避免重复无效调用。"
                if skipped
                else ""
            )
            QMessageBox.warning(
                self,
                "自动资产板部分失败",
                f"{result.failures[0][1]}{suffix}\n\n"
                "已成功生成的图片和清单仍然保存。",
            )

    def _cancel_automatic_pipeline(self) -> None:
        if self._automatic_cancellation is not None:
            self._automatic_cancellation.cancel()
            self.auto_status.setText(
                "状态：正在取消 · 当前请求结束后停止，已完成结果将保留"
            )

    def _refresh_automatic_runs(self, select_run_id: str = "") -> None:
        self.auto_run_list.clear()
        self.auto_board_preview.setPixmap(QPixmap())
        self.auto_board_preview.setText("资产板预览")
        self.auto_export_button.setEnabled(False)
        if self._state is None or self._store is None:
            return
        selected_run = None
        for run in reversed(self._state.automatic_runs):
            status = {
                "completed": "完成",
                "partial": "部分完成",
                "failed": "失败",
                "cancelled": "已取消",
            }.get(run.status, run.status)
            completed = sum(
                item.status == "completed" for item in run.generations
            )
            plan = self._selected_plan()
            stale = (
                plan is None
                or run.plan_id != plan.plan_id
                or run.plan_fingerprint != plan_fingerprint(plan)
            )
            basis = " · 旧版依据" if stale else ""
            item = QListWidgetItem(
                f"{status}{basis} · {run.created_at} · "
                f"{completed}/{len(run.assets)} 项"
            )
            item.setData(Qt.ItemDataRole.UserRole, run.run_id)
            if run.error_summary:
                item.setToolTip(run.error_summary)
            self.auto_run_list.addItem(item)
            if selected_run is None or run.run_id == select_run_id:
                selected_run = run
        if selected_run is not None:
            self._show_automatic_run(selected_run.run_id)

    def _show_automatic_run(self, run_id: str) -> None:
        if self._state is None or self._store is None:
            return
        run = next(
            (
                item
                for item in self._state.automatic_runs
                if item.run_id == run_id
            ),
            None,
        )
        if run is None:
            return
        completed = sum(
            item.status == "completed" for item in run.generations
        )
        status = {
            "completed": "完成",
            "partial": "部分完成",
            "failed": "失败",
            "cancelled": "已取消",
        }.get(run.status, run.status)
        plan = self._selected_plan()
        stale = (
            plan is None
            or run.plan_id != plan.plan_id
            or run.plan_fingerprint != plan_fingerprint(plan)
        )
        basis_text = (
            f"；生成依据 {run.plan_name or '旧版方案'}，与当前方案不一致"
            if stale
            else f"；生成依据 {run.plan_name or (plan.name if plan else '未记录')}"
        )
        self.auto_status.setText(
            f"状态：{status}；识别 {len(run.assets)} 项，"
            f"生成 {completed} 项{basis_text}。"
        )
        self.auto_export_button.setEnabled(bool(run.manifest_relative_path))
        self.auto_export_button.setProperty("run_id", run.run_id)
        preview_relative = (
            run.board_relative_paths[0]
            if run.board_relative_paths
            else run.board_relative_path
        )
        if preview_relative:
            path = self._store.artifact_path(preview_relative)
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.auto_board_preview.setText("")
                self.auto_board_preview.setPixmap(
                    pixmap.scaled(
                        720,
                        560,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.auto_board_preview.setText("该次运行没有可显示的资产板。")

    def _export_automatic_run(self) -> None:
        if self._state is None or self._store is None:
            return
        run_id = str(self.auto_export_button.property("run_id") or "")
        run = next(
            (
                item
                for item in self._state.automatic_runs
                if item.run_id == run_id
            ),
            None,
        )
        if run is None:
            return
        destination = QFileDialog.getExistingDirectory(
            self,
            "选择自动资产板导出目录",
        )
        if not destination:
            return
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        relatives = [
            *run.board_relative_paths,
            run.board_relative_path,
            run.manifest_relative_path,
            *(
                record.relative_path
                for record in run.generations
                if record.relative_path
            ),
        ]
        copied = 0
        for relative in dict.fromkeys(item for item in relatives if item):
            source = self._store.artifact_path(relative)
            self._store.copy_export(source, folder / source.name)
            copied += 1
        QMessageBox.information(
            self,
            "导出完成",
            f"已导出 {copied} 个文件。",
        )

    def _refresh_prompt_sessions(
        self,
        select_session_id: str = "",
    ) -> None:
        combo = self.prompt_panel.session_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("新提示语会话", "")
            if self._state is None:
                selected_id = ""
            else:
                selected_id = (
                    select_session_id
                    or self._state.selected_prompt_session_id
                )
                for session in self._state.prompt_sessions:
                    combo.addItem(
                        (
                            f"{session.title}｜"
                            f"{len(session.revisions)} 版"
                        ),
                        session.session_id,
                    )
            index = combo.findData(selected_id)
            combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            combo.blockSignals(False)
        self._show_prompt_session(str(combo.currentData() or ""))

    def _current_prompt_session(self) -> AssetPromptSession | None:
        if self._state is None:
            return None
        session_id = str(
            self.prompt_panel.session_combo.currentData() or ""
        )
        return next(
            (
                item
                for item in self._state.prompt_sessions
                if item.session_id == session_id
            ),
            None,
        )

    def _show_prompt_session(self, session_id: str) -> None:
        if self._state is None or not session_id:
            self.prompt_panel.load_session(None)
            self._update_basis_views(self._selected_plan())
            return
        session = next(
            (
                item
                for item in self._state.prompt_sessions
                if item.session_id == session_id
            ),
            None,
        )
        self.prompt_panel.load_session(session)
        if session is None or session.current_revision is None:
            self._update_basis_views(self._selected_plan())
            return
        plan = self._selected_plan()
        revision = session.current_revision
        stale = (
            plan is None
            or revision.plan_id != plan.plan_id
            or revision.plan_fingerprint != plan_fingerprint(plan)
        )
        if stale:
            self.prompt_panel.set_basis(
                f"生成依据：{revision.plan_name or '旧版方案'} · "
                "与当前方案不一致；历史版本保留，重新生成后更新。",
                stale=True,
            )
        else:
            self._update_basis_views(plan)

    def _prompt_session_changed(self, _index: int) -> None:
        session_id = str(
            self.prompt_panel.session_combo.currentData() or ""
        )
        if self._store is not None:
            self._store.select_prompt_session(session_id)
            self._state = self._store.state
        self._show_prompt_session(session_id)

    def _new_prompt_session(self) -> None:
        if self._store is not None:
            self._store.select_prompt_session("")
            self._state = self._store.state
        self._refresh_prompt_sessions()
        self.prompt_panel.status_label.setText(
            "状态：新会话 · 选择目标工具后生成初稿"
        )

    def _prompt_target_tool(self) -> str:
        combo = self.prompt_panel.target_tool_combo
        index = combo.currentIndex()
        if index >= 0 and combo.currentText() == combo.itemText(index):
            value = combo.itemData(index)
            if value:
                return str(value)
        return combo.currentText().strip() or "generic"

    def _prompt_context_and_images(
        self,
        *,
        include_images: bool,
    ) -> tuple[AssetPromptContext, tuple[ProviderImage, ...]]:
        if (
            self._state is None
            or self._loaded is None
            or self._state.main_image is None
        ):
            raise ValueError("请先导入一张主原画。")
        images: list[ProviderImage] = []
        if include_images:
            images.append(
                prepare_provider_image(
                    self._loaded,
                    "main_concept",
                    ProviderImageExportOptions(maximum_side=2048),
                )
            )
        supplemental = []
        if self._store is not None:
            references = [
                image
                for image in self._state.source_images
                if image.role == "reference"
            ][:3]
            for index, reference in enumerate(references, start=1):
                role = f"supplemental_reference_{index}"
                supplemental.append(
                    {
                        "role": role,
                        "sha256": reference.sha256,
                        "filename_hidden": True,
                    }
                )
                if include_images:
                    loaded = load_image(self._store.image_path(reference))
                    images.append(
                        prepare_provider_image(
                            loaded,
                            role,
                            ProviderImageExportOptions(maximum_side=1536),
                        )
                    )
        plan = self._selected_plan()
        understanding = next(
            (
                item.to_dict()
                for item in self._state.scene_understandings
                if plan is not None
                and item.understanding_id == plan.source_understanding_id
            ),
            {},
        )
        context = AssetPromptContext(
            project_id=self._state.project_id,
            title=self._state.title,
            scene_type=self._state.scene_type,
            production_goal=self._state.production_goal,
            notes=self._state.notes,
            target_tool=self._prompt_target_tool(),
            image_metadata={
                "width": self._loaded.working_size[0],
                "height": self._loaded.working_size[1],
                "exif_orientation_applied": (
                    self._loaded.exif_orientation_applied
                ),
                "icc_converted_to_srgb": (
                    self._loaded.icc_converted_to_srgb
                ),
                "assumed_srgb": self._loaded.assumed_srgb,
            },
            supplemental_references=tuple(supplemental),
            scene_understanding=understanding,
            breakdown_plan=plan.to_dict() if plan else {},
            study_handoff=self._study_handoff_for_ai(),
        )
        return context, tuple(images)

    def _start_prompt_initial(self) -> None:
        self._start_prompt_request(refine=False)

    def _start_prompt_iteration(self) -> None:
        self._start_prompt_request(refine=True)

    def _start_prompt_request(self, *, refine: bool) -> None:
        if (
            self._state is None
            or self._loaded is None
            or self._state.main_image is None
        ):
            QMessageBox.information(
                self,
                "缺少主原画",
                "请先新建或打开资产项目并导入主原画。",
            )
            return
        self._save_fields()
        session = self._current_prompt_session() if refine else None
        base_revision = (
            self.prompt_panel.selected_revision()
            if session is not None
            else None
        )
        if (
            refine
            and base_revision is not None
            and self._prompt_editor_has_changes(base_revision)
        ):
            saved_revision = self._persist_manual_prompt_revision(
                show_status=False
            )
            if saved_revision is None:
                return
            session = self._current_prompt_session()
            base_revision = saved_revision
        feedback = self.prompt_panel.feedback_edit.toPlainText().strip()
        if refine and (session is None or base_revision is None):
            QMessageBox.information(
                self,
                "没有可修订的提示语",
                "请先生成提示语初稿，或选择一个已有会话。",
            )
            return
        if refine and not feedback:
            QMessageBox.information(
                self,
                "缺少修改意见",
                "请填写本次修订要求。",
            )
            return

        provider_id = str(self.prompt_panel.provider_combo.currentData())
        provider = self._provider_registry.get(provider_id)
        credential = self.prompt_panel.key_edit.text().strip()
        if provider_id != "mock" and not credential:
            QMessageBox.information(
                self,
                "缺少 API Key",
                "请输入 API Key，或选择“离线 Mock”只验证流程。",
            )
            return
        include_images = (
            not refine or self.prompt_panel.resend_image_check.isChecked()
        )
        try:
            context, images = self._prompt_context_and_images(
                include_images=include_images
            )
            request = self._prompt_reviewer.create_request(
                context,
                images,
                current_revision=base_revision,
                feedback=feedback,
                messages=session.messages if session is not None else (),
                model_id=(
                    self.prompt_panel.model_edit.text().strip() or None
                ),
                user_initiated=True,
                disclosure_confirmed=True,
            )
        except ValueError as exc:
            QMessageBox.information(self, "无法生成提示语", str(exc))
            return
        preview = disclosure_preview(provider.manifest, request)
        if refine and not include_images:
            image_notice = (
                "本次只发送当前提示语、最近协商记录和修改意见，不重新发送图片。"
            )
        else:
            image_notice = (
                "本次会发送主原画副本和最多三张补充参考；原始元数据已移除。"
            )
        dialog = SendDisclosureDialog(
            preview,
            purpose=("提示语修订" if refine else "提示语初稿"),
            extra_notice=(
                f"{image_notice}\n"
                "本次只生成文本，不调用图片生成服务。每次修订会产生一次"
                "所选视觉模型调用，并采用当前拆分方案。"
            ),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        cancellation = CancellationToken()
        self._prompt_cancellation = cancellation
        self.prompt_panel.set_busy(True)
        self.prompt_panel.status_label.setText(
            "状态：正在生成修订版本…"
            if refine
            else "状态：正在分析并生成初稿…"
        )
        project_id = self._state.project_id
        source_hash = self._state.main_image.sha256
        session_id = session.session_id if session is not None else ""
        base_revision_id = (
            base_revision.revision_id
            if base_revision is not None
            else ""
        )
        plan = self._selected_plan()
        plan_id = plan.plan_id if plan is not None else ""
        exact_plan_fingerprint = plan_fingerprint(plan)
        plan_name = plan.name if plan is not None else ""
        understanding_id = (
            plan.source_understanding_id if plan is not None else ""
        )

        def operation():
            execution = self._execution.run_review_with_model_fallback(
                provider,
                request,
                credential,
                cancellation,
                provider.manifest.fallback_models_for(
                    ProviderCapability.VISION_REVIEW,
                    request.model_id,
                ),
            )
            output = self._prompt_reviewer.validate_output(
                execution.response.output
            )
            return {
                "mode": "refine" if refine else "initial",
                "project_id": project_id,
                "source_hash": source_hash,
                "session_id": session_id,
                "base_revision_id": base_revision_id,
                "feedback": feedback,
                "images_sent": len(images),
                "target_tool": context.target_tool,
                "plan_id": plan_id,
                "plan_fingerprint": exact_plan_fingerprint,
                "plan_name": plan_name,
                "source_understanding_id": understanding_id,
                "output": output,
                "execution": execution,
            }

        self._start_worker(
            "prompt",
            operation,
            self._prompt_request_finished,
        )

    def _prompt_request_finished(self, result: object) -> None:
        self._prompt_cancellation = None
        self.prompt_panel.set_busy(False)
        if (
            not isinstance(result, dict)
            or self._store is None
            or self._state is None
            or self._state.main_image is None
        ):
            return
        if (
            result["project_id"] != self._state.project_id
            or result["source_hash"] != self._state.main_image.sha256
        ):
            self.prompt_panel.status_label.setText(
                "项目或主原画已经切换，旧的后台提示语结果已忽略。"
            )
            return
        output = result["output"]
        execution = result["execution"]
        now = utc_now()
        revision = PromptRevision(
            revision_id=str(uuid.uuid4()),
            origin="ai",
            title=str(output["prompt_title"]),
            target_tool=str(
                result.get(
                    "target_tool",
                    output.get("target_tool", "generic"),
                )
            ),
            analysis_summary=str(output["analysis_summary"]),
            prompt_zh=str(output["prompt_zh"]),
            prompt_en=str(output["prompt_en"]),
            negative_prompt=str(output["negative_prompt"]),
            constraints=tuple(
                str(item) for item in output["constraints"]
            ),
            asset_groups=tuple(
                dict(item) for item in output["asset_groups"]
            ),
            change_summary=str(output["change_summary"]),
            provider_id=execution.response.provider_id,
            model_id=execution.response.model_id,
            plan_id=str(result.get("plan_id", "")),
            plan_fingerprint=str(result.get("plan_fingerprint", "")),
            plan_name=str(result.get("plan_name", "")),
            source_understanding_id=str(
                result.get("source_understanding_id", "")
            ),
            created_at=now,
        )
        if result["mode"] == "initial":
            session = AssetPromptSession(
                session_id=str(uuid.uuid4()),
                title=revision.title,
                source_image_sha256=self._state.main_image.sha256,
                target_tool=revision.target_tool,
                revisions=(revision,),
                messages=(
                    PromptMessage(
                        message_id=str(uuid.uuid4()),
                        role="assistant",
                        content=(
                            revision.change_summary
                            or "已根据原画生成提示语初稿。"
                        ),
                        created_at=now,
                    ),
                ),
                created_at=now,
                updated_at=now,
            )
        else:
            session = next(
                (
                    item
                    for item in self._state.prompt_sessions
                    if item.session_id == result["session_id"]
                ),
                None,
            )
            if session is None:
                self.prompt_panel.status_label.setText(
                    "原提示语会话已经不存在，本次结果未写入。"
                )
                return
            session = replace(
                session,
                title=revision.title,
                target_tool=revision.target_tool,
                revisions=(*session.revisions, revision),
                messages=(
                    *session.messages,
                    PromptMessage(
                        message_id=str(uuid.uuid4()),
                        role="user",
                        content=str(result["feedback"]),
                        created_at=now,
                    ),
                    PromptMessage(
                        message_id=str(uuid.uuid4()),
                        role="assistant",
                        content=(
                            revision.change_summary
                            or "已按本次要求生成修订版本。"
                        ),
                        created_at=now,
                    ),
                ),
                updated_at=now,
            )
        self._store.add_or_replace_prompt_session(session)
        self._store.append_ai_run(
            {
                "run_id": str(uuid.uuid4()),
                "module_id": "scenelens.asset_breakdown",
                "reviewer_id": "asset_prompt_workshop",
                "reviewer_version": (
                    self._prompt_reviewer.descriptor.version
                ),
                "provider_id": execution.response.provider_id,
                "model_id": execution.response.model_id,
                "input_hashes": {
                    "main": self._state.main_image.sha256,
                },
                "parameters": {
                    "mode": result["mode"],
                    "target_tool": revision.target_tool,
                    "images_sent": result["images_sent"],
                    "base_revision_id": result["base_revision_id"],
                    "plan_id": revision.plan_id,
                    "plan_fingerprint": revision.plan_fingerprint,
                    "source_understanding_id": (
                        revision.source_understanding_id
                    ),
                },
                "result_summary": {
                    "session_id": session.session_id,
                    "revision_id": revision.revision_id,
                    "asset_group_count": len(revision.asset_groups),
                    "change_summary": revision.change_summary,
                },
                "created_at": now,
            }
        )
        self._state = self._store.state
        self._refresh_prompt_sessions(
            select_session_id=session.session_id
        )
        self.prompt_panel.feedback_edit.clear()
        self.prompt_panel.status_label.setText(
            (
                "状态：新版本已保存 · 可继续修订、编辑或复制"
                if result["mode"] == "refine"
                else "状态：初稿已保存 · 可继续修订、编辑或复制"
            )
        )

    def _save_manual_prompt_revision(self) -> None:
        self._persist_manual_prompt_revision(show_status=True)

    def _prompt_editor_has_changes(
        self,
        base: PromptRevision,
    ) -> bool:
        return any(
            (
                self.prompt_panel.prompt_zh_edit.toPlainText().strip()
                != base.prompt_zh,
                self.prompt_panel.prompt_en_edit.toPlainText().strip()
                != base.prompt_en,
                self.prompt_panel.negative_edit.toPlainText().strip()
                != base.negative_prompt,
                self.prompt_panel.constraints() != base.constraints,
                self._prompt_target_tool() != base.target_tool,
            )
        )

    def _persist_manual_prompt_revision(
        self,
        *,
        show_status: bool,
    ) -> PromptRevision | None:
        if self._store is None or self._state is None:
            return None
        session = self._current_prompt_session()
        base = self.prompt_panel.selected_revision()
        if session is None or base is None:
            QMessageBox.information(
                self,
                "没有提示语",
                "请先生成或选择一个提示语会话。",
            )
            return None
        if not self._prompt_editor_has_changes(base):
            if show_status:
                self.prompt_panel.status_label.setText(
                    "当前文字与所选历史版本相同，无需重复保存。"
                )
            return base
        prompt_zh = self.prompt_panel.prompt_zh_edit.toPlainText().strip()
        prompt_en = self.prompt_panel.prompt_en_edit.toPlainText().strip()
        if not prompt_zh and not prompt_en:
            QMessageBox.information(
                self,
                "提示语为空",
                "中文和英文提示语不能同时为空。",
            )
            return None
        now = utc_now()
        revision = PromptRevision(
            revision_id=str(uuid.uuid4()),
            origin="user_edit",
            title=base.title,
            target_tool=self._prompt_target_tool(),
            analysis_summary=base.analysis_summary,
            prompt_zh=prompt_zh,
            prompt_en=prompt_en,
            negative_prompt=(
                self.prompt_panel.negative_edit.toPlainText().strip()
            ),
            constraints=self.prompt_panel.constraints()[:24],
            asset_groups=base.asset_groups,
            change_summary="用户在 GATalk 内手动编辑并保存。",
            provider_id="user",
            model_id="",
            plan_id=base.plan_id,
            plan_fingerprint=base.plan_fingerprint,
            plan_name=base.plan_name,
            source_understanding_id=base.source_understanding_id,
            created_at=now,
        )
        updated = replace(
            session,
            title=revision.title,
            target_tool=revision.target_tool,
            revisions=(*session.revisions, revision),
            messages=(
                *session.messages,
                PromptMessage(
                    message_id=str(uuid.uuid4()),
                    role="user",
                    content="在软件内手动编辑并保存了提示语。",
                    created_at=now,
                ),
            ),
            updated_at=now,
        )
        self._store.add_or_replace_prompt_session(updated)
        self._state = self._store.state
        self._refresh_prompt_sessions(
            select_session_id=updated.session_id
        )
        if show_status:
            self.prompt_panel.status_label.setText(
                "手动修改已作为新版本保存，旧版本仍可在历史版本中查看。"
            )
        return revision

    def _copy_prompt_text(self, value: str, message: str) -> None:
        text = value.strip()
        if not text:
            QMessageBox.information(self, "没有可复制内容", "当前文字为空。")
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(message, 3000)

    def _cancel_prompt_request(self) -> None:
        if self._prompt_cancellation is not None:
            self._prompt_cancellation.cancel()
            self.prompt_panel.status_label.setText("状态：正在取消请求…")

    def _export_package(self) -> None:
        if self._store is None or self._state is None:
            return
        destination = QFileDialog.getExistingDirectory(
            self,
            "选择资产拆分导出目录",
        )
        if not destination:
            return
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        selected = tuple(
            asset
            for asset in self._state.assets
            if asset.selected_for_generation
            and asset.plan_id == self._state.selected_plan_id
        ) or tuple(
            asset for asset in self._state.assets
            if asset.plan_id == self._state.selected_plan_id
        )
        completed = [
            record
            for record in self._state.generations
            if record.status == "completed" and record.relative_path
        ]
        latest_by_asset = {}
        for record in completed:
            latest_by_asset[record.asset_id] = record
        board_entries = []
        for asset in selected:
            record = latest_by_asset.get(asset.asset_id)
            if record is None:
                continue
            source = self._store.artifact_path(record.relative_path)
            output = folder / f"{_safe_folder_name(asset.name)}_{asset.asset_id}.png"
            self._store.copy_export(source, output)
            board_entries.append((asset, output))
        manifest_path = write_asset_manifest(
            folder / "asset_manifest.json",
            project={
                "project_id": self._state.project_id,
                "title": self._state.title,
                "scene_type": self._state.scene_type,
                "main_image_sha256": (
                    self._state.main_image.sha256
                    if self._state.main_image
                    else ""
                ),
            },
            assets=selected,
            generations=(item.to_dict() for item in completed),
        )
        board_paths: list[Path] = []
        if board_entries:
            plan = self._selected_plan()
            pages = make_asset_board_pages(
                board_entries,
                title=(
                    f"{self._state.title} — "
                    f"{plan.name if plan else '资产展示板'}"
                ),
                grouping_strategy=(
                    plan.grouping_strategy if plan else "asset_family"
                ),
                max_items_per_page=(
                    plan.max_items_per_page if plan else 9
                ),
            )
            for index, page in enumerate(pages, start=1):
                board_path = folder / f"asset_board_{index:02d}.png"
                board_path.write_bytes(page.png_bytes)
                board_paths.append(board_path)
                record = AssetBoardPage(
                    page_id=str(uuid.uuid4()),
                    plan_id=plan.plan_id if plan else "",
                    title=page.title,
                    group_key=page.group_key,
                    page_index=index,
                    asset_ids=page.asset_ids,
                    relative_path="",
                    created_at=utc_now(),
                )
                self._store.append_board_page(record)
        self._store.append_export(
            {
                "export_id": str(uuid.uuid4()),
                "destination_hidden": True,
                "manifest_filename": manifest_path.name,
                "board_filenames": [item.name for item in board_paths],
                "plan_id": self._state.selected_plan_id,
                "asset_count": len(selected),
                "image_count": len(board_entries),
                "created_at": utc_now(),
            }
        )
        self._state = self._store.state
        QMessageBox.information(
            self,
            "导出完成",
            f"已导出结构化清单和 {len(board_entries)} 张资产图片。"
            + (
                f"\n同时生成 {len(board_paths)} 页资产展示板。"
                if board_paths else ""
            ),
        )

    def _production_assets(self) -> tuple[AssetItem, ...]:
        if self._state is None:
            return ()
        return tuple(
            item
            for item in self._state.assets
            if item.plan_id == self._state.selected_plan_id
        )

    def _sync_production_specs(self) -> None:
        if self._store is None or self._state is None:
            QMessageBox.information(self, "尚未打开项目", "请先打开资产拆分项目。")
            return
        assets = self._production_assets()
        if not assets:
            QMessageBox.information(
                self,
                "没有资产清单",
                "请先在当前拆分方案中建立资产清单。",
            )
            return
        current_ids = {item.asset_id for item in assets}
        retained = tuple(
            item
            for item in self._state.production_specs
            if item.asset_id not in current_ids
        )
        specs = synchronize_production_specs(
            assets,
            (
                item
                for item in self._state.production_specs
                if item.asset_id in current_ids
            ),
        )
        self._store.replace_production_specs((*retained, *specs))
        self._state = self._store.state
        self._refresh_production_specs()
        self.statusBar().showMessage(
            f"已同步 {len(specs)} 项生产规格；用户修改内容保持不变。",
            5000,
        )

    def _refresh_production_specs(self, select_asset_id: str = "") -> None:
        if not hasattr(self, "production_tree"):
            return
        current = select_asset_id
        if not current and self.production_tree.currentItem() is not None:
            current = str(
                self.production_tree.currentItem().data(
                    0, Qt.ItemDataRole.UserRole
                )
                or ""
            )
        self.production_tree.clear()
        if self._state is None:
            self.production_summary.setText("尚未打开项目。")
            return
        assets = {item.asset_id: item for item in self._production_assets()}
        specs = [
            item
            for item in self._state.production_specs
            if item.asset_id in assets
        ]
        for spec in specs:
            asset = assets[spec.asset_id]
            row = QTreeWidgetItem(
                [
                    spec.asset_code,
                    asset.name,
                    PRODUCTION_STATUS_LABELS.get(spec.status, spec.status),
                    asset.production_priority,
                    asset.reuse_group or "—",
                    spec.ue_destination,
                ]
            )
            row.setData(0, Qt.ItemDataRole.UserRole, spec.asset_id)
            self.production_tree.addTopLevelItem(row)
            if spec.asset_id == current:
                self.production_tree.setCurrentItem(row)
        if self.production_tree.currentItem() is None and self.production_tree.topLevelItemCount():
            self.production_tree.setCurrentItem(self.production_tree.topLevelItem(0))
        missing = len(assets) - len(specs)
        approved = sum(item.status == "approved" for item in specs)
        self.production_summary.setText(
            f"当前方案 {len(assets)} 项资产 · {len(specs)} 项生产规格 · "
            f"已通过 {approved} 项"
            + (f" · 待同步 {missing} 项" if missing else "")
        )

    def _current_production_spec(self) -> AssetProductionSpec | None:
        if self._state is None or self.production_tree.currentItem() is None:
            return None
        asset_id = str(
            self.production_tree.currentItem().data(
                0, Qt.ItemDataRole.UserRole
            )
            or ""
        )
        return next(
            (
                item
                for item in self._state.production_specs
                if item.asset_id == asset_id
            ),
            None,
        )

    def _show_production_spec(self, _current=None, _previous=None) -> None:
        spec = self._current_production_spec()
        if spec is None:
            return
        self.production_code.setText(spec.asset_code)
        _set_combo_data(self.production_status, spec.status)
        self.production_dimensions.setText(spec.target_dimensions_cm)
        self.production_pivot.setText(spec.pivot_policy)
        self.production_geometry.setPlainText(spec.geometry_strategy)
        self.production_materials.setText("，".join(spec.material_slots))
        self.production_textures.setText("，".join(spec.texture_sets))
        self.production_lod.setText(spec.lod_policy)
        self.production_collision.setText(spec.collision_policy)
        _set_combo_data(self.production_nanite, spec.nanite_policy)
        self.production_destination.setText(spec.ue_destination)
        self.production_dependencies.setText(
            "，".join(spec.dependency_asset_ids)
        )
        self.production_deliverables.setText("，".join(spec.deliverables))
        self.production_notes.setPlainText(spec.notes)

    def _save_production_spec(self) -> None:
        if self._store is None or self._state is None:
            return
        spec = self._current_production_spec()
        if spec is None:
            QMessageBox.information(self, "未选择规格", "请先选择一项生产规格。")
            return
        updated = replace(
            spec,
            asset_code=self.production_code.text().strip(),
            status=str(self.production_status.currentData()),
            target_dimensions_cm=self.production_dimensions.text().strip(),
            pivot_policy=self.production_pivot.text().strip(),
            geometry_strategy=self.production_geometry.toPlainText().strip(),
            material_slots=_split_list(self.production_materials.text()),
            texture_sets=_split_list(self.production_textures.text()),
            lod_policy=self.production_lod.text().strip(),
            collision_policy=self.production_collision.text().strip(),
            nanite_policy=str(self.production_nanite.currentData()),
            ue_destination=self.production_destination.text().strip(),
            dependency_asset_ids=_split_list(
                self.production_dependencies.text()
            ),
            deliverables=_split_list(self.production_deliverables.text()),
            notes=self.production_notes.toPlainText().strip(),
            user_modified=True,
            updated_at=utc_now(),
        )
        values = tuple(
            updated if item.asset_id == updated.asset_id else item
            for item in self._state.production_specs
        )
        try:
            validate_production_specs(self._state.assets, values)
            self._store.replace_production_specs(values)
        except ValueError as exc:
            QMessageBox.warning(self, "生产规格无效", str(exc))
            return
        self._state = self._store.state
        self._refresh_production_specs(updated.asset_id)
        self.statusBar().showMessage("生产规格已保存。", 4000)

    def _export_production_handoff(self, format_id: str) -> None:
        if self._store is None or self._state is None:
            QMessageBox.information(self, "尚未打开项目", "请先打开资产拆分项目。")
            return
        assets = self._production_assets()
        asset_ids = {item.asset_id for item in assets}
        specs = tuple(
            item
            for item in self._state.production_specs
            if item.asset_id in asset_ids
        )
        if not assets or len(specs) != len(assets):
            QMessageBox.information(
                self,
                "生产规格未完成",
                "请先点击“同步当前方案”，并确认每项资产的生产规格。",
            )
            return
        try:
            payload = build_handoff_payload(
                project_id=self._state.project_id,
                project_title=self._state.title,
                plan=self._selected_plan(),
                assets=assets,
                specs=specs,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "无法导出", str(exc))
            return
        extension = "csv" if format_id == "csv" else "json"
        filter_text = "CSV (*.csv)" if format_id == "csv" else "JSON (*.json)"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出资产生产交接",
            f"{self._state.title}_资产生产交接.{extension}",
            filter_text,
        )
        if not path:
            return
        try:
            output = (
                export_handoff_csv(path, payload)
                if format_id == "csv"
                else export_handoff_json(path, payload)
            )
            self._store.append_export(
                {
                    "export_id": str(uuid.uuid4()),
                    "type": "asset_production_handoff",
                    "format": format_id,
                    "plan_id": self._state.selected_plan_id,
                    "asset_count": len(assets),
                    "path": str(output),
                    "created_at": utc_now(),
                }
            )
            self._state = self._store.state
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.statusBar().showMessage(f"生产交接已导出：{output}", 5000)

    def _refresh_asset_tree(self, select_id: str = "") -> None:
        self.asset_tree.blockSignals(True)
        try:
            self.asset_tree.clear()
            if self._state is None:
                return
            items = {}
            current_assets = [
                asset for asset in self._state.assets
                if asset.plan_id == self._state.selected_plan_id
            ]
            pending = list(current_assets)
            for _pass in range(8):
                next_pending = []
                for index, asset in enumerate(pending):
                    parent = items.get(asset.parent_asset_id)
                    if asset.parent_asset_id and parent is None:
                        next_pending.append(asset)
                        continue
                    item = (
                        QTreeWidgetItem(parent)
                        if parent is not None
                        else QTreeWidgetItem(self.asset_tree)
                    )
                    item.setData(0, Qt.ItemDataRole.UserRole, asset.asset_id)
                    item.setFlags(
                        item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    item.setCheckState(
                        0,
                        Qt.CheckState.Checked
                        if asset.selected_for_generation
                        else Qt.CheckState.Unchecked,
                    )
                    item.setText(1, asset.name)
                    item.setText(2, CATEGORY_LABELS.get(asset.category, asset.category))
                    item.setText(3, str(asset.level))
                    item.setText(
                        4,
                        SOURCE_LABELS.get(
                            asset.evidence_kind,
                            asset.evidence_kind,
                        ),
                    )
                    item.setText(
                        5,
                        PRIORITY_LABELS.get(
                            asset.production_priority,
                            asset.production_priority,
                        ),
                    )
                    item.setToolTip(1, asset.visible_evidence)
                    items[asset.asset_id] = item
                    if asset.asset_id == select_id:
                        item.setSelected(True)
                if not next_pending:
                    pending = []
                    break
                pending = next_pending
            for asset in pending:
                item = QTreeWidgetItem(self.asset_tree)
                item.setData(0, Qt.ItemDataRole.UserRole, asset.asset_id)
                item.setText(1, asset.name)
                item.setText(2, CATEGORY_LABELS.get(asset.category, asset.category))
                items[asset.asset_id] = item
            self.asset_tree.expandAll()
            self.inventory_summary.setText(
                f"当前方案共 {len(current_assets)} 项；"
                f"用户修订 {sum(item.user_modified for item in current_assets)} 项；"
                f"待生成 {sum(item.selected_for_generation for item in current_assets)} 项。"
            )
        finally:
            self.asset_tree.blockSignals(False)
        if select_id:
            self._select_asset_by_id(select_id)
        self._refresh_production_specs(select_id)

    def _refresh_reference_list(self) -> None:
        self.reference_list.clear()
        if self._state is None:
            return
        for image in self._state.source_images:
            if image.role == "reference":
                self.reference_list.addItem(
                    f"{image.original_filename} · {image.width}×{image.height} · "
                    f"{image.sha256[:10]}…"
                )

    def _refresh_generation_list(self) -> None:
        self.generation_list.clear()
        if self._state is None:
            return
        for record in reversed(self._state.generations):
            asset = self._asset_by_id(record.asset_id)
            if asset is None or asset.plan_id != self._state.selected_plan_id:
                continue
            name = asset.name if asset else record.asset_id
            status = "完成" if record.status == "completed" else "失败"
            item = QListWidgetItem(
                f"{status} · {name} · "
                f"{GENERATION_KIND_LABELS.get(record.output_kind, record.output_kind)} · "
                f"{record.provider_id}/{record.model_id}"
            )
            if record.error_message:
                item.setToolTip(record.error_message)
                item.setStatusTip(record.error_message)
            self.generation_list.addItem(item)

    def _refresh_overlays(self) -> None:
        if self._state is None:
            self.canvas.clear_region_overlays()
            return
        selected_ids = {
            asset.asset_id for asset in self._selected_assets()
        }
        specs = []
        current_assets = [
            asset for asset in self._state.assets
            if asset.plan_id == self._state.selected_plan_id
        ]
        for index, asset in enumerate(current_assets):
            colour = (
                "#81C784"
                if asset.user_modified
                else (
                    "#FFD166"
                    if asset.evidence_kind == "ai_inference"
                    else ASSET_COLOURS[index % len(ASSET_COLOURS)]
                )
            )
            specs.append(
                RegionOverlaySpec(
                    region_id=asset.asset_id,
                    name=f"{index + 1:02d} {asset.name}",
                    normalized_rect=asset.normalized_rect,
                    colour=colour,
                    selected=asset.asset_id in selected_ids,
                    muted=bool(
                        selected_ids and asset.asset_id not in selected_ids
                    ),
                )
            )
        self.canvas.set_region_overlays(specs)
        self.canvas.set_regions_visible(self._state.regions_visible)

    def _asset_selection_changed(self) -> None:
        asset = self._selected_asset()
        self.asset_task_button.setEnabled(bool(self._selected_assets()))
        if asset is None:
            return
        self._populate_detail(asset)
        self.canvas.clear_overlay()
        self._refresh_overlays()
        self.canvas.select_regions(
            item.asset_id for item in self._selected_assets()
        )
        if self._state is not None and self._store is not None:
            self._state = replace(
                self._state,
                selected_asset_id=asset.asset_id,
            )
            self._store.save(self._state)
            self._state = self._store.state

    def _asset_check_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0 or self._store is None or self._state is None:
            return
        asset_id = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        asset = self._asset_by_id(asset_id)
        if asset is None:
            return
        updated = replace(
            asset,
            selected_for_generation=(
                item.checkState(0) == Qt.CheckState.Checked
            ),
            updated_at=utc_now(),
        )
        assets = tuple(
            updated if value.asset_id == asset_id else value
            for value in self._state.assets
        )
        self._push_asset_state(
            assets,
            self._state.generations,
            select_id=asset_id,
            text="更改生成选择",
        )

    def _populate_detail(self, asset: AssetItem) -> None:
        self.detail_name.setText(asset.name)
        index = self.detail_category.findData(asset.category)
        if index >= 0:
            self.detail_category.setCurrentIndex(index)
        else:
            self.detail_category.setEditText(asset.category)
        self.detail_semantic.setText(asset.semantic_type)
        self.detail_parent.setText(asset.parent_asset_id)
        self.detail_reuse.setText(asset.reuse_group)
        priority = self.detail_priority.findData(asset.production_priority)
        if priority >= 0:
            self.detail_priority.setCurrentIndex(priority)
        self.detail_source.setText(
            SOURCE_LABELS.get(asset.evidence_kind, asset.evidence_kind)
            + f" · 可信度 {asset.confidence:.2f}"
        )
        self.detail_rect.setText(
            ", ".join(f"{value:.4f}" for value in asset.normalized_rect)
        )
        self.detail_evidence.setPlainText(asset.visible_evidence)
        self.detail_inference.setPlainText(asset.inferred_details)
        self.detail_uncertainty.setPlainText(asset.uncertainty)
        self.detail_strategy.setPlainText(asset.production_strategy)
        self.detail_material.setPlainText(asset.material_notes)

    def _select_asset_by_id(self, asset_id: str) -> None:
        iterator = self.asset_tree.findItems(
            "",
            Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive,
            1,
        )
        for item in iterator:
            if str(item.data(0, Qt.ItemDataRole.UserRole) or "") == asset_id:
                self.asset_tree.setCurrentItem(item)
                item.setSelected(True)
                break

    def focus_entity(self, entity_type: str, entity_id: str) -> None:
        if entity_type == "asset" and entity_id:
            self.workflow_tabs.setCurrentIndex(0)
            self.manual_tabs.setCurrentIndex(1)
            self._select_asset_by_id(entity_id)

    def _select_assets_by_ids(self, asset_ids: object) -> None:
        selected = {str(item) for item in asset_ids}
        self.asset_tree.blockSignals(True)
        try:
            iterator = self.asset_tree.findItems(
                "",
                Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive,
                1,
            )
            current = None
            for item in iterator:
                asset_id = str(
                    item.data(0, Qt.ItemDataRole.UserRole) or ""
                )
                item.setSelected(asset_id in selected)
                if current is None and asset_id in selected:
                    current = item
            if current is not None:
                self.asset_tree.setCurrentItem(current)
        finally:
            self.asset_tree.blockSignals(False)
        self._asset_selection_changed()

    def _selected_asset(self) -> AssetItem | None:
        items = self.asset_tree.selectedItems()
        if not items:
            return None
        asset_id = str(
            items[0].data(0, Qt.ItemDataRole.UserRole) or ""
        )
        return self._asset_by_id(asset_id)

    def _selected_assets(self) -> list[AssetItem]:
        values = []
        for item in self.asset_tree.selectedItems():
            asset = self._asset_by_id(
                str(item.data(0, Qt.ItemDataRole.UserRole) or "")
            )
            if asset is not None:
                values.append(asset)
        return values

    def _send_selected_assets_to_review_center(self) -> None:
        if self._store is None or self._state is None:
            return
        assets = self._selected_assets()
        if not assets:
            QMessageBox.information(self, "尚未选择资产", "请先在资产清单中选择一项或多项资产。")
            return
        payloads = []
        for asset in assets:
            details = [
                f"分类：{CATEGORY_LABELS.get(asset.category, asset.category)}",
                f"层级：{asset.level}",
                f"制作策略：{asset.production_strategy or '待补充'}",
                f"可见依据：{asset.visible_evidence or '未记录'}",
            ]
            if asset.uncertainty:
                details.append(f"不确定性：{asset.uncertainty}")
            priority = asset.production_priority
            if priority not in {"critical", "high", "medium", "low"}:
                priority = "medium"
            payloads.append(
                {
                    "title": f"制作与复核资产：{asset.name}",
                    "description": "\n".join(details),
                    "acceptance_criteria": (
                        "按当前拆分方案完成该资产，并在目标版本中核对轮廓、"
                        "尺度、复用关系和与原画可见证据的一致性。"
                    ),
                    "priority": priority,
                    "source_module_id": "scenelens.asset_breakdown",
                    "source_project_id": self._state.project_id,
                    "source_project_title": self._state.title,
                    "source_project_path": str(self._store.root),
                    "source_entity_type": "asset_item",
                    "source_entity_id": asset.asset_id,
                    "source_version_id": (
                        self._state.main_image.sha256
                        if self._state.main_image is not None
                        else ""
                    ),
                    "labels": ("资产拆分", asset.category, asset.semantic_type),
                }
            )
        self.review_task_requested.emit(payloads)

    def _asset_by_id(self, asset_id: str) -> AssetItem | None:
        if self._state is None:
            return None
        return next(
            (
                asset
                for asset in self._state.assets
                if asset.asset_id == asset_id
            ),
            None,
        )

    def _push_asset_state(
        self,
        assets: tuple[AssetItem, ...],
        generations: tuple[GenerationRecord, ...],
        *,
        select_id: str = "",
        text: str,
    ) -> None:
        if self._state is None or self._store is None:
            return
        command = _AssetStateCommand(
            self,
            before_assets=self._state.assets,
            before_generations=self._state.generations,
            after_assets=tuple(assets),
            after_generations=tuple(generations),
            select_id=select_id,
            text=text,
        )
        self._undo_stack.push(command)

    def _restore_asset_state(
        self,
        assets: tuple[AssetItem, ...],
        generations: tuple[GenerationRecord, ...],
        *,
        select_id: str = "",
    ) -> None:
        if self._state is None or self._store is None:
            return
        self._state = replace(
            self._state,
            assets=tuple(assets),
            generations=tuple(generations),
            selected_asset_id=select_id,
        )
        self._store.save(self._state)
        self._state = self._store.state
        self._refresh_asset_tree(select_id=select_id)
        self._refresh_generation_list()
        self._refresh_overlays()

    def _undo_requested(self) -> None:
        focus = self.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit)):
            focus.undo()
            return
        self._undo_stack.undo()

    def _redo_requested(self) -> None:
        focus = self.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit)):
            focus.redo()
            return
        self._undo_stack.redo()

    def _delete_shortcut_requested(self) -> None:
        focus = self.focusWidget()
        if focus is self.asset_tree or focus is self.asset_tree.viewport():
            self._delete_selected()

    def _set_regions_visible(self, visible: bool) -> None:
        self.canvas.set_regions_visible(visible)
        if self._state is not None and self._store is not None:
            self._state = replace(self._state, regions_visible=visible)
            self._store.save(self._state)
            self._state = self._store.state

    def _view_state_changed(
        self,
        zoom: float,
        center_x: float,
        center_y: float,
    ) -> None:
        if self._state is None or self._store is None or self._restoring:
            return
        self._state = replace(
            self._state,
            zoom_factor=zoom,
            center_x=center_x,
            center_y=center_y,
        )
        self._store.save(self._state)
        self._state = self._store.state

    def _provider_changed(
        self,
        combo: QComboBox,
        model_edit: QLineEdit,
        key_edit: QLineEdit,
        capability: ProviderCapability,
        *,
        model_combo: QComboBox | None = None,
    ) -> None:
        provider_id = combo.currentData()
        if provider_id is None:
            return
        provider = self._provider_registry.get(str(provider_id))
        default_model = provider.manifest.model_for(capability)
        if model_combo is not None:
            model_combo.blockSignals(True)
            try:
                model_combo.clear()
                choices = provider.manifest.model_choices_for(capability)
                if choices:
                    for model_id, label in choices:
                        model_combo.addItem(label, model_id)
                    index = model_combo.findData(default_model)
                    if index >= 0:
                        model_combo.setCurrentIndex(index)
                    else:
                        model_combo.setEditText(default_model)
                else:
                    model_combo.setEditText(default_model)
            finally:
                model_combo.blockSignals(False)
        else:
            model_edit.setText(default_model)
        secret = self._credential_store.get(
            provider.manifest.credential_target
        )
        key_edit.setText(secret or "")

    def _sync_ai_controls(self, source: str) -> None:
        if self._syncing_ai_controls:
            return
        self._syncing_ai_controls = True
        try:
            vision_controls = {
                "manual_vision": (
                    self.vision_provider_combo,
                    self.vision_model_edit,
                    self.vision_key_edit,
                ),
                "automatic_vision": (
                    self.auto_vision_provider_combo,
                    self.auto_vision_model_edit,
                    self.auto_vision_key_edit,
                ),
                "prompt_vision": (
                    self.prompt_panel.provider_combo,
                    self.prompt_panel.model_edit,
                    self.prompt_panel.key_edit,
                ),
            }
            if source in vision_controls:
                source_provider, source_model, source_key = vision_controls[
                    source
                ]
                for name, controls in vision_controls.items():
                    if name == source:
                        continue
                    target_provider, target_model, target_key = controls
                    _set_combo_data(
                        target_provider,
                        source_provider.currentData(),
                    )
                    target_model.setText(source_model.text())
                    target_key.setText(source_key.text())
                self._sync_matching_credential_fields(
                    source_provider,
                    source_key,
                )
                return

            if source == "manual_image":
                source_provider = self.image_provider_combo
                source_model = self.image_model_combo
                source_key = self.image_key_edit
                source_resolution = self.image_resolution_combo
                target_provider = self.auto_image_provider_combo
                target_model = self.auto_image_model_combo
                target_key = self.auto_image_key_edit
                target_resolution = self.auto_resolution_combo
            elif source == "automatic_image":
                source_provider = self.auto_image_provider_combo
                source_model = self.auto_image_model_combo
                source_key = self.auto_image_key_edit
                source_resolution = self.auto_resolution_combo
                target_provider = self.image_provider_combo
                target_model = self.image_model_combo
                target_key = self.image_key_edit
                target_resolution = self.image_resolution_combo
            else:
                return
            _set_combo_data(target_provider, source_provider.currentData())
            _set_model_combo(target_model, _combo_model_id(source_model))
            target_key.setText(source_key.text())
            _set_combo_data(
                target_resolution,
                source_resolution.currentData(),
            )
            self._sync_matching_credential_fields(
                source_provider,
                source_key,
            )
        finally:
            self._syncing_ai_controls = False

    def _sync_matching_credential_fields(
        self,
        source_provider: QComboBox,
        source_key: QLineEdit,
    ) -> None:
        provider_id = source_provider.currentData()
        if provider_id is None:
            return
        credential_target = self._provider_registry.get(
            str(provider_id)
        ).manifest.credential_target
        controls = (
            (self.vision_provider_combo, self.vision_key_edit),
            (self.auto_vision_provider_combo, self.auto_vision_key_edit),
            (self.image_provider_combo, self.image_key_edit),
            (self.auto_image_provider_combo, self.auto_image_key_edit),
            (
                self.prompt_panel.provider_combo,
                self.prompt_panel.key_edit,
            ),
        )
        for provider_combo, key_edit in controls:
            target_provider_id = provider_combo.currentData()
            if target_provider_id is None:
                continue
            target_manifest = self._provider_registry.get(
                str(target_provider_id)
            ).manifest
            if target_manifest.credential_target == credential_target:
                key_edit.setText(source_key.text())

    def _save_provider_key(
        self,
        combo: QComboBox,
        key_edit: QLineEdit,
    ) -> None:
        provider_id = combo.currentData()
        if provider_id is None:
            return
        provider = self._provider_registry.get(str(provider_id))
        secret = key_edit.text().strip()
        try:
            if secret:
                self._credential_store.set(
                    provider.manifest.credential_target,
                    secret,
                )
                self.statusBar().showMessage(
                    "API Key 已保存到 Windows 系统凭据。", 3500
                )
            else:
                self._credential_store.delete(
                    provider.manifest.credential_target
                )
        except OSError as exc:
            QMessageBox.warning(self, "系统凭据保存失败", str(exc))

    def _current_profile(self) -> dict:
        if self._state is None:
            return {}
        return next(
            (
                dict(item)
                for item in self._profiles["scene_types"]
                if item["id"] == self._state.scene_type
            ),
            {},
        )

    def _start_worker(self, kind: str, operation, callback) -> None:
        generation = self._generation_counter.get(kind, 0) + 1
        self._generation_counter[kind] = generation
        worker = FunctionWorker("asset_breakdown", kind, generation, operation)
        self._callbacks[(kind, generation)] = callback
        worker.signals.result.connect(self._worker_result)
        worker.signals.error.connect(self._worker_error)
        worker.signals.finished.connect(
            lambda _role, _kind, _generation, value=worker: (
                self._workers.discard(value)
            )
        )
        self._workers.add(worker)
        self._thread_pool.start(worker)

    def _worker_result(
        self,
        _role: str,
        kind: str,
        generation: int,
        result: object,
    ) -> None:
        if generation != self._generation_counter.get(kind):
            return
        callback = self._callbacks.pop((kind, generation), None)
        if callable(callback):
            callback(result)

    def _worker_error(
        self,
        _role: str,
        kind: str,
        generation: int,
        message: str,
        trace: str,
    ) -> None:
        if generation != self._generation_counter.get(kind):
            return
        self._callbacks.pop((kind, generation), None)
        LOGGER.error("Asset breakdown %s failed:\n%s", kind, trace)
        if kind == "advisory":
            self._ai_cancellation = None
            self.understand_button.setEnabled(True)
            self.cancel_understanding_button.setEnabled(False)
            title = "场景结构分析失败"
        elif kind == "ai":
            self._ai_cancellation = None
            self.analyze_button.setEnabled(True)
            self.cancel_analysis_button.setEnabled(False)
            title = "资产清单生成失败"
        elif kind == "generate":
            self._image_cancellation = None
            self.generate_button.setEnabled(True)
            self.cancel_generation_button.setEnabled(False)
            title = "资产图片生成失败"
        elif kind == "automatic":
            self._automatic_cancellation = None
            self.auto_start_button.setEnabled(True)
            self.auto_cancel_button.setEnabled(False)
            self.auto_status.setText("状态：自动资产板失败 · 请查看错误原因")
            title = "自动资产板失败"
        elif kind == "prompt":
            self._prompt_cancellation = None
            self.prompt_panel.set_busy(False)
            self.prompt_panel.status_label.setText(
                "提示语生成失败；已有版本和手动内容均已保留。"
            )
            title = "资产拆分提示语失败"
        else:
            title = "处理失败"
        QMessageBox.warning(self, title, message)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.canvas.clear_overlay()
            if self.region_mode_action.isChecked():
                self.region_mode_action.setChecked(False)
            else:
                self.canvas.cancel_region_creation()
            self.statusBar().showMessage("已退出当前遮罩或框选工具。", 2500)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_fields()
        if self._ai_cancellation is not None:
            self._ai_cancellation.cancel()
        if self._image_cancellation is not None:
            self._image_cancellation.cancel()
        if self._automatic_cancellation is not None:
            self._automatic_cancellation.cancel()
        if self._prompt_cancellation is not None:
            self._prompt_cancellation.cancel()
        self._execution.close()
        if self._store is not None:
            self._store.close()
            self._store = None
        super().closeEvent(event)


def _safe_folder_name(value: str) -> str:
    forbidden = '<>:"/\\|?*'
    result = "".join("_" if character in forbidden else character for character in value)
    return result.strip(" .")[:80] or "未命名资产拆分"


def _split_list(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item.strip()
            for item in value.replace("，", ",").replace("；", ",").split(",")
            if item.strip()
        )
    )


def _combo_model_id(combo: QComboBox) -> str | None:
    index = combo.currentIndex()
    if index >= 0 and combo.currentText() == combo.itemText(index):
        value = combo.itemData(index)
        if value:
            return str(value).strip() or None
    return combo.currentText().strip() or None


def _set_combo_data(combo: QComboBox, value: object) -> None:
    index = combo.findData(value)
    if index >= 0 and index != combo.currentIndex():
        combo.setCurrentIndex(index)


def _set_model_combo(combo: QComboBox, model_id: str | None) -> None:
    if not model_id:
        combo.setEditText("")
        return
    index = combo.findData(model_id)
    if index >= 0:
        combo.setCurrentIndex(index)
    else:
        combo.setEditText(model_id)


def _mask_png(mask: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(mask, mode="L").save(buffer, format="PNG")
    return buffer.getvalue()
