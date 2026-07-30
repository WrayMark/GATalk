from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import logging
from pathlib import Path
import uuid

import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, QThreadPool, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
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
    make_asset_board,
    write_asset_manifest,
)
from scenelens.modules.asset_breakdown.models import (
    ASSET_CATEGORIES,
    AssetBreakdownState,
    AssetItem,
    GenerationRecord,
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
from scenelens.providers.contracts import (
    CancellationToken,
    DataDisclosurePreview,
    ImageEditRequest,
    ProviderCapability,
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
            "SceneLens 不会自动上传。继续后，下面列出的图片副本和结构化"
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
            "商业保密内容是否允许上传由你的团队政策决定。AI 识别、分类、"
            "模块关系和不可见结构均为推断；生成补全不是原画事实。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#E6B450;")
        layout.addWidget(warning)
        if extra_notice:
            extra = QLabel(extra_notice)
            extra.setWordWrap(True)
            extra.setStyleSheet("color:#E6B450;")
            layout.addWidget(extra)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认并发送")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AssetBreakdownWindow(QMainWindow):
    workspace_home_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SceneLens — 资产拆分工作台")
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
        self._restoring = False

        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(
            min(4, max(2, QThread.idealThreadCount()))
        )
        self._provider_registry = create_default_provider_registry()
        self._execution = ProviderExecutionService()
        self._reviewer = AssetBreakdownReview()
        self._profiles = load_scene_profiles()
        try:
            self._credential_store = WindowsCredentialStore()
        except OSError:
            self._credential_store = MemoryCredentialStore()

        self._build_actions()
        self._build_toolbar()
        self._build_project_dock()
        self._build_central_ui()
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

        menu = self.menuBar().addMenu("文件")
        menu.addActions(
            [
                self.home_action,
                self.new_action,
                self.open_action,
                self.save_action,
                self.import_main_action,
                self.import_reference_action,
            ]
        )

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("资产拆分", self)
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
        dock.setMinimumWidth(280)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        form = QFormLayout()
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
        legend.setStyleSheet("color:#BDC1C6;")
        layout.addWidget(legend)
        layout.addStretch(1)
        dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_central_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.canvas = ImageCanvas(
            "将场景原画拖到这里，或点击“导入主原画”"
        )
        splitter.addWidget(self.canvas)
        tabs = QTabWidget()
        tabs.setMinimumWidth(500)
        tabs.addTab(self._build_inventory_tab(), "资产清单")
        tabs.addTab(self._build_detail_tab(), "资产详情")
        tabs.addTab(self._build_generation_tab(), "生成与导出")
        splitter.addWidget(tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([980, 520])
        self.setCentralWidget(splitter)

    def _build_inventory_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        provider_group = QGroupBox("AI 场景理解与资产拆分")
        provider_form = QFormLayout(provider_group)
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
        buttons = QWidget()
        button_layout = QHBoxLayout(buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.analyze_button = QPushButton("查看发送清单并开始拆分")
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
        layout.addWidget(self.asset_tree, 1)
        self.inventory_summary = QLabel("尚未生成资产清单。")
        self.inventory_summary.setWordWrap(True)
        layout.addWidget(self.inventory_summary)
        return root

    def _build_detail_tab(self) -> QWidget:
        content = QWidget()
        form = QFormLayout(content)
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

    def _build_generation_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        group = QGroupBox("只生成勾选的资产")
        form = QFormLayout(group)
        self.image_provider_combo = QComboBox()
        for provider in self._provider_registry.for_capability(
            ProviderCapability.IMAGE_EDIT
        ):
            self.image_provider_combo.addItem(
                provider.manifest.display_name,
                provider.manifest.provider_id,
            )
        self.image_model_edit = QLineEdit()
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
        form.addRow("图片供应商", self.image_provider_combo)
        form.addRow("模型 ID", self.image_model_edit)
        form.addRow("API Key", key_row)
        form.addRow("生成类型", self.generation_kind_combo)
        warning = QLabel(
            "生成结果是概念辅助，不是原画中不可见结构的事实，也不会自动成为"
            "生产资产。每项结果会保留模型、参数、来源区域和输入哈希。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#E6B450;")
        form.addRow(warning)
        generation_buttons = QWidget()
        button_layout = QHBoxLayout(generation_buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.generate_button = QPushButton("确认发送并生成勾选项")
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
        layout.addWidget(self.generation_list, 1)
        return root

    def _connect_signals(self) -> None:
        self.canvas.file_dropped.connect(self._import_main_path)
        self.canvas.region_created.connect(self._manual_region_created)
        self.canvas.region_selected.connect(self._select_asset_by_id)
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
        )
        self.title_edit.editingFinished.connect(self._save_fields)
        self.scene_type_combo.currentTextChanged.connect(
            lambda _value: self._save_fields()
        )
        self.goal_edit.textChanged.connect(self._mark_unsaved)
        self.notes_edit.textChanged.connect(self._mark_unsaved)
        self.asset_tree.itemSelectionChanged.connect(
            self._asset_selection_changed
        )
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
            "打开 SceneLens 资产拆分项目",
        )
        if not folder:
            return
        try:
            store = AssetBreakdownStore.open(folder)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法打开项目", str(exc))
            return
        self._attach_store(store)

    def _attach_store(self, store: AssetBreakdownStore) -> None:
        if self._store is not None:
            self._store.close()
        self._store = store
        self._state = store.state
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
            self._refresh_asset_tree()
            self._refresh_generation_list()
        finally:
            self._restoring = False
        self._load_main_image()
        self.statusBar().showMessage(f"已打开：{store.root}")

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

    def _start_ai_breakdown(self) -> None:
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
        self.statusBar().showMessage("AI 正在理解场景并规划资产…")

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
            output = self._reviewer.validate_output(execution.response.output)
            return output, execution

        self._start_worker("ai", operation, self._ai_breakdown_finished)

    def _ai_breakdown_finished(self, result: object) -> None:
        self._ai_cancellation = None
        self.analyze_button.setEnabled(True)
        self.cancel_analysis_button.setEnabled(False)
        if self._store is None or self._state is None:
            return
        output, execution = result
        main = self._state.main_image
        if main is None:
            return
        incoming = tuple(
            asset_from_ai(item, source_image_id=main.image_id)
            for item in output["assets"]
        )
        assets = merge_ai_assets(self._state.assets, incoming)
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
                },
                "result_summary": {
                    "scene_understanding": output["scene_understanding"],
                    "production_strategy": output["production_strategy"],
                    "relationships": output["relationships"],
                    "uncertainties": output["uncertainties"],
                },
                "created_at": utc_now(),
            }
        )
        self._state = self._store.state
        self._refresh_asset_tree()
        self._refresh_overlays()
        self.statusBar().showMessage(
            f"资产拆分完成：{len(incoming)} 项；AI 推断等待用户校正。",
            5000,
        )

    def _cancel_analysis(self) -> None:
        if self._ai_cancellation is not None:
            self._ai_cancellation.cancel()
            self.statusBar().showMessage("正在取消 AI 资产拆分…")

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
        )
        self._store.add_or_replace_asset(asset)
        self._state = self._store.state
        self._refresh_asset_tree(select_id=asset.asset_id)
        self._refresh_overlays()

    def _split_selected(self) -> None:
        asset = self._selected_asset()
        if asset is None or self._store is None or self._state is None:
            return
        children = split_asset(asset)
        assets = tuple(
            item for item in self._state.assets if item.asset_id != asset.asset_id
        ) + children
        self._store.replace_assets(assets)
        self._state = self._store.state
        self._refresh_asset_tree(select_id=children[0].asset_id)
        self._refresh_overlays()

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
        self._store.replace_assets(assets)
        self._state = self._store.state
        self._refresh_asset_tree(select_id=merged.asset_id)
        self._refresh_overlays()

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
        for asset in selected:
            self._store.delete_asset(asset.asset_id)
        self._state = self._store.state
        self._refresh_asset_tree()
        self._refresh_generation_list()
        self._refresh_overlays()

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
        self._store.add_or_replace_asset(updated)
        self._state = self._store.state
        self._refresh_asset_tree(select_id=updated.asset_id)
        self._refresh_overlays()
        self.statusBar().showMessage("用户修订已保存，不会被后续 AI 覆盖。", 3000)

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
        self._store.add_or_replace_asset(updated)
        self._state = self._store.state
        self._refresh_asset_tree(select_id=asset_id)
        self._refresh_overlays()

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
        preview_request = ImageEditRequest(
            instruction=asset_generation_instruction(
                first_asset.to_dict(),
                output_kind=output_kind,
                scene_type=self._state.scene_type,
            ),
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
            model_id=self.image_model_edit.text().strip() or None,
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
        model_id = self.image_model_edit.text().strip() or None
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
                request = ImageEditRequest(
                    instruction=asset_generation_instruction(
                        asset.to_dict(),
                        output_kind=output_kind,
                        scene_type=scene_type,
                    ),
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
                    failures.append((asset.asset_id, str(exc)))
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
            return (
                successes,
                failures,
                output_kind,
                source_hash,
                cancellation.cancelled,
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
        successes, failures, output_kind, source_hash, cancelled = result
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
                    model_id=self.image_model_edit.text().strip(),
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
            f"生成结束：成功 {len(successes)}，失败 {len(failures)}{suffix}。",
            6000,
        )

    def _cancel_generation(self) -> None:
        if self._image_cancellation is not None:
            self._image_cancellation.cancel()
            self.statusBar().showMessage("正在取消；已完成的资产图片会保留…")

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
        ) or self._state.assets
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
        board_path = None
        if board_entries:
            board_path = folder / "asset_board.png"
            board_path.write_bytes(
                make_asset_board(
                    board_entries,
                    title=f"{self._state.title} — 资产展示板",
                )
            )
        self._store.append_export(
            {
                "export_id": str(uuid.uuid4()),
                "destination_hidden": True,
                "manifest_filename": manifest_path.name,
                "board_filename": board_path.name if board_path else "",
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
            + ("\n同时生成 asset_board.png。" if board_path else ""),
        )

    def _refresh_asset_tree(self, select_id: str = "") -> None:
        self.asset_tree.blockSignals(True)
        try:
            self.asset_tree.clear()
            if self._state is None:
                return
            items = {}
            pending = list(self._state.assets)
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
                f"共 {len(self._state.assets)} 项；"
                f"用户修订 {sum(item.user_modified for item in self._state.assets)} 项；"
                f"待生成 {sum(item.selected_for_generation for item in self._state.assets)} 项。"
            )
        finally:
            self.asset_tree.blockSignals(False)
        if select_id:
            self._select_asset_by_id(select_id)

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
            name = asset.name if asset else record.asset_id
            status = "完成" if record.status == "completed" else "失败"
            self.generation_list.addItem(
                f"{status} · {name} · "
                f"{GENERATION_KIND_LABELS.get(record.output_kind, record.output_kind)} · "
                f"{record.provider_id}/{record.model_id}"
            )

    def _refresh_overlays(self) -> None:
        if self._state is None:
            self.canvas.clear_region_overlays()
            return
        selected = self._selected_asset()
        selected_id = selected.asset_id if selected else ""
        specs = []
        for index, asset in enumerate(self._state.assets):
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
                    selected=asset.asset_id == selected_id,
                    muted=bool(selected_id and asset.asset_id != selected_id),
                )
            )
        self.canvas.set_region_overlays(specs)
        self.canvas.set_regions_visible(self._state.regions_visible)

    def _asset_selection_changed(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            return
        self._populate_detail(asset)
        self.canvas.clear_overlay()
        self._refresh_overlays()
        self.canvas.select_region(asset.asset_id)
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
        self._store.add_or_replace_asset(updated)
        self._state = self._store.state
        self.inventory_summary.setText(
            f"共 {len(self._state.assets)} 项；"
            f"待生成 {sum(item.selected_for_generation for item in self._state.assets)} 项。"
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
    ) -> None:
        provider_id = combo.currentData()
        if provider_id is None:
            return
        provider = self._provider_registry.get(str(provider_id))
        model_edit.setText(provider.manifest.model_for(capability))
        secret = self._credential_store.get(
            provider.manifest.credential_target
        )
        key_edit.setText(secret or "")

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
        if kind == "ai":
            self._ai_cancellation = None
            self.analyze_button.setEnabled(True)
            self.cancel_analysis_button.setEnabled(False)
            title = "AI 资产拆分失败"
        elif kind == "generate":
            self._image_cancellation = None
            self.generate_button.setEnabled(True)
            self.cancel_generation_button.setEnabled(False)
            title = "资产图片生成失败"
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
        self._execution.close()
        if self._store is not None:
            self._store.close()
            self._store = None
        super().closeEvent(event)


def _safe_folder_name(value: str) -> str:
    forbidden = '<>:"/\\|?*'
    result = "".join("_" if character in forbidden else character for character in value)
    return result.strip(" .")[:80] or "未命名资产拆分"


def _mask_png(mask: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(mask, mode="L").save(buffer, format="PNG")
    return buffer.getvalue()
