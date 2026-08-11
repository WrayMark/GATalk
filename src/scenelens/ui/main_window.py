from __future__ import annotations

from dataclasses import dataclass, replace
from io import BytesIO
import logging
import hashlib
import uuid
from functools import partial
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from scenelens.analysis.luminance import quantize_three_value_with_thresholds
from scenelens import __version__
from scenelens.analysis.grading import SafeGradeRecipe, apply_safe_grade
from scenelens.analysis.comparison_distributions import (
    compare_colour_distribution,
)
from scenelens.analysis.match_profile import MatchProfile, build_match_profile
from scenelens.analysis.models import (
    ImageMeasurements,
    DistributionComparison,
    LuminanceComparison,
    RenderSettings,
    SharedPaletteResult,
)
from scenelens.analysis.pipeline import render_image
from scenelens.analysis.region_analysis import (
    PairedRegionAnalysis,
    render_region_palette_source_mask,
)
from scenelens.analysis.preview_validation import (
    PreviewValidation,
    validate_concept_preview,
)
from scenelens.analysis.shared_palette import (
    palette_membership_mask,
    render_palette_source_mask,
)
from scenelens.core.analyzers import AnalyzerRequest
from scenelens.core.domain import (
    AIConceptPreview,
    AIRun,
    AIRunStatus,
    Annotation,
    Evidence,
    EvidenceSource,
    EvidenceType,
    Task,
    TaskPriority,
    TaskStatus,
)
from scenelens.imaging.loader import LoadedImage, load_image
from scenelens.imaging.provider_export import (
    ProviderImageExportOptions,
    prepare_provider_image,
)
from scenelens.imaging.qt import numpy_to_qimage
from scenelens.modules.visual_review import MODULE_ID
from scenelens.modules.visual_review.analyzers import (
    BASIC_MEASUREMENTS_ANALYZER_ID,
    LUMINANCE_COMPARISON_ANALYZER_ID,
    PAIRED_REGION_ANALYZER_ID,
    SHARED_PALETTE_ANALYZER_ID,
)
from scenelens.modules.visual_review.brief_measurements import (
    build_reference_measurement_fields,
)
from scenelens.modules.visual_review.comparison_results import (
    luminance_comparison_from_payload,
    luminance_comparison_to_payload,
    shared_palette_from_payload,
    shared_palette_to_payload,
)
from scenelens.modules.visual_review.composition_guides import (
    COMPOSITION_GUIDES,
    composition_guide,
)
from scenelens.modules.visual_review.presets import load_visual_review_presets
from scenelens.modules.visual_review.grading_io import (
    write_cube_lut,
    write_grade_png,
    write_grade_recipe,
)
from scenelens.modules.visual_review.preview_instructions import (
    PreviewProtectionControls,
    build_structured_preview_instruction,
)
from scenelens.modules.visual_review.review_evidence import (
    build_review_evidence_digest,
)
from scenelens.modules.visual_review.region_results import (
    paired_region_from_payload,
    paired_region_to_payload,
)
from scenelens.modules.visual_review.review_coordinator import (
    ReviewCoordinator,
    ReviewRunOutcome,
    review_outcome_from_payload,
    review_outcome_to_payload,
)
from scenelens.modules.visual_review.review_pack_io import (
    write_offline_review_pack,
)
from scenelens.modules.visual_review.review_services import (
    build_offline_review_pack,
)
from scenelens.modules.visual_review.reviews import (
    ArtDirectorReview,
    DeepArtDirectorReview,
    LightingReview,
    ReviewContext,
)
from scenelens.modules.visual_review.registry import (
    create_visual_review_registry,
)
from scenelens.modules.visual_review.ui.ai_review_panel import (
    AIReviewPanel,
    DataDisclosureDialog,
    ReviewPanelOptions,
)
from scenelens.modules.visual_review.ui.region_controller import (
    RegionController,
)
from scenelens.modules.visual_review.ui.optimization_lab import (
    ConceptPreviewOptions,
    OptimizationLabPanel,
)
from scenelens.modules.visual_review.ui.region_widgets import RegionPairPanel
from scenelens.storage.errors import ProjectLockedError, StorageError
from scenelens.storage.atomic import canonical_json
from scenelens.storage.models import (
    ArtBrief,
    BriefFieldValue,
    CanvasState,
    FieldSource,
    ImageAssetRecord,
    VersionRecord,
    WorkspaceState,
)
from scenelens.storage.project_store import (
    ProjectStore,
    utc_now,
)
from scenelens.storage.recent_projects import RecentProjects
from scenelens.storage.workbench_store import WorkbenchStore
from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditRequest,
    ImageEditResponse,
    ProviderCapability,
    disclosure_preview,
)
from scenelens.providers.credentials import (
    MemoryCredentialStore,
    WindowsCredentialStore,
)
from scenelens.providers.factory import create_default_provider_registry
from scenelens.ui.analysis_widgets import AnalysisSummaryWidget
from scenelens.ui.brief_widgets import (
    CREATIVE_INTENT_FIELDS,
    BriefEditorDialog,
    ReferenceVisualBriefDialog,
)
from scenelens.ui.comparison_widgets import ComparisonPanel
from scenelens.ui.image_canvas import (
    AnnotationOverlaySpec,
    GuideOverlaySpec,
    ImageCanvas,
)
from scenelens.ui.project_widgets import ProjectNavigator
from scenelens.ui.workers import FunctionWorker


LOGGER = logging.getLogger(__name__)
ROLE_LABELS = {"reference": "参考图", "current": "当前截图"}
INVALID_WINDOWS_NAME_CHARS = set('<>:"/\\|?*')


@dataclass(frozen=True)
class ConceptPreviewOutcome:
    entity: AIConceptPreview
    rgb: np.ndarray
    validation: PreviewValidation


class ImagePane(QWidget):
    def __init__(self, title: str, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "paneTitle")
        layout.addWidget(self.title_label)

        self.canvas = ImageCanvas(placeholder)
        layout.addWidget(self.canvas, 1)


class MainWindow(QMainWindow):
    workspace_home_requested = Signal()
    review_task_requested = Signal(object)

    def __init__(self, recent_projects: RecentProjects | None = None) -> None:
        super().__init__()
        self.setWindowTitle("GATalk — 游戏场景美术控制工作台")
        self.resize(1550, 900)
        self.setMinimumSize(1050, 650)

        self._images: dict[str, LoadedImage] = {}
        self._measurements: dict[str, ImageMeasurements] = {}
        self._asset_ids: dict[str, str | None] = {
            "reference": None,
            "current": None,
        }
        self._load_generation = {"reference": 0, "current": 0}
        self._render_generation = {"reference": 0, "current": 0}
        self._measure_generation = {"reference": 0, "current": 0}
        self._import_generation = {"reference": 0, "current": 0}
        self._brief_generation = 0
        self._comparison_generation = 0
        self._region_analysis_generation = 0
        self._mask_generation = 0
        self._ai_review_generation = 0
        self._match_generation = 0
        self._grade_generation = 0
        self._concept_generation = 0
        self._ai_cancellation: CancellationToken | None = None
        self._concept_cancellation: CancellationToken | None = None
        self._active_ai_run: AIRun | None = None
        self._active_concept_run: AIRun | None = None
        self._last_review_outcome: ReviewRunOutcome | None = None
        self._safe_grade_preview: np.ndarray | None = None
        self._safe_grade_recipe: SafeGradeRecipe | None = None
        self._concept_preview_rgb: np.ndarray | None = None
        self._last_concept_preview: AIConceptPreview | None = None
        self._last_preview_validation: PreviewValidation | None = None
        self._optimization_preview_visible = False
        self._active_mask: tuple[str, int] | None = None
        self._shared_palette_result: SharedPaletteResult | None = None
        self._active_region_analysis: (
            tuple[str, PairedRegionAnalysis] | None
        ) = None
        self._load_context: dict[
            str, dict[int, tuple[str | None, bool, CanvasState | None]]
        ] = {"reference": {}, "current": {}}
        self._measure_context: dict[
            str, dict[int, tuple[str | None, dict]]
        ] = {"reference": {}, "current": {}}
        self._import_context: dict[str, dict[int, tuple[str, str]]] = {
            "reference": {},
            "current": {},
        }
        self._active_jobs = 0
        self._ab_role = "reference"

        self._project_store: ProjectStore | None = None
        self._active_shot_id: str | None = None
        self._active_version_id: str | None = None
        self._workspace_template = WorkspaceState()
        self._workspace_dirty = False
        self._restoring_workspace = False
        self._recent_projects = recent_projects or RecentProjects()
        self._analyzer_registry = create_visual_review_registry()
        self._measurement_analyzer = self._analyzer_registry.get(
            MODULE_ID,
            BASIC_MEASUREMENTS_ANALYZER_ID,
        )
        self._shared_palette_analyzer = self._analyzer_registry.get(
            MODULE_ID,
            SHARED_PALETTE_ANALYZER_ID,
        )
        self._luminance_comparison_analyzer = self._analyzer_registry.get(
            MODULE_ID,
            LUMINANCE_COMPARISON_ANALYZER_ID,
        )
        self._paired_region_analyzer = self._analyzer_registry.get(
            MODULE_ID,
            PAIRED_REGION_ANALYZER_ID,
        )
        self._presets = load_visual_review_presets()
        self._provider_registry = create_default_provider_registry()
        self._reviewers = {
            "deep_art_director_review": DeepArtDirectorReview(),
            "art_director_review": ArtDirectorReview(),
            "lighting_review": LightingReview(),
        }
        self._review_coordinator = ReviewCoordinator(
            self._provider_registry,
            self._reviewers,
        )
        try:
            self._credential_store = WindowsCredentialStore()
        except OSError:
            LOGGER.warning(
                "Windows Credential Manager unavailable; using session memory."
            )
            self._credential_store = MemoryCredentialStore()

        self._thread_pool = QThreadPool(self)
        ideal = max(2, QThread.idealThreadCount())
        self._thread_pool.setMaxThreadCount(min(4, ideal))

        self._build_actions_and_menus()
        self._build_toolbar()
        self._build_central_ui()
        self._build_project_dock()
        self._build_status_bar()
        self._build_region_controller()
        self._connect_canvas_sync()
        self._refresh_recent_menu()

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(140)
        self._render_timer.timeout.connect(self._refresh_rendered_images)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(800)
        self._autosave_timer.timeout.connect(self._autosave_workspace)

        self._comparison_timer = QTimer(self)
        self._comparison_timer.setSingleShot(True)
        self._comparison_timer.setInterval(180)
        self._comparison_timer.timeout.connect(self._start_comparison_analysis)

        ab_action = QAction("切换 A/B", self)
        ab_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        ab_action.triggered.connect(self._toggle_ab)
        self.addAction(ab_action)

        escape_action = QAction("退出当前遮罩或工具", self)
        escape_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        escape_action.triggered.connect(self._escape_current_tool)
        self.addAction(escape_action)

        self.statusBar().showMessage(
            "可先新建/打开项目，也可直接拖入图片继续使用 M0.5 工作台。"
        )

    def _build_actions_and_menus(self) -> None:
        self.home_action = QAction("工作台首页", self)
        self.home_action.triggered.connect(
            lambda _checked=False: self.workspace_home_requested.emit()
        )

        self.new_project_action = QAction("新建项目…", self)
        self.new_project_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_project_action.triggered.connect(self._new_project_dialog)

        self.open_project_action = QAction("打开项目…", self)
        self.open_project_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_project_action.triggered.connect(self._open_project_dialog)

        self.save_project_action = QAction("保存项目", self)
        self.save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_project_action.setEnabled(False)
        self.save_project_action.triggered.connect(self._save_project_action)

        file_menu = self.menuBar().addMenu("文件")
        file_menu.addAction(self.home_action)
        file_menu.addSeparator()
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addAction(self.save_project_action)
        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu("最近项目")

        self._view_menu = self.menuBar().addMenu("视图")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具", self)
        toolbar.setObjectName("visualReviewToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel("项目："))
        toolbar.addAction(self.new_project_action)
        toolbar.addAction(self.open_project_action)
        toolbar.addAction(self.save_project_action)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("导入："))
        self.reference_button = QPushButton("参考图")
        self.reference_button.clicked.connect(
            partial(self._choose_image, "reference")
        )
        toolbar.addWidget(self.reference_button)

        self.current_button = QPushButton("当前截图 / 新版本")
        self.current_button.clicked.connect(partial(self._choose_image, "current"))
        toolbar.addWidget(self.current_button)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("显示："))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("原图", "original")
        self.mode_combo.addItem("灰度", "grayscale")
        self.mode_combo.addItem("三阶明度", "three_value")
        self.mode_combo.addItem("五阶明度", "five_value")
        self.mode_combo.addItem("曝光伪色（非真实 EV）", "exposure_false_colour")
        self.mode_combo.addItem("高光 / 暗部溢出", "clipping_warning")
        self.mode_combo.addItem("可调剪影", "silhouette")
        self.mode_combo.addItem("缩略图观察", "thumbnail_observation")
        self.mode_combo.addItem("明度模糊", "luminance_blur")
        self.mode_combo.addItem(
            "灯光明度代理图（非灰模）",
            "lighting_luminance_proxy",
        )
        self.mode_combo.setToolTip(
            "灯光明度代理图只能减弱色彩和细节干扰，不能从截图剥离材质与纹理。"
        )
        self.mode_combo.currentIndexChanged.connect(self._display_mode_changed)
        toolbar.addWidget(self.mode_combo)

        toolbar.addWidget(QLabel("模糊："))
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setRange(0, 200)
        self.blur_slider.setValue(0)
        self.blur_slider.setFixedWidth(145)
        self.blur_slider.valueChanged.connect(self._blur_changed)
        toolbar.addWidget(self.blur_slider)

        self.blur_label = QLabel("0.0")
        self.blur_label.setMinimumWidth(34)
        toolbar.addWidget(self.blur_label)

        toolbar.addWidget(QLabel("剪影阈值："))
        self.silhouette_slider = QSlider(Qt.Orientation.Horizontal)
        self.silhouette_slider.setRange(5, 95)
        self.silhouette_slider.setValue(45)
        self.silhouette_slider.setFixedWidth(100)
        self.silhouette_slider.setEnabled(False)
        self.silhouette_slider.valueChanged.connect(
            self._silhouette_threshold_changed
        )
        toolbar.addWidget(self.silhouette_slider)
        self.silhouette_label = QLabel("0.45")
        self.silhouette_label.setMinimumWidth(34)
        toolbar.addWidget(self.silhouette_label)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("对比："))
        self.comparison_combo = QComboBox()
        self.comparison_combo.addItem("双图并排", "split")
        self.comparison_combo.addItem("A/B 单图", "ab")
        self.comparison_combo.currentIndexChanged.connect(
            self._comparison_mode_changed
        )
        toolbar.addWidget(self.comparison_combo)

        self.ab_button = QPushButton("切换 A/B（Space）")
        self.ab_button.setEnabled(False)
        self.ab_button.clicked.connect(self._toggle_ab)
        toolbar.addWidget(self.ab_button)

        self.sync_checkbox = QCheckBox("同步视图")
        self.sync_checkbox.setChecked(True)
        self.sync_checkbox.toggled.connect(self._mark_workspace_dirty)
        toolbar.addWidget(self.sync_checkbox)

        reset_button = QPushButton("重置视图")
        reset_button.clicked.connect(self._reset_views)
        toolbar.addWidget(reset_button)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("构图辅助："))
        self.composition_guide_combo = QComboBox()
        self.composition_guide_combo.addItem("关闭", "none")
        for guide_id in (
            "thirds",
            "golden_ratio",
            "diagonals",
            "center",
            "triangle",
            "one_point_perspective",
            "two_point_perspective",
        ):
            guide = COMPOSITION_GUIDES[guide_id]
            self.composition_guide_combo.addItem(
                guide.display_name,
                guide.guide_id,
            )
        self.composition_guide_combo.setToolTip(
            "在左右画布叠加观察线；它是人工构图辅助，不是自动构图判断。"
        )
        self.composition_guide_combo.currentIndexChanged.connect(
            self._composition_guide_changed
        )
        toolbar.addWidget(self.composition_guide_combo)

    def _build_central_ui(self) -> None:
        self.reference_pane = ImagePane(
            "参考图",
            "拖入参考图\nPNG / JPG / JPEG / WebP",
        )
        self.current_pane = ImagePane(
            "当前截图",
            "拖入当前截图\nPNG / JPG / JPEG / WebP",
        )
        self.reference_pane.canvas.file_dropped.connect(
            partial(self._import_or_load, "reference")
        )
        self.current_pane.canvas.file_dropped.connect(
            partial(self._import_or_load, "current")
        )

        self.image_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.image_splitter.addWidget(self.reference_pane)
        self.image_splitter.addWidget(self.current_pane)
        self.image_splitter.setSizes([700, 700])
        self.image_splitter.setChildrenCollapsible(False)

        self.analysis_tabs = QTabWidget()
        self.analysis_tabs.setMinimumWidth(360)
        self.analysis_widgets = {
            "reference": AnalysisSummaryWidget("尚未导入参考图"),
            "current": AnalysisSummaryWidget("尚未导入当前截图"),
        }
        for role, widget in self.analysis_widgets.items():
            widget.palette.colour_selected.connect(
                partial(self._independent_palette_selected, role)
            )
        self.analysis_tabs.addTab(self.analysis_widgets["reference"], "参考分析")
        self.analysis_tabs.addTab(self.analysis_widgets["current"], "截图分析")
        self.comparison_panel = ComparisonPanel()
        self.comparison_panel.palette_selected.connect(
            self._shared_palette_selected
        )
        self.comparison_panel.thresholds_changed.connect(
            self._comparison_thresholds_changed
        )
        self.comparison_panel.independent_palette_selected.connect(
            self._independent_palette_selected
        )
        self.comparison_panel.distribution_parameters_changed.connect(
            self._schedule_comparison_analysis
        )
        self.region_panel = RegionPairPanel()
        self.comparison_panel.set_region_panel(self.region_panel)
        self.analysis_tabs.addTab(self.comparison_panel, "对比分析")
        self.ai_review_panel = AIReviewPanel(
            self._provider_registry.manifests()
        )
        self.ai_review_panel.review_requested.connect(
            self._start_ai_review
        )
        self.ai_review_panel.cancel_requested.connect(
            self._cancel_ai_review
        )
        self.ai_review_panel.credential_save_requested.connect(
            self._save_provider_credential
        )
        self.ai_review_panel.credential_delete_requested.connect(
            self._delete_provider_credential
        )
        self.ai_review_panel.task_requested.connect(
            self._confirm_review_task
        )
        self.ai_review_panel.annotations_selected.connect(
            self._show_lighting_annotations
        )
        self.ai_review_panel.annotation_tasks_requested.connect(
            self._confirm_annotation_tasks
        )
        self.ai_review_panel.offline_export_requested.connect(
            self._export_offline_review_pack
        )
        self.ai_review_panel.history_selected.connect(
            self._show_saved_ai_review
        )
        self.ai_review_panel.history_delete_requested.connect(
            self._delete_saved_ai_review
        )
        self.analysis_tabs.addTab(self.ai_review_panel, "AI 审阅与任务")
        self.optimization_panel = OptimizationLabPanel(
            self._provider_registry.manifests()
        )
        self.optimization_panel.match_requested.connect(
            self._start_match_profile
        )
        self.optimization_panel.safe_preview_requested.connect(
            self._start_safe_grade_preview
        )
        self.optimization_panel.show_original_requested.connect(
            self._show_safe_grade_original
        )
        self.optimization_panel.grade_export_requested.connect(
            self._export_safe_grade
        )
        self.optimization_panel.concept_requested.connect(
            self._start_concept_preview
        )
        self.optimization_panel.concept_cancel_requested.connect(
            self._cancel_concept_preview
        )
        self.optimization_panel.concept_tasks_requested.connect(
            self._confirm_concept_preview_tasks
        )
        self.optimization_panel.credential_save_requested.connect(
            self._save_provider_credential
        )
        self.optimization_panel.credential_delete_requested.connect(
            self._delete_provider_credential
        )
        self.analysis_tabs.addTab(self.optimization_panel, "优化实验室")
        self.analysis_tabs.currentChanged.connect(
            self._analysis_tab_changed
        )

        self.root_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.root_splitter.addWidget(self.image_splitter)
        self.root_splitter.addWidget(self.analysis_tabs)
        self.root_splitter.setSizes([780, 450])
        self.root_splitter.setStretchFactor(0, 1)
        self.root_splitter.setStretchFactor(1, 0)
        self.root_splitter.setCollapsible(0, False)
        self.root_splitter.setCollapsible(1, True)
        self.setCentralWidget(self.root_splitter)

    def _build_project_dock(self) -> None:
        self.project_navigator = ProjectNavigator()
        self.project_navigator.new_shot_requested.connect(
            self._new_shot_dialog
        )
        self.project_navigator.edit_brief_requested.connect(
            self._edit_art_brief
        )
        self.project_navigator.edit_reference_brief_requested.connect(
            self._edit_reference_visual_brief
        )
        self.project_navigator.shot_requested.connect(self._activate_shot)
        self.project_navigator.version_requested.connect(self._activate_version)

        self.project_dock = QDockWidget("项目 / Shot / Version", self)
        self.project_dock.setObjectName("projectNavigatorDock")
        self.project_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        self.project_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.project_dock.setWidget(self.project_navigator)
        self.project_dock.setMinimumWidth(235)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.project_dock)
        self._view_menu.addAction(self.project_dock.toggleViewAction())

    def _build_status_bar(self) -> None:
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(130)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)

    def _build_region_controller(self) -> None:
        self.region_controller = RegionController(
            self.reference_pane.canvas,
            self.current_pane.canvas,
            self.region_panel,
            self._presets,
            self,
        )
        self.region_controller.status_message.connect(
            self.statusBar().showMessage
        )
        self.region_controller.analysis_requested.connect(
            self._start_region_analysis
        )
        self.region_panel.region_palette_selected.connect(
            self._region_palette_selected
        )

    @staticmethod
    def _placeholder_panel(text: str) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("role", "muted")
        label.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(label)
        return panel

    def _connect_canvas_sync(self) -> None:
        self.reference_pane.canvas.view_state_changed.connect(
            partial(self._sync_from, "reference")
        )
        self.current_pane.canvas.view_state_changed.connect(
            partial(self._sync_from, "current")
        )

    def _new_project_dialog(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            "新建 GATalk 项目",
            "项目名称：",
        )
        if not accepted:
            return
        name = name.strip()
        if not self._is_valid_project_folder_name(name):
            QMessageBox.warning(
                self,
                "项目名称不可用",
                "项目名称不能为空，不能包含 Windows 文件名禁用字符，"
                "也不能以空格或句点结尾。",
            )
            return
        parent = QFileDialog.getExistingDirectory(self, "选择项目保存位置")
        if not parent:
            return
        self.create_project(Path(parent) / f"{name}.scenelens", name)

    def _open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开 GATalk 项目",
            "",
            "GATalk 项目 (project.json);;JSON 文件 (*.json)",
        )
        if path:
            self.open_project(Path(path))

    def create_project(self, root: Path, name: str) -> bool:
        if not self._prepare_project_switch():
            return False
        try:
            store = ProjectStore.create(root, name)
            self._activate_project_store(store)
            self._remember_project(store)
            self.statusBar().showMessage(f"项目已创建：{store.manifest.name}")
            return True
        except StorageError as exc:
            self._show_storage_error("无法创建项目", exc)
            return False

    def open_project(self, path: Path, read_only: bool = False) -> bool:
        if not self._prepare_project_switch():
            return False
        try:
            store = ProjectStore.open(path, read_only=read_only)
            self._activate_project_store(store)
            self._remember_project(store)
            mode = "（只读）" if store.read_only else ""
            self.statusBar().showMessage(
                f"项目已打开{mode}：{store.manifest.name}"
            )
            return True
        except ProjectLockedError as exc:
            return self._offer_read_only_open(path, exc)
        except StorageError as exc:
            self._show_storage_error("无法打开项目", exc)
            return False

    def _prepare_project_switch(self) -> bool:
        if self._project_store is None:
            return True
        if not self._flush_autosave(show_error=True):
            return False
        self._project_store.close()
        self._project_store = None
        self._active_shot_id = None
        self._active_version_id = None
        self.region_controller.set_context(None, None, None)
        self._invalidate_image_jobs()
        self._clear_role("reference")
        self._clear_role("current")
        self.project_navigator.clear_project()
        self.save_project_action.setEnabled(False)
        self.reference_button.setEnabled(True)
        self.current_button.setEnabled(True)
        self.setWindowTitle(f"GATalk — {__version__}")
        return True

    def _offer_read_only_open(
        self,
        path: Path,
        error: ProjectLockedError,
    ) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("项目已被其他进程打开")
        dialog.setText(str(error))
        dialog.setInformativeText(
            "可以只读打开以查看项目，或取消并回到当前界面。"
        )
        read_only_button = dialog.addButton(
            "只读打开",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton(
            "取消",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.exec()
        if dialog.clickedButton() is read_only_button:
            return self.open_project(path, read_only=True)
        return False

    def _activate_project_store(self, store: ProjectStore) -> None:
        self._invalidate_image_jobs()
        self._project_store = store
        self.save_project_action.setEnabled(not store.read_only)
        self.reference_button.setEnabled(not store.read_only)
        self.current_button.setEnabled(not store.read_only)
        suffix = " [只读]" if store.read_only else ""
        self.setWindowTitle(f"GATalk — {store.manifest.name}{suffix}")
        state = store.get_workspace_state()
        shots = store.list_shots()
        shot_ids = {shot.id for shot in shots}
        active_shot = (
            state.current_shot_id
            if state.current_shot_id in shot_ids
            else (shots[0].id if shots else None)
        )
        versions = store.list_versions(active_shot) if active_shot else ()
        version_ids = {version.id for version in versions}
        active_version = (
            state.current_version_id
            if state.current_version_id in version_ids
            else (versions[-1].id if versions else None)
        )

        self._restoring_workspace = True
        try:
            self._workspace_template = state
            self._active_shot_id = active_shot
            self._active_version_id = active_version
            self.region_controller.set_context(
                store,
                active_shot,
                active_version,
            )
            self._ab_role = (
                state.ab_role
                if state.ab_role in {"reference", "current"}
                else "reference"
            )
            self._set_combo_data(self.mode_combo, state.display_mode, "original")
            self._set_combo_data(
                self.comparison_combo,
                state.comparison_mode,
                "split",
            )
            self._set_combo_data(
                self.composition_guide_combo,
                state.composition_guide,
                "none",
            )
            self.blur_slider.setValue(
                max(0, min(200, int(round(state.blur_sigma * 10.0))))
            )
            self.silhouette_slider.setValue(
                max(
                    5,
                    min(
                        95,
                        int(round(state.silhouette_threshold * 100.0)),
                    ),
                )
            )
            self.sync_checkbox.setChecked(state.sync_views)
            self.comparison_panel.set_thresholds(
                state.three_threshold_low,
                state.three_threshold_high,
            )
            tab_names = (
                "reference",
                "current",
                "comparison",
                "tasks",
                "optimization",
            )
            self.analysis_tabs.setCurrentIndex(
                (
                    tab_names.index(state.active_analysis_tab)
                    if state.active_analysis_tab in tab_names
                    else 0
                )
            )
            self._comparison_mode_changed(self.comparison_combo.currentIndex())
            self._clear_role("reference")
            self._clear_role("current")
            self._refresh_project_navigator()
            self._load_active_project_images()
            self._refresh_workbench_tasks()
            self._refresh_ai_review_history()
        finally:
            self._restoring_workspace = False
            self._workspace_dirty = False
            self._autosave_timer.stop()

    def _remember_project(self, store: ProjectStore) -> None:
        try:
            self._recent_projects.add(
                store.manifest.project_id,
                store.manifest.name,
                store.manifest_path,
                utc_now(),
            )
        except OSError:
            LOGGER.exception("Failed to update recent projects")
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        entries = self._recent_projects.load()
        if not entries:
            action = self._recent_menu.addAction("暂无最近项目")
            action.setEnabled(False)
            return
        for entry in entries:
            suffix = "" if entry.is_available else "（路径不可用）"
            action = self._recent_menu.addAction(f"{entry.name}{suffix}")
            action.setToolTip(str(entry.manifest_path))
            action.setEnabled(entry.is_available)
            action.triggered.connect(
                lambda _checked=False, path=entry.manifest_path: self.open_project(
                    path
                )
            )

    def _save_project_action(self) -> None:
        if self._project_store is None:
            return
        if not self._flush_autosave(show_error=True):
            return
        try:
            self._project_store.save()
            self.statusBar().showMessage("项目已保存")
        except StorageError as exc:
            self._show_storage_error("项目保存失败", exc)

    def _new_shot_dialog(self) -> None:
        if self._project_store is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            "新建 Shot",
            "Shot 名称：",
        )
        if accepted and name.strip():
            self.create_shot(name)

    def create_shot(self, name: str) -> bool:
        store = self._project_store
        if store is None:
            return False
        if not self._flush_autosave(show_error=True):
            return False
        try:
            shot = store.create_shot(name)
            self._active_shot_id = shot.id
            self._active_version_id = None
            self.region_controller.set_context(store, shot.id, None)
            self._clear_role("reference")
            self._clear_role("current")
            self._refresh_project_navigator()
            self._mark_workspace_dirty()
            self.statusBar().showMessage(f"已创建 Shot：{shot.name}")
            return True
        except StorageError as exc:
            self._show_storage_error("无法创建 Shot", exc)
            return False

    def _edit_art_brief(self) -> None:
        store = self._project_store
        if store is None:
            return
        choices = ["项目级制作意图"]
        if self._active_shot_id is not None:
            choices.append("当前 Shot 覆盖")
        selection = choices[0]
        if len(choices) > 1:
            selection, accepted = QInputDialog.getItem(
                self,
                "选择制作意图范围",
                "编辑范围：",
                choices,
                0,
                False,
            )
            if not accepted:
                return
        shot_id = (
            self._active_shot_id
            if selection == "当前 Shot 覆盖"
            else None
        )
        document = store.get_creative_intent_document(shot_id)
        if document is None and not store.read_only:
            document = store.ensure_creative_intent_document(shot_id)
        if document is None:
            QMessageBox.information(
                self,
                "暂无制作意图",
                "当前只读项目中没有该范围的制作意图。",
            )
            return
        fields = store.list_brief_fields(document.id)
        dialog = BriefEditorDialog(
            (
                "制作意图 · 项目级"
                if shot_id is None
                else "制作意图 · 当前 Shot 覆盖"
            ),
            CREATIVE_INTENT_FIELDS,
            fields,
            self._presets,
            read_only=store.read_only,
            parent=self,
        )
        if (
            not store.read_only
            and dialog.exec() == QDialog.DialogCode.Accepted
        ):
            self._save_user_brief_values(
                document.id,
                dialog.values(),
                fields,
                "制作意图",
            )
        elif store.read_only:
            dialog.exec()

    def _edit_reference_visual_brief(self) -> None:
        store = self._project_store
        if store is None or self._active_shot_id is None:
            return
        document = store.get_reference_visual_brief(self._active_shot_id)
        if document is None:
            QMessageBox.information(
                self,
                "暂无参考图视觉简报",
                "请先为当前 Shot 导入参考图。",
            )
            return
        fields = store.list_brief_fields(document.id)
        dialog = ReferenceVisualBriefDialog(
            fields,
            self._presets,
            read_only=store.read_only,
            parent=self,
        )
        if (
            not store.read_only
            and dialog.exec() == QDialog.DialogCode.Accepted
        ):
            self._save_user_brief_values(
                document.id,
                dialog.values(),
                fields,
                "参考图视觉简报",
            )
        elif store.read_only:
            dialog.exec()

    def _save_user_brief_values(
        self,
        document_id: str,
        values: dict,
        existing: dict[str, BriefFieldValue],
        label: str,
    ) -> bool:
        store = self._project_store
        if store is None:
            return False
        fields = {
            key: BriefFieldValue(
                value=value,
                source=(
                    FieldSource.USER_REVISION
                    if key in existing
                    else FieldSource.USER_INPUT
                ),
                evidence={"edited_in": "scenelens"},
                user_confirmed=True,
            )
            for key, value in values.items()
        }
        try:
            store.save_brief_fields(document_id, fields)
            self.statusBar().showMessage(f"{label}已保存")
            return True
        except StorageError as exc:
            self._show_storage_error(f"{label}保存失败", exc)
            return False

    def save_art_brief(self, brief: ArtBrief) -> bool:
        store = self._project_store
        if store is None:
            return False
        try:
            store.save_art_brief(brief)
            self.statusBar().showMessage("制作意图已保存")
            return True
        except StorageError as exc:
            self._show_storage_error("制作意图保存失败", exc)
            return False

    def _activate_shot(self, shot_id: str) -> None:
        store = self._project_store
        if store is None or shot_id == self._active_shot_id:
            return
        if not self._flush_autosave(show_error=True):
            self._refresh_project_navigator()
            return
        versions = store.list_versions(shot_id)
        self._active_shot_id = shot_id
        self._active_version_id = versions[-1].id if versions else None
        self.region_controller.set_context(
            store,
            self._active_shot_id,
            self._active_version_id,
        )
        self._clear_role("reference")
        self._clear_role("current")
        self._refresh_project_navigator()
        self._load_active_project_images()
        self._refresh_ai_review_history()
        self._mark_workspace_dirty()

    def _activate_version(self, shot_id: str, version_id: str) -> None:
        if (
            self._project_store is None
            or (
                shot_id == self._active_shot_id
                and version_id == self._active_version_id
            )
        ):
            return
        if not self._flush_autosave(show_error=True):
            self._refresh_project_navigator()
            return
        self._active_shot_id = shot_id
        self._active_version_id = version_id
        self.region_controller.set_context(
            self._project_store,
            shot_id,
            version_id,
        )
        self._clear_role("reference")
        self._clear_role("current")
        self._refresh_project_navigator()
        self._load_active_project_images()
        self._refresh_ai_review_history()
        self._mark_workspace_dirty()

    def _refresh_project_navigator(self) -> None:
        if self._project_store is None:
            self.project_navigator.clear_project()
            return
        self.project_navigator.refresh(
            self._project_store,
            self._active_shot_id,
            self._active_version_id,
        )

    def _load_active_project_images(self) -> None:
        store = self._project_store
        if store is None or self._active_shot_id is None:
            return
        try:
            shot = store.get_shot(self._active_shot_id)
            if shot.reference_asset_id is not None:
                state = store.get_canvas_state(
                    "reference",
                    shot.id,
                    None,
                )
                self._load_project_asset(
                    "reference",
                    shot.reference_asset_id,
                    state,
                )
            if self._active_version_id is not None:
                version = store.get_version(self._active_version_id)
                state = store.get_canvas_state(
                    "current",
                    shot.id,
                    version.id,
                )
                self._load_project_asset("current", version.asset_id, state)
        except StorageError as exc:
            self._show_storage_error("项目图片恢复失败", exc)

    def _load_project_asset(
        self,
        role: str,
        asset_id: str,
        canvas_state: CanvasState | None = None,
    ) -> None:
        store = self._project_store
        if store is None:
            return
        path = store.asset_path(asset_id)
        self._asset_ids[role] = asset_id
        self._load_path(
            role,
            str(path),
            asset_id=asset_id,
            reset_view=True,
            canvas_state=canvas_state,
        )

    def _choose_image(self, role: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"选择{ROLE_LABELS[role]}",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if path:
            self._import_or_load(role, path)

    def _import_or_load(self, role: str, path: str) -> None:
        if self._project_store is None:
            self._load_path(role, path)
            return
        if self._project_store.read_only:
            QMessageBox.information(
                self,
                "项目为只读",
                "该项目正由另一个进程写入；当前窗口不会导入或修改图片。",
            )
            return
        if self._active_shot_id is None:
            QMessageBox.information(
                self,
                "请先创建 Shot",
                "项目图片必须归属于一个 Shot。请先在左侧创建 Shot。",
            )
            return
        self._start_project_import(role, Path(path))

    def _start_project_import(self, role: str, path: Path) -> None:
        store = self._project_store
        shot_id = self._active_shot_id
        if store is None or shot_id is None:
            return
        self._import_generation[role] += 1
        generation = self._import_generation[role]
        self._import_context[role][generation] = (
            store.manifest.project_id,
            shot_id,
        )
        kind = "import_reference" if role == "reference" else "import_version"
        operation = (
            (lambda: store.import_reference(shot_id, path))
            if role == "reference"
            else (lambda: store.add_version(shot_id, path))
        )
        self.statusBar().showMessage(
            f"正在将{ROLE_LABELS[role]}复制到项目并校验原始字节…"
        )
        self._start_worker(role, kind, generation, operation)

    def _load_path(
        self,
        role: str,
        path: str,
        asset_id: str | None = None,
        reset_view: bool = True,
        canvas_state: CanvasState | None = None,
    ) -> None:
        self._load_generation[role] += 1
        generation = self._load_generation[role]
        self._load_context[role][generation] = (
            asset_id,
            reset_view,
            canvas_state,
        )
        if asset_id is None:
            self._asset_ids[role] = None
        self.statusBar().showMessage(f"正在读取{ROLE_LABELS[role]}：{Path(path).name}")
        self._start_worker(
            role,
            "load",
            generation,
            lambda: load_image(path),
        )

    def _on_worker_result(
        self,
        role: str,
        kind: str,
        generation: int,
        result: object,
    ) -> None:
        if kind == "m3_match":
            if generation != self._match_generation:
                return
            if isinstance(result, MatchProfile):
                self.optimization_panel.show_match_profile(result)
                self.statusBar().showMessage(
                    "目标匹配画像已更新；结果仅代表当前算法与权重"
                )
            return

        if kind == "m3_grade":
            if generation != self._grade_generation:
                return
            if (
                isinstance(result, tuple)
                and len(result) == 2
                and isinstance(result[0], SafeGradeRecipe)
                and isinstance(result[1], np.ndarray)
            ):
                recipe, preview = result
                self._safe_grade_recipe = recipe
                self._safe_grade_preview = preview
                image = self._images.get("current")
                if image is not None:
                    self.current_pane.canvas.set_image(
                        numpy_to_qimage(preview, image.alpha),
                        reset_view=False,
                    )
                self._optimization_preview_visible = True
                self.optimization_panel.show_grade_preview(recipe)
                self.statusBar().showMessage(
                    "安全调色预览已生成；原始截图未被修改"
                )
            return

        if kind == "m3_concept":
            if generation != self._concept_generation:
                return
            self._concept_cancellation = None
            if isinstance(result, ConceptPreviewOutcome):
                self._last_concept_preview = result.entity
                self._concept_preview_rgb = result.rgb
                self._last_preview_validation = result.validation
                image = self._images.get("current")
                if image is not None:
                    self.current_pane.canvas.set_image(
                        numpy_to_qimage(result.rgb, None),
                        reset_view=False,
                    )
                self._optimization_preview_visible = True
                self.optimization_panel.show_concept_validation(
                    result.validation,
                    provider_id=result.entity.provider_id,
                    model_id=result.entity.model_id,
                )
                self._finish_concept_ai_run(
                    status=AIRunStatus.COMPLETE,
                    output={
                        "preview_id": result.entity.id,
                        "relative_path": result.entity.relative_path,
                        "preview_status": (
                            result.entity.preview_status.value
                        ),
                        "validation": result.validation.to_dict(),
                    },
                )
                self.statusBar().showMessage(
                    "AIConceptPreview 已保存；真实 Version 未发生变化"
                )
            return

        if kind == "ai_review":
            if generation != self._ai_review_generation:
                return
            self._ai_cancellation = None
            if not isinstance(result, ReviewRunOutcome):
                return
            self._last_review_outcome = result
            self._persist_review_annotations(result)
            self.ai_review_panel.show_outcome(result)
            if self._active_ai_run is not None:
                manifest = dict(self._active_ai_run.input_manifest)
                manifest["requested_model_id"] = result.requested_model_id
                manifest["attempted_model_ids"] = list(
                    result.attempted_model_ids
                )
                manifest["model_fallback_used"] = (
                    result.model_fallback_used
                )
                manifest["model_fallback_reason"] = (
                    result.model_fallback_reason
                )
                self._active_ai_run = replace(
                    self._active_ai_run,
                    model_id=result.model_id,
                    input_manifest=manifest,
                )
            self._finish_ai_run(
                status=AIRunStatus.COMPLETE,
                output=review_outcome_to_payload(result),
            )
            self._refresh_ai_review_history()
            self._refresh_workbench_tasks()
            return

        if kind in {"import_reference", "import_version"}:
            if generation != self._import_generation[role]:
                return
            context = self._import_context[role].pop(generation, None)
            store = self._project_store
            if context is None or store is None:
                return
            project_id, shot_id = context
            if (
                project_id != store.manifest.project_id
                or shot_id != self._active_shot_id
            ):
                return
            if kind == "import_reference" and isinstance(
                result, ImageAssetRecord
            ):
                self._refresh_project_navigator()
                self._load_project_asset("reference", result.id)
                self.statusBar().showMessage("参考图已安全导入项目")
            elif kind == "import_version" and isinstance(result, VersionRecord):
                self._active_version_id = result.id
                self.region_controller.set_context(
                    store,
                    self._active_shot_id,
                    result.id,
                )
                self._refresh_project_navigator()
                self._load_project_asset("current", result.asset_id)
                self._mark_workspace_dirty()
                self.statusBar().showMessage(
                    f"已添加 V{result.ordinal}：{result.name}"
                )
            return

        if kind == "load":
            if generation != self._load_generation[role]:
                return
            loaded = result
            if not isinstance(loaded, LoadedImage):
                return
            asset_id, reset_view, canvas_state = self._load_context[role].pop(
                generation,
                (None, True, None),
            )
            self._images[role] = loaded
            self._measurements.pop(role, None)
            self._clear_palette_mask()
            self._asset_ids[role] = asset_id
            display_name: str | None = None
            if asset_id is not None and self._project_store is not None:
                try:
                    display_name = self._project_store.get_asset(
                        asset_id
                    ).original_filename
                except StorageError:
                    LOGGER.exception("Failed to read original asset name")
            self.analysis_widgets[role].set_loaded_image(
                loaded,
                display_name=display_name,
            )
            self._canvas_for(role).set_image(
                numpy_to_qimage(loaded.rgb, loaded.alpha),
                reset_view=reset_view,
            )
            self.region_controller.refresh()
            if canvas_state is not None:
                self._canvas_for(role).apply_external_view_state(
                    canvas_state.zoom_factor,
                    canvas_state.center_x,
                    canvas_state.center_y,
                )
            cached = self._load_cached_measurements(asset_id)
            if cached is not None:
                self._measurements[role] = cached
                self.analysis_widgets[role].set_measurements(cached)
                if role == "reference":
                    self._start_reference_brief_fields(cached)
                self.statusBar().showMessage(
                    f"{ROLE_LABELS[role]}已恢复历史分析结果"
                )
            else:
                self._start_measurement(role)
            self._start_render(role)
            self._schedule_comparison_analysis()
            self.statusBar().showMessage(
                f"{ROLE_LABELS[role]}已导入：{loaded.working_size[0]} × "
                f"{loaded.working_size[1]}"
            )
            return

        if kind == "measure":
            if generation != self._measure_generation[role]:
                return
            measurements = result
            if isinstance(measurements, ImageMeasurements):
                self._measurements[role] = measurements
                self.analysis_widgets[role].set_measurements(measurements)
                context = self._measure_context[role].pop(
                    generation,
                    (None, {}),
                )
                asset_id, parameters = context
                if asset_id is not None and self._project_store is not None:
                    try:
                        self._project_store.save_measurements(
                            asset_id,
                            measurements,
                            parameters,
                        )
                    except (StorageError, OSError, ValueError):
                        LOGGER.exception("Failed to persist image measurements")
                        self.statusBar().showMessage(
                            f"{ROLE_LABELS[role]}分析完成，但结果保存失败"
                        )
                        return
                if role == "reference":
                    self._start_reference_brief_fields(measurements)
                self._schedule_comparison_analysis()
                self.statusBar().showMessage(f"{ROLE_LABELS[role]}分析完成")
            return

        if kind == "reference_brief":
            if generation != self._brief_generation:
                return
            self._persist_reference_brief_fields(result)
            return

        if kind == "comparison":
            if generation != self._comparison_generation:
                return
            self._apply_comparison_result(result)
            return

        if kind == "region_analysis":
            if generation != self._region_analysis_generation:
                return
            self._apply_region_analysis_result(result)
            return

        if kind == "mask":
            if generation != self._mask_generation:
                return
            self._apply_mask_result(result)
            return

        if kind == "render":
            if generation != self._render_generation[role]:
                return
            loaded = self._images.get(role)
            if loaded is None:
                return
            self._canvas_for(role).set_image(
                numpy_to_qimage(result, loaded.alpha),
                reset_view=False,
            )

    def _on_worker_error(
        self,
        role: str,
        kind: str,
        generation: int,
        message: str,
        details: str,
    ) -> None:
        if kind == "m3_match":
            expected = self._match_generation
        elif kind == "m3_grade":
            expected = self._grade_generation
        elif kind == "m3_concept":
            expected = self._concept_generation
        elif kind == "ai_review":
            expected = self._ai_review_generation
        elif kind in {"import_reference", "import_version"}:
            expected = self._import_generation[role]
        elif kind == "reference_brief":
            expected = self._brief_generation
        elif kind == "comparison":
            expected = self._comparison_generation
        elif kind == "region_analysis":
            expected = self._region_analysis_generation
        elif kind == "mask":
            expected = self._mask_generation
        else:
            expected = {
                "load": self._load_generation,
                "measure": self._measure_generation,
                "render": self._render_generation,
            }[kind][role]
        if generation != expected:
            return
        if kind == "m3_concept":
            self._concept_cancellation = None
            self.optimization_panel.show_concept_error(message)
            status = (
                AIRunStatus.CANCELLED
                if "取消" in message or "cancel" in message.lower()
                else AIRunStatus.FAILED
            )
            self._finish_concept_ai_run(
                status=status,
                error_code=(
                    "cancelled"
                    if status == AIRunStatus.CANCELLED
                    else "provider_error"
                ),
                error_message=message,
            )
        elif kind == "ai_review":
            self._ai_cancellation = None
            self.ai_review_panel.show_error(message)
            status = (
                AIRunStatus.CANCELLED
                if "取消" in message or "cancel" in message.lower()
                else AIRunStatus.FAILED
            )
            self._finish_ai_run(
                status=status,
                error_code=(
                    "cancelled"
                    if status == AIRunStatus.CANCELLED
                    else "provider_error"
                ),
                error_message=message,
            )
        LOGGER.error("%s %s failed:\n%s", role, kind, details)
        title = {
            "load": "图片读取失败",
            "measure": "图片分析失败",
            "render": "显示处理失败",
            "import_reference": "参考图导入失败",
            "import_version": "截图版本导入失败",
            "reference_brief": "参考图自动测量关联失败",
            "comparison": "对比分析失败",
            "region_analysis": "成对区域分析失败",
            "mask": "颜色来源遮罩失败",
            "ai_review": "AI 专项审阅失败",
            "m3_match": "目标匹配画像失败",
            "m3_grade": "安全调色预览失败",
            "m3_concept": "AI 优化预演失败",
        }.get(kind, "GATalk 操作失败")
        QMessageBox.warning(
            self,
            title,
            (
                f"{ROLE_LABELS[role]}处理失败：\n{message}"
                if role in ROLE_LABELS
                else f"处理失败：\n{message}"
            ),
        )
        self.statusBar().showMessage(
            (
                f"{ROLE_LABELS[role]}处理失败"
                if role in ROLE_LABELS
                else "处理失败"
            )
        )

    def _on_worker_finished(self, _role: str, _kind: str, _generation: int) -> None:
        self._active_jobs = max(0, self._active_jobs - 1)
        self.progress.setVisible(self._active_jobs > 0)

    def _start_worker(
        self,
        role: str,
        kind: str,
        generation: int,
        function,
    ) -> None:
        worker = FunctionWorker(role, kind, generation, function)
        worker.signals.result.connect(self._on_worker_result)
        worker.signals.error.connect(self._on_worker_error)
        worker.signals.finished.connect(self._on_worker_finished)
        self._active_jobs += 1
        self.progress.setVisible(True)
        self._thread_pool.start(worker)

    def _start_match_profile(self, raw_weights: object) -> None:
        if not {"reference", "current"}.issubset(self._images):
            QMessageBox.information(
                self,
                "目标匹配画像",
                "请先加载参考图和当前截图。",
            )
            return
        weights = (
            dict(raw_weights)
            if isinstance(raw_weights, dict)
            else self.optimization_panel.match_weights()
        )
        paired_values: list[PairedRegionAnalysis] = []
        region_store = self.region_controller.store
        if region_store is not None:
            for view in self.region_controller.pair_views():
                try:
                    record = region_store.latest_analysis(view.pair.id)
                    if record is not None:
                        paired_values.append(
                            paired_region_from_payload(record.result)
                        )
                except (StorageError, KeyError, TypeError, ValueError):
                    LOGGER.exception(
                        "Failed to read paired analysis for match profile"
                    )
        if (
            not paired_values
            and self._active_region_analysis is not None
        ):
            paired_values.append(self._active_region_analysis[1])
        paired = tuple(paired_values)
        reference = self._images["reference"].rgb
        current = self._images["current"].rgb
        shared = self._shared_palette_result
        self._match_generation += 1
        generation = self._match_generation
        self._start_worker(
            "m3",
            "m3_match",
            generation,
            lambda: build_match_profile(
                reference,
                current,
                shared_palette=shared,
                paired_regions=paired,
                weights=weights,
            ),
        )

    def _start_safe_grade_preview(self, raw_options: object) -> None:
        current = self._images.get("current")
        if current is None:
            QMessageBox.information(
                self,
                "安全调色",
                "请先加载当前截图。",
            )
            return
        options = raw_options if isinstance(raw_options, dict) else {}
        recipe = options.get("recipe")
        if not isinstance(recipe, SafeGradeRecipe):
            scope = str(options.get("scope", "full"))
            rect = None
            if scope == "selected_region":
                rect = self.region_controller.selected_current_rect()
                if rect is None:
                    QMessageBox.information(
                        self,
                        "区域安全调色",
                        "请先在成对区域列表中选择一个完整区域对。",
                    )
                    return
            recipe = self.optimization_panel.current_recipe(rect)
        reference = self._images.get("reference")
        reference_rgb = (
            None if reference is None else reference.rgb
        )
        if (
            recipe.reference_colour_transfer > 0.0
            and reference_rgb is None
        ):
            QMessageBox.information(
                self,
                "参考色迁移",
                "启用参考色迁移前需要加载参考图。",
            )
            return
        self._grade_generation += 1
        generation = self._grade_generation
        self._start_worker(
            "m3",
            "m3_grade",
            generation,
            lambda: (
                recipe,
                apply_safe_grade(
                    current.rgb,
                    recipe,
                    reference_rgb=reference_rgb,
                ),
            ),
        )

    def _show_safe_grade_original(self, show_original: bool) -> None:
        image = self._images.get("current")
        if image is None:
            return
        rgb = (
            image.rgb
            if show_original or self._safe_grade_preview is None
            else self._safe_grade_preview
        )
        self.current_pane.canvas.set_image(
            numpy_to_qimage(rgb, image.alpha),
            reset_view=False,
        )
        self._optimization_preview_visible = not show_original
        self.statusBar().showMessage(
            "正在显示原始截图"
            if show_original
            else "正在显示安全调色预览"
        )

    def _export_safe_grade(self, export_kind: str) -> None:
        if (
            self._safe_grade_preview is None
            or self._safe_grade_recipe is None
        ):
            QMessageBox.information(
                self,
                "导出安全调色",
                "请先生成安全调色预览。",
            )
            return
        base = (
            self._project_store.root / "exports"
            if self._project_store is not None
            else Path.cwd()
        )
        filters = {
            "png": ("导出预览 PNG", "PNG 图片 (*.png)", ".png"),
            "json": ("导出调色配方", "JSON 文件 (*.json)", ".json"),
            "cube": ("导出 3D LUT", "Cube LUT (*.cube)", ".cube"),
        }
        title, file_filter, suffix = filters[export_kind]
        selected, _ = QFileDialog.getSaveFileName(
            self,
            title,
            str(base / f"scenelens_safe_grade{suffix}"),
            file_filter,
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() != suffix:
            path = path.with_suffix(suffix)
        try:
            if export_kind == "png":
                write_grade_png(path, self._safe_grade_preview)
            elif export_kind == "json":
                write_grade_recipe(path, self._safe_grade_recipe)
            else:
                write_cube_lut(path, self._safe_grade_recipe)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.statusBar().showMessage(f"已导出：{path.name}")

    def _start_concept_preview(self, raw_options: object) -> None:
        if not isinstance(raw_options, ConceptPreviewOptions):
            return
        store = self._project_store
        if (
            store is None
            or store.read_only
            or self._active_shot_id is None
            or self._active_version_id is None
        ):
            QMessageBox.information(
                self,
                "AI 优化预演",
                "请先以可写方式打开项目，并选择一个真实 Version。",
            )
            return
        if not {"reference", "current"}.issubset(self._images):
            QMessageBox.information(
                self,
                "AI 优化预演",
                "预演需要参考图和当前截图。",
            )
            return
        try:
            manifest = self._provider_registry.manifest(
                raw_options.provider_id
            )
            provider = self._provider_registry.get(
                raw_options.provider_id
            )
            context = self._build_review_context()
            workbench = WorkbenchStore(store)
            tasks = workbench.list_tasks(
                MODULE_ID,
                shot_id=self._active_shot_id,
                version_id=self._active_version_id,
            )
            confirmed_tasks = tuple(
                {
                    "task_id": item.id,
                    "title": item.title,
                    "description": item.description,
                    "priority": item.priority.value,
                    "status": item.status.value,
                    "verification": dict(item.verification),
                }
                for item in tasks
            )
            pair_views = self.region_controller.pair_views()
            paired_regions = tuple(
                {
                    "pair_id": view.pair.id,
                    "name": view.pair.name,
                    "semantic_type": view.pair.semantic_type,
                    "reference_rect": (
                        view.reference_region.normalized_rect.to_dict()
                    ),
                    "current_rect": (
                        view.current_region.normalized_rect.to_dict()
                    ),
                }
                for view in pair_views
            )
            preserve_ids = tuple(
                view.current_region.id for view in pair_views
            )
            protection = PreviewProtectionControls(
                preserve_composition=raw_options.preserve_composition,
                preserve_geometry=raw_options.preserve_geometry,
                preserve_asset_identity=(
                    raw_options.preserve_asset_identity
                ),
                preserve_regions=preserve_ids,
            )
            instruction = build_structured_preview_instruction(
                mode=raw_options.mode,
                change_budget_percent=(
                    raw_options.change_budget_percent
                ),
                creative_intent=context.creative_intent,
                reference_visual_brief=(
                    context.reference_visual_brief
                ),
                confirmed_tasks=confirmed_tasks,
                paired_regions=paired_regions,
                protection=protection,
            )
            export_options = ProviderImageExportOptions(
                remove_metadata=raw_options.remove_metadata,
                maximum_side=raw_options.maximum_side,
            )
            images = tuple(
                prepare_provider_image(
                    self._images[role],
                    role,
                    export_options,
                )
                for role in ("reference", "current")
            )
            request = ImageEditRequest(
                instruction=instruction,
                images=images,
                model_id=raw_options.model_id,
                change_budget=raw_options.change_budget_percent,
            )
            preview = disclosure_preview(manifest, request)
        except (KeyError, OSError, StorageError, ValueError) as exc:
            QMessageBox.warning(self, "无法准备 AI 预演", str(exc))
            return
        dialog = DataDisclosureDialog(
            preview,
            second_opinion=False,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("AI 优化预演已取消，未发送数据")
            return

        credential = ""
        if raw_options.provider_id != "mock":
            try:
                credential = (
                    self._credential_store.get(
                        manifest.credential_target
                    )
                    or ""
                )
            except OSError as exc:
                QMessageBox.warning(self, "读取系统凭据失败", str(exc))
                return
            if not credential:
                QMessageBox.information(
                    self,
                    "缺少 API Key",
                    "请先把所选供应商的 API Key 存入 Windows 系统凭据。",
                )
                return

        approved = replace(
            request,
            user_initiated=True,
            disclosure_confirmed=True,
        )
        self._concept_generation += 1
        generation = self._concept_generation
        cancellation = CancellationToken()
        self._concept_cancellation = cancellation
        model_id = manifest.model_for(
            ProviderCapability.IMAGE_EDIT,
            raw_options.model_id,
        )
        request_hash = hashlib.sha256(
            (
                canonical_json(dict(instruction))
                + "|"
                + "|".join(item.sha256 for item in images)
            ).encode("utf-8")
        ).hexdigest()
        self._active_concept_run = AIRun(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            reviewer_id="ai_concept_preview",
            provider_id=raw_options.provider_id,
            model_id=model_id,
            capability=ProviderCapability.IMAGE_EDIT.value,
            request_hash=request_hash,
            input_manifest={
                "image_hashes": {
                    item.role: item.sha256 for item in images
                },
                "change_budget": raw_options.change_budget_percent,
                "edit_mode": raw_options.mode.value,
                "remove_metadata": raw_options.remove_metadata,
                "maximum_side": raw_options.maximum_side,
            },
            status=AIRunStatus.RUNNING,
            created_at=utc_now(),
        )
        self._persist_ai_run(self._active_concept_run)
        self.optimization_panel.show_concept_running(True)
        self.statusBar().showMessage("AI 优化预演已在后台启动")
        project_root = store.root
        shot_id = self._active_shot_id
        version_id = self._active_version_id
        protected_rects = tuple(
            (
                view.current_region.normalized_rect.x,
                view.current_region.normalized_rect.y,
                view.current_region.normalized_rect.width,
                view.current_region.normalized_rect.height,
            )
            for view in pair_views
        )
        current_rgb = self._images["current"].rgb
        reference_rgb = self._images["reference"].rgb
        input_hashes = {
            item.role: item.sha256 for item in images
        }

        def run_preview() -> ConceptPreviewOutcome:
            response = self._review_coordinator.execution.run_image_edit(
                provider,
                approved,
                credential,
                cancellation,
            )
            if not isinstance(response, ImageEditResponse):
                raise ValueError("图像供应商返回了不支持的响应类型。")
            try:
                with Image.open(BytesIO(response.image_bytes)) as opened:
                    preview_rgb = np.asarray(
                        opened.convert("RGB"),
                        dtype=np.uint8,
                    )
            except (OSError, ValueError) as exc:
                raise ValueError("供应商返回的图片无法解码。") from exc
            preview_rgb = np.ascontiguousarray(preview_rgb)
            validation = validate_concept_preview(
                current_rgb,
                preview_rgb,
                reference_rgb,
                stable_regions=protected_rects,
                protected_regions=protected_rects,
            )
            preview_id = str(uuid.uuid4())
            relative = (
                f"artifacts/ai_previews/{preview_id}.png"
            )
            write_grade_png(project_root / relative, preview_rgb)
            entity = AIConceptPreview(
                id=preview_id,
                module_id=MODULE_ID,
                shot_id=shot_id,
                source_version_id=version_id,
                provider_id=response.provider_id,
                model_id=response.model_id,
                relative_path=relative,
                input_hashes=input_hashes,
                instruction=instruction,
                protection_constraints={
                    "preserve_composition": (
                        protection.preserve_composition
                    ),
                    "preserve_geometry": protection.preserve_geometry,
                    "preserve_asset_identity": (
                        protection.preserve_asset_identity
                    ),
                    "preserve_regions": list(
                        protection.preserve_regions
                    ),
                },
                validation_metrics=validation.to_dict(),
                preview_status=validation.status,
                created_at=utc_now(),
            )
            WorkbenchStore(store).save_ai_concept_preview(entity)
            return ConceptPreviewOutcome(
                entity,
                preview_rgb,
                validation,
            )

        self._start_worker(
            "m3",
            "m3_concept",
            generation,
            run_preview,
        )

    def _cancel_concept_preview(self) -> None:
        if self._concept_cancellation is not None:
            self._concept_cancellation.cancel()
            self.optimization_panel.concept_status.setText(
                "正在取消 AI 优化预演…"
            )

    def _finish_concept_ai_run(
        self,
        *,
        status: AIRunStatus,
        output: dict | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        run = self._active_concept_run
        if run is None:
            return
        finished = replace(
            run,
            status=status,
            output=output,
            error_code=error_code,
            error_message=(
                None
                if error_message is None
                else str(error_message)[:2000]
            ),
            completed_at=utc_now(),
        )
        self._persist_ai_run(finished)
        self._active_concept_run = None

    def _confirm_concept_preview_tasks(self) -> None:
        store = self._project_store
        preview = self._last_concept_preview
        validation = self._last_preview_validation
        if (
            store is None
            or store.read_only
            or preview is None
            or validation is None
        ):
            QMessageBox.information(
                self,
                "预演任务",
                "当前没有可转换的已保存 AIConceptPreview。",
            )
            return
        if (
            QMessageBox.question(
                self,
                "确认预演任务",
                "将当前预演的结构化改动方向确认为一个修改任务？\n"
                "预演图片只作为概念证据，不会替代真实 UE Version。",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        mode = str(preview.instruction.get("edit_mode", ""))
        title = {
            "lighting_only": "根据 AI 预演调整灯光",
            "colour_only": "根据 AI 预演调整调色",
            "fog_atmosphere_only": "根据 AI 预演调整雾与氛围",
        }.get(mode, "根据 AIConceptPreview 调整场景")
        now = utc_now()
        evidence = Evidence(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            shot_id=preview.shot_id,
            version_id=preview.source_version_id,
            evidence_type=EvidenceType.ALGORITHM_INFERENCE,
            source=EvidenceSource.AI_PROVIDER,
            subject_type="ai_concept_preview",
            subject_id=preview.id,
            payload={
                "relative_path": preview.relative_path,
                "provider_id": preview.provider_id,
                "model_id": preview.model_id,
                "preview_status": preview.preview_status.value,
                "validation": validation.to_dict(),
                "user_confirmed": True,
            },
            created_at=now,
        )
        task = Task(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            shot_id=preview.shot_id,
            version_id=preview.source_version_id,
            source_evidence_id=evidence.id,
            title=title,
            description=(
                str(
                    preview.instruction.get(
                        "change_budget",
                        {},
                    ).get("semantics", "")
                )
                + "\n预演边界："
                + (
                    "仅适合概念参考"
                    if preview.preview_status.value == "concept_only"
                    else "候选预演，仍需在 UE 中实施并导入新截图复查"
                )
            ),
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.OPEN,
            verification={
                "ai_concept_preview_id": preview.id,
                "requires_real_ue_version": True,
                "validation_metrics": validation.to_dict(),
            },
            created_at=now,
            updated_at=now,
        )
        try:
            workbench = WorkbenchStore(store)
            workbench.save_evidence(evidence)
            workbench.save_task(task)
        except (StorageError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存预演任务失败", str(exc))
            return
        self._refresh_workbench_tasks()
        self._emit_review_center_task(task)
        self.statusBar().showMessage(
            "AI 预演已转为任务；真实 Version 仍保持不变"
        )

    def _start_ai_review(self, raw_options: object) -> None:
        if not isinstance(raw_options, ReviewPanelOptions):
            return
        store = self._project_store
        if (
            store is None
            or self._active_shot_id is None
            or self._active_version_id is None
        ):
            QMessageBox.information(
                self,
                "AI 专项审阅",
                "请先打开项目，并选择包含参考图和当前 Version 的 Shot。",
            )
            return
        if not {"reference", "current"}.issubset(self._images):
            QMessageBox.information(
                self,
                "AI 专项审阅",
                "专项审阅需要参考图和当前截图。",
            )
            return
        run_options = raw_options.run
        if (
            run_options.second_opinion_provider_id
            == run_options.provider_id
        ):
            QMessageBox.information(
                self,
                "第二意见",
                "第二意见需要选择不同于主模型的供应商。",
            )
            return
        try:
            provider_images = self._prepare_review_images(raw_options)
            context = self._build_review_context()
            reviewer = self._reviewers[run_options.reviewer_id]
            preview_request = reviewer.create_request(
                context,
                provider_images,
                model_id=run_options.model_id,
            )
            manifest = self._provider_registry.manifest(
                run_options.provider_id
            )
            preview = disclosure_preview(manifest, preview_request)
        except (OSError, ValueError, StorageError) as exc:
            QMessageBox.warning(self, "准备审阅失败", str(exc))
            return
        dialog = DataDisclosureDialog(
            preview,
            second_opinion=bool(
                run_options.second_opinion_provider_id
            ),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("已取消 AI 发送")
            return

        credentials: dict[str, str] = {}
        provider_ids = [run_options.provider_id]
        if run_options.second_opinion_provider_id:
            provider_ids.append(run_options.second_opinion_provider_id)
        for provider_id in provider_ids:
            if provider_id == "mock":
                credentials[provider_id] = ""
                continue
            provider_manifest = self._provider_registry.manifest(provider_id)
            try:
                credential = self._credential_store.get(
                    provider_manifest.credential_target
                )
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "读取系统凭据失败",
                    f"{provider_manifest.display_name}：{exc}",
                )
                return
            if not credential:
                QMessageBox.information(
                    self,
                    "缺少 API Key",
                    f"请先为 {provider_manifest.display_name} 保存 API Key。",
                )
                return
            credentials[provider_id] = credential

        self._ai_review_generation += 1
        generation = self._ai_review_generation
        cancellation = CancellationToken()
        self._ai_cancellation = cancellation
        request_hash = hashlib.sha256(
            canonical_json(
                {
                    "reviewer_id": run_options.reviewer_id,
                    "provider_id": run_options.provider_id,
                    "model_id": preview.model_id,
                    "context": context.to_payload(),
                    "images": [
                        {
                            "role": image.role,
                            "sha256": image.sha256,
                            "media_type": image.media_type,
                        }
                        for image in provider_images
                    ],
                }
            ).encode("utf-8")
        ).hexdigest()
        self._active_ai_run = AIRun(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            reviewer_id=run_options.reviewer_id,
            provider_id=run_options.provider_id,
            model_id=preview.model_id,
            capability=ProviderCapability.VISION_REVIEW.value,
            request_hash=request_hash,
            input_manifest={
                "project_id": store.manifest.project_id,
                "shot_id": self._active_shot_id,
                "version_id": self._active_version_id,
                "payload_fields": list(preview.payload_fields),
                "images": [
                    {
                        "role": image.role,
                        "sha256": image.sha256,
                        "media_type": image.media_type,
                        "byte_size": len(image.data),
                    }
                    for image in provider_images
                ],
                "privacy": {
                    "remove_metadata": raw_options.remove_metadata,
                    "maximum_side": raw_options.maximum_side,
                },
                "second_opinion_provider_id": (
                    run_options.second_opinion_provider_id
                ),
            },
            status=AIRunStatus.RUNNING,
            created_at=utc_now(),
        )
        self._persist_ai_run(self._active_ai_run)
        self.ai_review_panel.set_running(True)
        self.statusBar().showMessage("AI 专项审阅已在后台启动")
        self._start_worker(
            "ai",
            "ai_review",
            generation,
            lambda: self._review_coordinator.run(
                options=run_options,
                context=context,
                images=provider_images,
                current_rgb=self._images["current"].rgb,
                reference_rgb=self._images["reference"].rgb,
                credentials=credentials,
                cancellation=cancellation,
            ),
        )

    def _prepare_review_images(
        self,
        options: ReviewPanelOptions,
    ):
        export_options = ProviderImageExportOptions(
            remove_metadata=options.remove_metadata,
            maximum_side=options.maximum_side,
        )
        return tuple(
            prepare_provider_image(
                self._images[role],
                role,
                export_options,
            )
            for role in ("reference", "current")
        )

    def _build_review_context(self) -> ReviewContext:
        store = self._project_store
        if (
            store is None
            or self._active_shot_id is None
            or self._active_version_id is None
        ):
            raise ValueError("当前没有可审阅的项目上下文。")

        creative: dict[str, object] = {}
        for shot_id in (None, self._active_shot_id):
            document = store.get_creative_intent_document(shot_id)
            if document is not None:
                creative.update(
                    self._brief_fields_payload(
                        store.list_brief_fields(document.id)
                    )
                )
        reference_brief: dict[str, object] = {}
        reference_document = store.get_reference_visual_brief(
            self._active_shot_id
        )
        if reference_document is not None:
            reference_brief = self._brief_fields_payload(
                store.list_brief_fields(reference_document.id)
            )

        measurements: dict[str, object] = {
            "three_value_thresholds": (
                list(self.comparison_panel.thresholds())
            ),
        }
        for role in ("reference", "current"):
            value = self._measurements.get(role)
            if value is None:
                continue
            measurements[role] = {
                "palette": [
                    {
                        "hex": colour.hex_colour,
                        "oklab": list(colour.oklab),
                        "proportion": colour.proportion,
                    }
                    for colour in value.palette
                ],
                "luminance_histogram": (
                    value.luminance_histogram.tolist()
                ),
                "sampled_pixel_count": value.sampled_pixel_count,
            }
        if self._shared_palette_result is not None:
            measurements["shared_palette"] = [
                {
                    "hex": colour.hex_colour,
                    "oklab": list(colour.oklab),
                    "reference_proportion": colour.reference_proportion,
                    "current_proportion": colour.current_proportion,
                }
                for colour in self._shared_palette_result.colours
            ]
        paired_values: list[dict[str, object]] = []
        region_store = self.region_controller.store
        if region_store is not None:
            for view in self.region_controller.pair_views():
                record = region_store.latest_analysis(view.pair.id)
                item: dict[str, object] = {
                    "pair_id": view.pair.id,
                    "name": view.pair.name,
                    "semantic_type": view.pair.semantic_type,
                    "notes": view.pair.notes,
                    "reference_region": {
                        "region_id": view.reference_region.id,
                        "name": view.reference_region.name,
                        "semantic_type": (
                            view.reference_region.semantic_type
                        ),
                        "normalized_rect": (
                            view.reference_region.normalized_rect.to_dict()
                        ),
                    },
                    "current_region": {
                        "region_id": view.current_region.id,
                        "name": view.current_region.name,
                        "semantic_type": view.current_region.semantic_type,
                        "normalized_rect": (
                            view.current_region.normalized_rect.to_dict()
                        ),
                    },
                    "analysis_status": view.analysis_status,
                }
                if record is not None:
                    item["analysis_status"] = record.status
                    item["analysis"] = dict(record.result)
                    item["analyzer"] = {
                        "analyzer_id": record.analyzer_id,
                        "analyzer_version": record.analyzer_version,
                        "parameters": dict(record.parameters),
                    }
                paired_values.append(item)
        paired = tuple(paired_values)
        low_threshold, high_threshold = self.comparison_panel.thresholds()
        evidence_digest = build_review_evidence_digest(
            self._images["reference"].rgb,
            self._images["current"].rgb,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            measurements=self._measurements,
        )
        history = tuple(
            {
                "version_id": version.id,
                "ordinal": version.ordinal,
                "name": version.name,
                "created_at": version.created_at,
            }
            for version in store.list_versions(self._active_shot_id)
        )
        locked = tuple(
            str(creative[key]["value"])
            for key in (
                "primary_focus",
                "secondary_focus",
                "preserve_content",
            )
            if isinstance(creative.get(key), dict)
            and creative[key].get("value")
        )
        constraints = creative.get("constraints", {})
        return ReviewContext(
            project_id=store.manifest.project_id,
            shot_id=self._active_shot_id,
            version_id=self._active_version_id,
            creative_intent=creative,
            reference_visual_brief=reference_brief,
            global_measurements=measurements,
            local_evidence_digest=evidence_digest,
            paired_region_measurements=paired,
            version_history=history,
            locked_goals=locked,
            production_context={
                "constraints": (
                    constraints.get("value")
                    if isinstance(constraints, dict)
                    else constraints
                )
            },
        )

    @staticmethod
    def _brief_fields_payload(fields: dict[str, BriefFieldValue]) -> dict:
        return {
            key: {
                "value": field.value,
                "source": field.source.value,
                "confidence": field.confidence,
                "evidence": field.evidence,
                "user_confirmed": field.user_confirmed,
                "updated_at": field.updated_at,
            }
            for key, field in fields.items()
        }

    def _cancel_ai_review(self) -> None:
        if self._ai_cancellation is not None:
            self._ai_cancellation.cancel()
            self.ai_review_panel.status_label.setText("正在取消 AI 审阅…")

    def _save_provider_credential(
        self,
        provider_id: str,
        secret: str,
    ) -> None:
        try:
            manifest = self._provider_registry.manifest(provider_id)
            self._credential_store.set(
                manifest.credential_target,
                secret,
            )
            self.statusBar().showMessage(
                f"{manifest.display_name} API Key 已存入 Windows 系统凭据"
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存系统凭据失败", str(exc))

    def _delete_provider_credential(self, provider_id: str) -> None:
        try:
            manifest = self._provider_registry.manifest(provider_id)
            self._credential_store.delete(manifest.credential_target)
            self.statusBar().showMessage(
                f"{manifest.display_name} API Key 已从系统凭据删除"
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "删除系统凭据失败", str(exc))

    def _persist_ai_run(self, run: AIRun) -> None:
        store = self._project_store
        if store is None or store.read_only:
            return
        try:
            WorkbenchStore(store).save_ai_run(run)
        except (StorageError, OSError, ValueError):
            LOGGER.exception("Failed to persist AI run")
            self.statusBar().showMessage("AI 审阅继续运行，但运行记录保存失败")

    def _finish_ai_run(
        self,
        *,
        status: AIRunStatus,
        output: dict | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        run = self._active_ai_run
        if run is None:
            return
        finished = replace(
            run,
            status=status,
            output=output,
            error_code=error_code,
            error_message=(
                None
                if error_message is None
                else str(error_message)[:2000]
            ),
            completed_at=utc_now(),
        )
        self._persist_ai_run(finished)
        self._active_ai_run = None

    def _matching_ai_review_runs(self) -> tuple[AIRun, ...]:
        store = self._project_store
        if store is None or self._active_shot_id is None or self._active_version_id is None:
            return ()
        try:
            runs = WorkbenchStore(store).list_ai_runs(
                MODULE_ID,
                status=AIRunStatus.COMPLETE,
            )
        except (StorageError, OSError, ValueError):
            LOGGER.exception("Failed to list saved AI reviews")
            return ()
        return tuple(
            run
            for run in runs
            if run.input_manifest.get("shot_id") == self._active_shot_id
            and run.input_manifest.get("version_id") == self._active_version_id
            and run.output is not None
        )

    def _refresh_ai_review_history(self, selected_id: str | None = None) -> None:
        runs = self._matching_ai_review_runs()
        reviewer_labels = {
            "deep_art_director_review": "深度主美",
            "art_director_review": "主美专项",
            "lighting_review": "灯光专项",
        }
        entries = [
            {
                "run_id": run.id,
                "label": (
                    f"{(run.completed_at or run.created_at).replace('T', ' ')[:19]} · "
                    f"{reviewer_labels.get(run.reviewer_id, run.reviewer_id)} · "
                    f"{run.provider_id} / {run.model_id}"
                ),
            }
            for run in runs
        ]
        chosen = selected_id or (runs[0].id if runs else None)
        self.ai_review_panel.set_history(
            entries,
            selected_id=chosen,
            read_only=bool(self._project_store and self._project_store.read_only),
        )
        if chosen:
            self._show_saved_ai_review(chosen)
        else:
            self._last_review_outcome = None
            self.ai_review_panel.clear_outcome()

    def _show_saved_ai_review(self, run_id: str) -> None:
        store = self._project_store
        if store is None:
            return
        try:
            run = WorkbenchStore(store).get_ai_run(run_id)
            if run is None or run.output is None:
                return
            outcome = review_outcome_from_payload(run.output)
        except (StorageError, OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, "无法读取审阅记录", str(exc))
            return
        self._last_review_outcome = outcome
        self.ai_review_panel.show_outcome(outcome)
        index = self.ai_review_panel.reviewer_combo.findData(run.reviewer_id)
        if index >= 0:
            self.ai_review_panel.reviewer_combo.setCurrentIndex(index)

    def _delete_saved_ai_review(self, run_id: str) -> None:
        store = self._project_store
        if store is None or store.read_only:
            return
        if QMessageBox.question(
            self,
            "删除审阅记录",
            "删除这次 AI 审阅记录？由它确认生成的任务和证据不会被删除。",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            WorkbenchStore(store).delete_ai_run(run_id)
        except (StorageError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法删除审阅记录", str(exc))
            return
        self._refresh_ai_review_history()
        self.statusBar().showMessage("审阅记录已删除；任务与证据保持不变")

    def _confirm_review_task(self, finding: object) -> None:
        if not isinstance(finding, dict):
            return
        store = self._project_store
        if store is None or store.read_only:
            QMessageBox.information(
                self,
                "修改任务",
                "当前项目为只读，不能保存任务。",
            )
            return
        if (
            QMessageBox.question(
                self,
                "确认修改任务",
                "将选中的 AI 发现确认为修改任务？\n"
                "AI 原文和来源会作为证据保留。",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        now = utc_now()
        evidence_id = str(uuid.uuid4())
        source = self._last_review_outcome
        evidence = Evidence(
            id=evidence_id,
            module_id=MODULE_ID,
            shot_id=self._active_shot_id,
            version_id=self._active_version_id,
            evidence_type=EvidenceType.ART_JUDGMENT,
            source=EvidenceSource.AI_PROVIDER,
            subject_type="review_finding",
            subject_id=str(finding.get("finding_id", evidence_id)),
            payload={
                "finding": dict(finding),
                "provider_id": (
                    None if source is None else source.provider_id
                ),
                "model_id": None if source is None else source.model_id,
                "user_confirmed": True,
            },
            created_at=now,
        )
        try:
            priority = TaskPriority(str(finding.get("priority", "medium")))
        except ValueError:
            priority = TaskPriority.MEDIUM
        task = Task(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            shot_id=self._active_shot_id,
            version_id=self._active_version_id,
            source_evidence_id=evidence.id,
            title=str(finding.get("observation", "AI 审阅任务")),
            description=(
                f"{finding.get('recommended_action', '')}\n"
                f"影响：{finding.get('impact', '')}"
            ).strip(),
            priority=priority,
            status=TaskStatus.OPEN,
            verification={
                "next_version_validation": finding.get(
                    "next_version_validation", ""
                )
            },
            created_at=now,
            updated_at=now,
        )
        try:
            workbench = WorkbenchStore(store)
            workbench.save_evidence(evidence)
            workbench.save_task(task)
        except (StorageError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存任务失败", str(exc))
            return
        self._refresh_workbench_tasks()
        self._emit_review_center_task(task)
        self.statusBar().showMessage("AI 发现已由用户确认为修改任务")

    def _show_lighting_annotations(self, scheme: object) -> None:
        if not isinstance(scheme, dict):
            return
        specs = []
        for index, annotation in enumerate(
            scheme.get("annotations", [])
        ):
            points = tuple(
                (float(point["x"]), float(point["y"]))
                for point in annotation.get("points", [])
                if isinstance(point, dict)
                and "x" in point
                and "y" in point
            )
            if not points:
                continue
            specs.append(
                AnnotationOverlaySpec(
                    annotation_id=f"preview-{index}",
                    kind=str(annotation.get("kind", "light_area")),
                    points=points,
                    label=str(annotation.get("label", "灯光标注")),
                )
            )
        self.reference_pane.canvas.clear_annotation_overlays()
        self.current_pane.canvas.set_annotation_overlays(specs)
        if specs:
            self.statusBar().showMessage(
                f"正在显示 {scheme.get('strategy', '')} 灯光方案标注 · "
                "Esc 退出"
            )

    def _persist_review_annotations(
        self,
        outcome: ReviewRunOutcome,
    ) -> None:
        store = self._project_store
        if store is None or store.read_only:
            return
        workbench = WorkbenchStore(store)
        now = utc_now()
        try:
            for scheme in outcome.output.get("target_schemes", []):
                strategy = str(scheme.get("strategy", ""))
                for item in scheme.get("annotations", []):
                    workbench.save_annotation(
                        Annotation(
                            id=str(uuid.uuid4()),
                            module_id=MODULE_ID,
                            shot_id=self._active_shot_id,
                            version_id=self._active_version_id,
                            evidence_id=None,
                            annotation_type=str(
                                item.get("kind", "light_area")
                            ),
                            geometry={
                                "points": list(item.get("points", [])),
                                "strategy": strategy,
                            },
                            label=str(item.get("label", "灯光标注")),
                            style={
                                "source": "ai_provider",
                                "provider_id": outcome.provider_id,
                                "model_id": outcome.model_id,
                            },
                            created_at=now,
                            updated_at=now,
                        )
                    )
        except (StorageError, OSError, ValueError):
            LOGGER.exception("Failed to persist lighting annotations")
            self.statusBar().showMessage("审阅完成，但灯光标注保存失败")

    def _confirm_annotation_tasks(self, scheme: object) -> None:
        if not isinstance(scheme, dict):
            return
        annotations = list(scheme.get("annotations", []))
        if not annotations:
            QMessageBox.information(
                self,
                "灯光标注任务",
                "当前方案没有可转换的标注。",
            )
            return
        store = self._project_store
        if store is None or store.read_only:
            QMessageBox.information(
                self,
                "灯光标注任务",
                "当前项目为只读，不能保存任务。",
            )
            return
        if (
            QMessageBox.question(
                self,
                "确认灯光标注任务",
                f"将当前方案的 {len(annotations)} 条标注确认为修改任务？",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        now = utc_now()
        workbench = WorkbenchStore(store)
        created_tasks = []
        try:
            for item in annotations:
                task = Task(
                        id=str(uuid.uuid4()),
                        module_id=MODULE_ID,
                        shot_id=self._active_shot_id,
                        version_id=self._active_version_id,
                        title=str(item.get("label", "灯光方案标注")),
                        description=(
                            f"方案：{scheme.get('strategy', '')}\n"
                            f"标注类型：{item.get('kind', '')}"
                        ),
                        priority=TaskPriority.MEDIUM,
                        status=TaskStatus.OPEN,
                        verification={
                            "annotation_geometry": list(
                                item.get("points", [])
                            )
                        },
                        created_at=now,
                        updated_at=now,
                    )
                workbench.save_task(task)
                created_tasks.append(task)
        except (StorageError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存灯光任务失败", str(exc))
            return
        self._refresh_workbench_tasks()
        self.review_task_requested.emit(
            [self._review_center_payload(task) for task in created_tasks]
        )
        self.statusBar().showMessage("灯光方案标注已由用户确认为修改任务")

    def _emit_review_center_task(self, task: Task) -> None:
        self.review_task_requested.emit(self._review_center_payload(task))

    def _review_center_payload(self, task: Task) -> dict[str, object]:
        store = self._project_store
        verification = dict(task.verification)
        acceptance = str(
            verification.get("next_version_validation", "")
            or (
                "在新的真实 UE 截图版本中复查，并记录与当前证据的差异。"
                if verification.get("requires_real_ue_version")
                else "在目标版本中复查该任务，并记录可核对的画面或测量证据。"
            )
        )
        return {
            "task_id": task.id,
            "title": task.title,
            "description": task.description,
            "acceptance_criteria": acceptance,
            "priority": task.priority.value,
            "source_module_id": task.module_id,
            "source_project_id": "" if store is None else store.manifest.project_id,
            "source_project_title": "" if store is None else store.manifest.name,
            "source_project_path": "" if store is None else str(store.root),
            "source_entity_type": "workbench_task",
            "source_entity_id": task.id,
            "source_version_id": task.version_id or "",
            "labels": ("场景审阅",),
        }

    def _refresh_workbench_tasks(self) -> None:
        store = self._project_store
        if store is None:
            self.ai_review_panel.show_tasks(())
            return
        try:
            tasks = WorkbenchStore(store).list_tasks(
                MODULE_ID,
                shot_id=self._active_shot_id,
                version_id=self._active_version_id,
            )
        except (StorageError, OSError):
            LOGGER.exception("Failed to load workbench tasks")
            return
        self.ai_review_panel.show_tasks(tasks)

    def focus_entity(self, entity_type: str, entity_id: str) -> None:
        """Focus an object selected by the application-wide search."""

        store = self._project_store
        if store is None or not entity_id:
            return
        if entity_type == "shot":
            if entity_id != self._active_shot_id:
                self._activate_shot(entity_id)
            self._refresh_project_navigator()
            return
        if entity_type != "workbench_task":
            return
        task = next(
            (
                item
                for item in WorkbenchStore(store).list_tasks(MODULE_ID)
                if item.id == entity_id
            ),
            None,
        )
        if task is None:
            return
        if task.shot_id and task.version_id:
            self._activate_version(task.shot_id, task.version_id)
        elif task.shot_id:
            self._activate_shot(task.shot_id)
        self.analysis_tabs.setCurrentWidget(self.ai_review_panel)
        self.statusBar().showMessage(
            f"已定位审阅任务：{task.title}",
            5000,
        )

    def _export_offline_review_pack(self) -> None:
        if (
            self._project_store is None
            or not {"reference", "current"}.issubset(self._images)
        ):
            QMessageBox.information(
                self,
                "离线审阅包",
                "请先打开项目并加载参考图和当前截图。",
            )
            return
        options = self.ai_review_panel.options()
        try:
            images = self._prepare_review_images(options)
            context = self._build_review_context()
            reviewer = self._reviewers[options.run.reviewer_id]
            pack = build_offline_review_pack(
                reviewer_id=options.run.reviewer_id,
                context=context.to_payload(),
                image_manifest=tuple(
                    {
                        "role": image.role,
                        "sha256": image.sha256,
                        "media_type": image.media_type,
                        "filename": f"{image.role}.png",
                    }
                    for image in images
                ),
                output_schema=reviewer.output_schema,
            )
        except (OSError, ValueError, StorageError) as exc:
            QMessageBox.warning(self, "导出准备失败", str(exc))
            return
        default = (
            self._project_store.root
            / self._project_store.manifest.exports_path
            / f"{self._active_shot_id}-{self._active_version_id}-review.zip"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出离线 AI 审阅包",
            str(default),
            "GATalk 审阅包 (*.zip)",
        )
        if not path:
            return
        try:
            destination = Path(path)
            if destination.suffix.lower() != ".zip":
                destination = destination.with_suffix(".zip")
            write_offline_review_pack(destination, pack, images)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.statusBar().showMessage(f"离线审阅包已导出：{destination}")

    def _start_measurement(self, role: str) -> None:
        loaded = self._images.get(role)
        if loaded is None:
            return
        parameters = self._measurement_parameters()
        self._measure_generation[role] += 1
        generation = self._measure_generation[role]
        self._measure_context[role][generation] = (
            self._asset_ids.get(role),
            parameters,
        )
        request = AnalyzerRequest(
            inputs={"rgb": loaded.rgb, "alpha": loaded.alpha},
            input_hashes={
                "rgb": self._measurement_input_hash(role, generation),
            },
            parameters=parameters,
        )
        self._start_worker(
            role,
            "measure",
            generation,
            lambda: self._measurement_analyzer.run(request),
        )

    def _measurement_parameters(self) -> dict:
        state = self._workspace_template
        return self._measurement_analyzer.default_parameters(
            state.palette_colours,
            state.palette_seed,
            state.palette_max_samples,
        )

    def _measurement_input_hash(self, role: str, generation: int) -> str:
        asset_id = self._asset_ids.get(role)
        if asset_id is not None and self._project_store is not None:
            try:
                return self._project_store.get_asset(asset_id).sha256
            except StorageError:
                LOGGER.exception("Failed to read analyzer input hash")
        return f"session:{role}:{generation}"

    def _load_cached_measurements(
        self,
        asset_id: str | None,
    ) -> ImageMeasurements | None:
        if asset_id is None or self._project_store is None:
            return None
        try:
            return self._project_store.load_measurements(
                asset_id,
                self._measurement_parameters(),
            )
        except (StorageError, OSError, ValueError):
            LOGGER.exception("Failed to restore cached measurements")
            return None

    def _start_reference_brief_fields(
        self,
        measurements: ImageMeasurements,
    ) -> None:
        store = self._project_store
        shot_id = self._active_shot_id
        asset_id = self._asset_ids.get("reference")
        image = self._images.get("reference")
        if (
            store is None
            or store.read_only
            or shot_id is None
            or asset_id is None
            or image is None
        ):
            return
        try:
            asset = store.get_asset(asset_id)
        except StorageError:
            LOGGER.exception("Failed to read reference asset for Brief")
            return
        descriptor = self._measurement_analyzer.descriptor
        project_id = store.manifest.project_id
        thresholds = self.comparison_panel.thresholds()
        five_thresholds = self._workspace_template.five_thresholds
        palette_seed = self._workspace_template.palette_seed
        palette_max_samples = self._workspace_template.palette_max_samples
        self._brief_generation += 1
        generation = self._brief_generation

        def build_fields():
            return {
                "project_id": project_id,
                "shot_id": shot_id,
                "asset_id": asset_id,
                "fields": build_reference_measurement_fields(
                    image,
                    asset,
                    measurements,
                    three_thresholds=thresholds,
                    five_thresholds=five_thresholds,
                    analyzer_id=descriptor.analyzer_id,
                    analyzer_version=descriptor.version,
                    palette_seed=palette_seed,
                    palette_max_samples=palette_max_samples,
                ),
                "analyzer_id": descriptor.analyzer_id,
                "analyzer_version": descriptor.version,
                "analyzed_at": utc_now(),
            }

        self._start_worker(
            "reference",
            "reference_brief",
            generation,
            build_fields,
        )

    def _persist_reference_brief_fields(self, result: object) -> None:
        if not isinstance(result, dict):
            return
        store = self._project_store
        if (
            store is None
            or store.read_only
            or result.get("project_id") != store.manifest.project_id
            or result.get("shot_id") != self._active_shot_id
            or result.get("asset_id") != self._asset_ids.get("reference")
        ):
            return
        document = store.get_reference_visual_brief(self._active_shot_id)
        if (
            document is None
            or document.asset_id != result.get("asset_id")
            or not isinstance(result.get("fields"), dict)
        ):
            return
        try:
            store.save_brief_fields(document.id, result["fields"])
            store.mark_reference_brief_analyzed(
                document.id,
                analyzer_id=str(result["analyzer_id"]),
                analyzer_version=str(result["analyzer_version"]),
                analyzed_at=str(result["analyzed_at"]),
            )
        except StorageError:
            LOGGER.exception("Failed to persist reference visual measurements")

    def _schedule_comparison_analysis(self) -> None:
        self._clear_palette_mask()
        if set(self._images) >= {"reference", "current"}:
            self._comparison_timer.start()
        else:
            self._comparison_timer.stop()
            self._comparison_generation += 1
            self._shared_palette_result = None
            self.comparison_panel.clear()

    def _start_comparison_analysis(self) -> None:
        reference = self._images.get("reference")
        current = self._images.get("current")
        if reference is None or current is None:
            return
        shared_parameters = self._shared_palette_analyzer.default_parameters(
            self._workspace_template.palette_colours,
            self._workspace_template.palette_seed,
            self._workspace_template.palette_max_samples,
        )
        low, high = self.comparison_panel.thresholds()
        distribution_metric, distribution_bins, neutral_threshold = (
            self.comparison_panel.distribution_parameters()
        )
        luminance_parameters = (
            self._luminance_comparison_analyzer.default_parameters(low, high)
        )
        input_hashes = {
            "reference": self._role_input_hash("reference"),
            "current": self._role_input_hash("current"),
        }
        selection = {
            "project_id": (
                None
                if self._project_store is None
                else self._project_store.manifest.project_id
            ),
            "shot_id": self._active_shot_id,
            "version_id": self._active_version_id,
            "reference_asset_id": self._asset_ids.get("reference"),
            "current_asset_id": self._asset_ids.get("current"),
        }
        cached_shared: SharedPaletteResult | None = None
        cached_luminance: LuminanceComparison | None = None
        store = self._project_store
        if (
            store is not None
            and self._active_shot_id is not None
            and self._active_version_id is not None
        ):
            try:
                shared_record = store.load_comparison_analysis(
                    self._active_shot_id,
                    self._active_version_id,
                    module_id=MODULE_ID,
                    analyzer_id=SHARED_PALETTE_ANALYZER_ID,
                    analyzer_version=self._shared_palette_analyzer.descriptor.version,
                    parameters=shared_parameters,
                )
                luminance_record = store.load_comparison_analysis(
                    self._active_shot_id,
                    self._active_version_id,
                    module_id=MODULE_ID,
                    analyzer_id=LUMINANCE_COMPARISON_ANALYZER_ID,
                    analyzer_version=(
                        self._luminance_comparison_analyzer.descriptor.version
                    ),
                    parameters=luminance_parameters,
                )
                if shared_record is not None:
                    cached_shared = shared_palette_from_payload(
                        shared_record.result
                    )
                if luminance_record is not None:
                    cached_luminance = luminance_comparison_from_payload(
                        luminance_record.result
                    )
            except (StorageError, KeyError, TypeError, ValueError):
                LOGGER.exception("Failed to restore comparison analysis")

        self._comparison_generation += 1
        generation = self._comparison_generation
        shared_request = AnalyzerRequest(
            inputs={
                "reference_rgb": reference.rgb,
                "current_rgb": current.rgb,
            },
            input_hashes=input_hashes,
            parameters=shared_parameters,
        )
        luminance_request = AnalyzerRequest(
            inputs={
                "reference_rgb": reference.rgb,
                "current_rgb": current.rgb,
            },
            input_hashes=input_hashes,
            parameters=luminance_parameters,
        )

        def analyze():
            shared = (
                cached_shared
                if cached_shared is not None
                else self._shared_palette_analyzer.run(shared_request)
            )
            luminance = (
                cached_luminance
                if cached_luminance is not None
                else self._luminance_comparison_analyzer.run(
                    luminance_request
                )
            )
            return {
                "selection": selection,
                "shared": shared,
                "luminance": luminance,
                "shared_parameters": shared_parameters,
                "luminance_parameters": luminance_parameters,
                "reference_thumbnail": quantize_three_value_with_thresholds(
                    reference.rgb,
                    low,
                    high,
                ),
                "current_thumbnail": quantize_three_value_with_thresholds(
                    current.rgb,
                    low,
                    high,
                ),
                "distribution": compare_colour_distribution(
                    reference.rgb,
                    current.rgb,
                    metric=distribution_metric,
                    bins=distribution_bins,
                    neutral_threshold=neutral_threshold,
                ),
            }

        self.statusBar().showMessage("正在计算共享色板与三阶明度比较…")
        self._start_worker("comparison", "comparison", generation, analyze)

    def _apply_comparison_result(self, result: object) -> None:
        if not isinstance(result, dict):
            return
        selection = result.get("selection")
        if not isinstance(selection, dict):
            return
        current_selection = {
            "project_id": (
                None
                if self._project_store is None
                else self._project_store.manifest.project_id
            ),
            "shot_id": self._active_shot_id,
            "version_id": self._active_version_id,
            "reference_asset_id": self._asset_ids.get("reference"),
            "current_asset_id": self._asset_ids.get("current"),
        }
        if selection != current_selection:
            return
        shared = result.get("shared")
        luminance = result.get("luminance")
        distribution = result.get("distribution")
        if not isinstance(shared, SharedPaletteResult) or not isinstance(
            luminance,
            LuminanceComparison,
        ) or not isinstance(distribution, DistributionComparison):
            return
        self._shared_palette_result = shared
        self.comparison_panel.set_shared_palette(shared)
        reference = self._images.get("reference")
        current = self._images.get("current")
        if reference is None or current is None:
            return
        self.comparison_panel.set_luminance(
            luminance,
            numpy_to_qimage(result["reference_thumbnail"]),
            numpy_to_qimage(result["current_thumbnail"]),
        )
        self.comparison_panel.set_distribution(distribution)
        reference_measurements = self._measurements.get("reference")
        current_measurements = self._measurements.get("current")
        if reference_measurements is not None and current_measurements is not None:
            self.comparison_panel.set_independent_palettes(
                reference_measurements.palette,
                current_measurements.palette,
            )
        self._update_region_analysis_freshness()
        store = self._project_store
        if (
            store is not None
            and not store.read_only
            and self._active_shot_id is not None
            and self._active_version_id is not None
        ):
            try:
                store.save_comparison_analysis(
                    self._active_shot_id,
                    self._active_version_id,
                    module_id=MODULE_ID,
                    analyzer_id=SHARED_PALETTE_ANALYZER_ID,
                    analyzer_version=(
                        self._shared_palette_analyzer.descriptor.version
                    ),
                    parameters=result["shared_parameters"],
                    result=shared_palette_to_payload(shared),
                    evidence_type="algorithm_inference",
                )
                store.save_comparison_analysis(
                    self._active_shot_id,
                    self._active_version_id,
                    module_id=MODULE_ID,
                    analyzer_id=LUMINANCE_COMPARISON_ANALYZER_ID,
                    analyzer_version=(
                        self._luminance_comparison_analyzer.descriptor.version
                    ),
                    parameters=result["luminance_parameters"],
                    result=luminance_comparison_to_payload(luminance),
                    evidence_type="measurement",
                )
            except StorageError:
                LOGGER.exception("Failed to persist comparison analysis")
                self.statusBar().showMessage(
                    "对比分析完成，但结果保存失败"
                )
                return
        self.statusBar().showMessage("共享色板与三阶明度比较完成")
        selected_pair_id = self.region_controller.selected_pair_id
        if selected_pair_id is not None:
            self._start_region_analysis(selected_pair_id)

    def _start_region_analysis(self, pair_id: str) -> None:
        store = self._project_store
        region_store = self.region_controller.store
        view = self.region_controller.pair_view(pair_id)
        shared = self._shared_palette_result
        reference = self._images.get("reference")
        current = self._images.get("current")
        if (
            store is None
            or region_store is None
            or view is None
            or shared is None
            or reference is None
            or current is None
            or self._active_shot_id is None
            or self._active_version_id is None
        ):
            self.region_panel.clear_analysis(
                "等待参考图、当前截图和全图共享色板完成后再分析。"
            )
            return
        centres = np.asarray(
            [item.oklab for item in shared.colours],
            dtype=np.float64,
        )
        if len(centres) == 0:
            self.region_panel.clear_analysis("共享色板为空，无法进行区域归类。")
            return
        reference_rect = view.reference_region.normalized_rect
        current_rect = view.current_region.normalized_rect
        parameters = self._paired_region_analyzer.default_parameters(
            *self.comparison_panel.thresholds()
        )
        reference_hash = self._role_input_hash("reference")
        current_hash = self._role_input_hash("current")
        shared_cache_key = self._shared_palette_cache_key(
            reference_hash,
            current_hash,
        )
        reference_geometry = reference_rect.to_dict()
        current_geometry = current_rect.to_dict()
        request = AnalyzerRequest(
            inputs={
                "reference_rgb": reference.rgb,
                "current_rgb": current.rgb,
                "reference_rect": tuple(reference_geometry.values()),
                "current_rect": tuple(current_geometry.values()),
                "shared_palette_centres": centres,
            },
            input_hashes={
                "reference_image": reference_hash,
                "current_image": current_hash,
                "reference_geometry": self._dict_hash(reference_geometry),
                "current_geometry": self._dict_hash(current_geometry),
                "shared_palette": shared_cache_key,
            },
            parameters=parameters,
        )
        cache_key = self._paired_region_analyzer.cache_key(request)
        selection = {
            "project_id": store.manifest.project_id,
            "shot_id": self._active_shot_id,
            "version_id": self._active_version_id,
            "pair_id": pair_id,
            "reference_asset_id": self._asset_ids.get("reference"),
            "current_asset_id": self._asset_ids.get("current"),
            "reference_geometry": reference_geometry,
            "current_geometry": current_geometry,
            "shared_palette_cache_key": shared_cache_key,
        }
        try:
            cached = region_store.load_analysis(cache_key)
            if cached is not None:
                restored = paired_region_from_payload(cached.result)
                self._active_region_analysis = (pair_id, restored)
                self.region_panel.set_analysis(restored, shared)
                self.region_controller.refresh()
                self.statusBar().showMessage("成对区域分析已从项目恢复")
                return
            latest = region_store.latest_analysis(pair_id)
            if latest is not None:
                try:
                    stale_result = paired_region_from_payload(latest.result)
                    self.region_panel.set_analysis(
                        stale_result,
                        shared,
                        stale=True,
                    )
                except (KeyError, TypeError, ValueError):
                    self.region_panel.clear_analysis(
                        "旧区域分析无法读取，正在重新分析。"
                    )
            else:
                self.region_panel.clear_analysis("正在分析选中的区域对…")
            if not store.read_only:
                region_store.mark_pair_analyses_stale(pair_id)
        except (StorageError, KeyError, TypeError, ValueError):
            LOGGER.exception("Failed to restore paired region analysis")
            self.region_panel.clear_analysis("正在重新计算区域分析…")

        self._region_analysis_generation += 1
        generation = self._region_analysis_generation

        def analyze_region_pair():
            result = self._paired_region_analyzer.run(request)
            return {
                "selection": selection,
                "result": result,
                "parameters": parameters,
                "cache_key": cache_key,
                "reference_hash": reference_hash,
                "current_hash": current_hash,
            }

        self.statusBar().showMessage("正在后台计算成对区域明度与色彩…")
        self._start_worker(
            "comparison",
            "region_analysis",
            generation,
            analyze_region_pair,
        )

    def _apply_region_analysis_result(self, result: object) -> None:
        if not isinstance(result, dict):
            return
        selection = result.get("selection")
        analysis = result.get("result")
        if (
            not isinstance(selection, dict)
            or not isinstance(analysis, PairedRegionAnalysis)
        ):
            return
        pair_id = str(selection.get("pair_id", ""))
        current_view = self.region_controller.pair_view(pair_id)
        store = self._project_store
        if current_view is None or store is None:
            return
        current_selection = {
            "project_id": store.manifest.project_id,
            "shot_id": self._active_shot_id,
            "version_id": self._active_version_id,
            "pair_id": pair_id,
            "reference_asset_id": self._asset_ids.get("reference"),
            "current_asset_id": self._asset_ids.get("current"),
            "reference_geometry": (
                current_view.reference_region.normalized_rect.to_dict()
            ),
            "current_geometry": (
                current_view.current_region.normalized_rect.to_dict()
            ),
            "shared_palette_cache_key": self._shared_palette_cache_key(
                self._role_input_hash("reference"),
                self._role_input_hash("current"),
            ),
        }
        if selection != current_selection:
            return
        shared = self._shared_palette_result
        if shared is None:
            return
        self._active_region_analysis = (pair_id, analysis)
        self.region_panel.set_analysis(analysis, shared)
        region_store = self.region_controller.store
        if region_store is not None and not store.read_only:
            try:
                descriptor = self._paired_region_analyzer.descriptor
                region_store.save_analysis(
                    pair_id,
                    analyzer_id=descriptor.analyzer_id,
                    analyzer_version=descriptor.version,
                    reference_image_hash=str(result["reference_hash"]),
                    current_image_hash=str(result["current_hash"]),
                    reference_region_geometry=selection[
                        "reference_geometry"
                    ],
                    current_region_geometry=selection["current_geometry"],
                    shared_palette_cache_key=selection[
                        "shared_palette_cache_key"
                    ],
                    parameters=result["parameters"],
                    cache_key=str(result["cache_key"]),
                    result=paired_region_to_payload(analysis),
                )
                self.region_controller.refresh()
            except (StorageError, ValueError, TypeError):
                LOGGER.exception("Failed to persist paired region analysis")
                self.statusBar().showMessage(
                    "区域分析完成，但结果保存失败"
                )
                return
        self.statusBar().showMessage("成对区域分析完成")

    @staticmethod
    def _dict_hash(value: dict) -> str:
        return hashlib.sha256(
            canonical_json(value).encode("utf-8")
        ).hexdigest()

    def _shared_palette_cache_key(
        self,
        reference_hash: str,
        current_hash: str,
    ) -> str:
        parameters = self._shared_palette_analyzer.default_parameters(
            self._workspace_template.palette_colours,
            self._workspace_template.palette_seed,
            self._workspace_template.palette_max_samples,
        )
        return self._shared_palette_analyzer.cache_key(
            AnalyzerRequest(
                inputs={},
                input_hashes={
                    "reference": reference_hash,
                    "current": current_hash,
                },
                parameters=parameters,
            )
        )

    def _update_region_analysis_freshness(self) -> None:
        store = self._project_store
        region_store = self.region_controller.store
        shared = self._shared_palette_result
        reference = self._images.get("reference")
        current = self._images.get("current")
        if (
            store is None
            or store.read_only
            or region_store is None
            or shared is None
            or reference is None
            or current is None
        ):
            return
        centres = np.asarray(
            [item.oklab for item in shared.colours],
            dtype=np.float64,
        )
        if len(centres) == 0:
            return
        reference_hash = self._role_input_hash("reference")
        current_hash = self._role_input_hash("current")
        shared_key = self._shared_palette_cache_key(
            reference_hash,
            current_hash,
        )
        parameters = self._paired_region_analyzer.default_parameters(
            *self.comparison_panel.thresholds()
        )
        expected: dict[str, str] = {}
        for view in self.region_controller.pair_views():
            reference_geometry = (
                view.reference_region.normalized_rect.to_dict()
            )
            current_geometry = view.current_region.normalized_rect.to_dict()
            request = AnalyzerRequest(
                inputs={},
                input_hashes={
                    "reference_image": reference_hash,
                    "current_image": current_hash,
                    "reference_geometry": self._dict_hash(
                        reference_geometry
                    ),
                    "current_geometry": self._dict_hash(current_geometry),
                    "shared_palette": shared_key,
                },
                parameters=parameters,
            )
            expected[view.pair.id] = self._paired_region_analyzer.cache_key(
                request
            )
        try:
            region_store.update_analysis_freshness(expected)
            self.region_controller.refresh()
        except StorageError:
            LOGGER.exception("Failed to update paired region freshness")

    def _role_input_hash(self, role: str) -> str:
        store = self._project_store
        asset_id = self._asset_ids.get(role)
        if store is not None and asset_id is not None:
            try:
                return store.get_asset(asset_id).sha256
            except StorageError:
                LOGGER.exception("Failed to read comparison input hash")
        image = self._images.get(role)
        if image is None:
            return f"session:{role}:empty"
        return (
            f"session:{role}:{image.working_size[0]}x{image.working_size[1]}:"
            f"{int(image.rgb[0, 0, 0])}"
        )

    def _comparison_thresholds_changed(self, low: float, high: float) -> None:
        if low >= high:
            return
        self._workspace_template = replace(
            self._workspace_template,
            three_threshold_low=low,
            three_threshold_high=high,
        )
        region_store = self.region_controller.store
        if (
            region_store is not None
            and self._project_store is not None
            and not self._project_store.read_only
            and self._active_shot_id is not None
            and self._active_version_id is not None
        ):
            try:
                region_store.mark_version_analyses_stale(
                    self._active_shot_id,
                    self._active_version_id,
                )
                self.region_controller.refresh()
            except StorageError:
                LOGGER.exception("Failed to stale region analyses")
        self._mark_workspace_dirty()
        self._schedule_comparison_analysis()
        if self.mode_combo.currentData() == "three_value":
            self._schedule_render()
        measurements = self._measurements.get("reference")
        if measurements is not None:
            self._start_reference_brief_fields(measurements)

    def _analysis_tab_changed(self, index: int) -> None:
        self._mark_workspace_dirty()
        if index == 4 and {"reference", "current"}.issubset(self._images):
            self._start_match_profile(
                self.optimization_panel.match_weights()
            )

    def _independent_palette_selected(self, role: str, index: int) -> None:
        if self._active_mask == (role, index):
            self._clear_palette_mask()
            return
        image = self._images.get(role)
        measurements = self._measurements.get(role)
        if (
            image is None
            or measurements is None
            or not 0 <= index < len(measurements.palette)
        ):
            return
        centres = np.asarray(
            [item.oklab for item in measurements.palette],
            dtype=np.float64,
        )
        self._start_palette_mask(
            (role, index),
            {role: (image.rgb, centres, index)},
        )

    def _shared_palette_selected(self, index: int) -> None:
        shared = self._shared_palette_result
        if self._active_mask == ("shared", index):
            self._clear_palette_mask()
            return
        if (
            shared is None
            or not 0 <= index < len(shared.colours)
            or "reference" not in self._images
            or "current" not in self._images
        ):
            return
        centres = np.asarray(
            [item.oklab for item in shared.colours],
            dtype=np.float64,
        )
        self._start_palette_mask(
            ("shared", index),
            {
                role: (self._images[role].rgb, centres, index)
                for role in ("reference", "current")
            },
        )

    def _region_palette_selected(self, index: int) -> None:
        active = self._active_region_analysis
        shared = self._shared_palette_result
        if active is None or shared is None:
            return
        pair_id, analysis = active
        view = self.region_controller.pair_view(pair_id)
        if (
            view is None
            or not 0 <= index < len(shared.colours)
            or "reference" not in self._images
            or "current" not in self._images
        ):
            return
        key = (f"region:{pair_id}", index)
        if self._active_mask == key:
            self._clear_palette_mask()
            return
        centres = np.asarray(
            [item.oklab for item in shared.colours],
            dtype=np.float64,
        )
        self._clear_palette_mask()
        self._active_mask = key
        self._mask_generation += 1
        generation = self._mask_generation
        reference_rect = view.reference_region.normalized_rect
        current_rect = view.current_region.normalized_rect
        reference_rgb = self._images["reference"].rgb
        current_rgb = self._images["current"].rgb

        def build_region_mask():
            return {
                "key": key,
                "previews": {
                    "reference": render_region_palette_source_mask(
                        reference_rgb,
                        (
                            reference_rect.x,
                            reference_rect.y,
                            reference_rect.width,
                            reference_rect.height,
                        ),
                        centres,
                        index,
                    ),
                    "current": render_region_palette_source_mask(
                        current_rgb,
                        (
                            current_rect.x,
                            current_rect.y,
                            current_rect.width,
                            current_rect.height,
                        ),
                        centres,
                        index,
                    ),
                },
            }

        self.statusBar().showMessage("正在定位成对区域内的颜色来源…")
        self._start_worker(
            "comparison",
            "mask",
            generation,
            build_region_mask,
        )

    def _start_palette_mask(
        self,
        key: tuple[str, int],
        inputs: dict[str, tuple[np.ndarray, np.ndarray, int]],
    ) -> None:
        self._clear_palette_mask()
        self._active_mask = key
        if key[0] in self.analysis_widgets:
            self.analysis_widgets[key[0]].palette.set_selected_index(key[1])
        self._mask_generation += 1
        generation = self._mask_generation

        def build_mask():
            previews = {}
            for role, (rgb, centres, index) in inputs.items():
                mask = palette_membership_mask(rgb, centres, index)
                previews[role] = render_palette_source_mask(rgb, mask)
            return {"key": key, "previews": previews}

        self.statusBar().showMessage("正在定位颜色来源区域…")
        self._start_worker("comparison", "mask", generation, build_mask)

    def _apply_mask_result(self, result: object) -> None:
        if (
            not isinstance(result, dict)
            or result.get("key") != self._active_mask
            or not isinstance(result.get("previews"), dict)
        ):
            return
        for role, preview in result["previews"].items():
            image = self._images.get(role)
            if image is not None:
                self._canvas_for(role).set_overlay(
                    numpy_to_qimage(preview, image.alpha)
                )
        if self._active_mask is None:
            return
        scope, index = self._active_mask
        if scope == "shared" and self._shared_palette_result is not None:
            item = self._shared_palette_result.colours[index]
            self.statusBar().showMessage(
                f"{item.hex_colour} · 参考 {item.reference_proportion * 100:.1f}% "
                f"· 当前 {item.current_proportion * 100:.1f}% · Esc 退出遮罩"
            )
        elif (
            scope.startswith("region:")
            and self._active_region_analysis is not None
            and self._shared_palette_result is not None
        ):
            pair_id, analysis = self._active_region_analysis
            if scope == f"region:{pair_id}":
                item = self._shared_palette_result.colours[index]
                reference_ratio = (
                    analysis.reference.shared_palette_proportions[index]
                )
                current_ratio = (
                    analysis.current.shared_palette_proportions[index]
                )
                self.statusBar().showMessage(
                    f"区域 {item.hex_colour} · "
                    f"参考 {reference_ratio * 100:.1f}% · "
                    f"当前 {current_ratio * 100:.1f}% · Esc 退出遮罩"
                )
        else:
            measurements = self._measurements.get(scope)
            if measurements is not None and index < len(measurements.palette):
                item = measurements.palette[index]
                self.statusBar().showMessage(
                    f"{ROLE_LABELS[scope]} {item.hex_colour} · "
                    f"{item.proportion * 100:.1f}% · Esc 退出遮罩"
                )

    def _clear_palette_mask(self) -> None:
        was_active = self._active_mask is not None
        self._active_mask = None
        self._mask_generation += 1
        for pane in (self.reference_pane, self.current_pane):
            pane.canvas.clear_overlay()
        for widget in self.analysis_widgets.values():
            widget.palette.set_selected_index(None)
        if hasattr(self, "comparison_panel"):
            self.comparison_panel.clear_palette_selection()
        if hasattr(self, "region_panel"):
            self.region_panel.clear_region_palette_selection()
        if was_active:
            self.statusBar().showMessage("已退出颜色来源遮罩")

    def _escape_current_tool(self) -> None:
        if self._active_mask is not None:
            self._clear_palette_mask()
            return
        if (
            self.reference_pane.canvas.annotation_overlay_count
            or self.current_pane.canvas.annotation_overlay_count
        ):
            self.reference_pane.canvas.clear_annotation_overlays()
            self.current_pane.canvas.clear_annotation_overlays()
            self.statusBar().showMessage("已退出灯光方案标注")
            return
        if self._optimization_preview_visible:
            current = self._images.get("current")
            if current is not None:
                self.current_pane.canvas.set_image(
                    numpy_to_qimage(current.rgb, current.alpha),
                    reset_view=False,
                )
            self._optimization_preview_visible = False
            self.optimization_panel.grade_original_button.blockSignals(
                True
            )
            self.optimization_panel.grade_original_button.setChecked(
                False
            )
            self.optimization_panel.grade_original_button.blockSignals(
                False
            )
            self.statusBar().showMessage(
                "已退出优化预览，恢复真实当前截图"
            )
            return
        if self.region_controller.escape():
            self.statusBar().showMessage("已退出区域模式")
            return
        if self.composition_guide_combo.currentData() != "none":
            self._set_combo_data(
                self.composition_guide_combo,
                "none",
                "none",
            )
            self.statusBar().showMessage("已关闭构图辅助线")

    def _current_render_settings(self) -> RenderSettings:
        return RenderSettings(
            mode=str(self.mode_combo.currentData()),
            blur_sigma=self.blur_slider.value() / 10.0,
            three_thresholds=self.comparison_panel.thresholds(),
            five_thresholds=self._workspace_template.five_thresholds,
            silhouette_threshold=self.silhouette_slider.value() / 100.0,
        )

    def _start_render(self, role: str) -> None:
        loaded = self._images.get(role)
        if loaded is None:
            return
        settings = self._current_render_settings()
        self._render_generation[role] += 1
        generation = self._render_generation[role]

        if settings.mode == "original" and settings.blur_sigma == 0.0:
            self._canvas_for(role).set_image(
                numpy_to_qimage(loaded.rgb, loaded.alpha),
                reset_view=False,
            )
            return

        self._start_worker(
            role,
            "render",
            generation,
            lambda: render_image(loaded.rgb, settings),
        )

    def _display_mode_changed(self, _value=None) -> None:
        self.silhouette_slider.setEnabled(
            self.mode_combo.currentData() == "silhouette"
        )
        self._schedule_render()
        self._mark_workspace_dirty()

    def _schedule_render(self, _value=None) -> None:
        if hasattr(self, "_render_timer"):
            self._render_timer.start()

    def _refresh_rendered_images(self) -> None:
        for role in tuple(self._images):
            self._start_render(role)

    def _blur_changed(self, value: int) -> None:
        self.blur_label.setText(f"{value / 10.0:.1f}")
        self._schedule_render()
        self._mark_workspace_dirty()

    def _silhouette_threshold_changed(self, value: int) -> None:
        self.silhouette_label.setText(f"{value / 100.0:.2f}")
        if self.mode_combo.currentData() == "silhouette":
            self._schedule_render()
        self._mark_workspace_dirty()

    def _comparison_mode_changed(self, _index: int) -> None:
        is_ab = self.comparison_combo.currentData() == "ab"
        self.ab_button.setEnabled(is_ab)
        if not is_ab:
            self.reference_pane.show()
            self.current_pane.show()
        else:
            self._apply_ab_visibility()
        self._mark_workspace_dirty()

    def _toggle_ab(self) -> None:
        if self.comparison_combo.currentData() != "ab":
            self.comparison_combo.setCurrentIndex(
                self.comparison_combo.findData("ab")
            )
        self._ab_role = "current" if self._ab_role == "reference" else "reference"
        self._apply_ab_visibility()
        self._mark_workspace_dirty()

    def _apply_ab_visibility(self) -> None:
        self.reference_pane.setVisible(self._ab_role == "reference")
        self.current_pane.setVisible(self._ab_role == "current")
        self.ab_button.setText(
            f"当前：{ROLE_LABELS[self._ab_role]}（Space 切换）"
        )
        self.analysis_tabs.setCurrentIndex(0 if self._ab_role == "reference" else 1)

    def _sync_from(
        self,
        source_role: str,
        zoom_factor: float,
        center_x: float,
        center_y: float,
    ) -> None:
        self._mark_workspace_dirty()
        if not self.sync_checkbox.isChecked():
            return
        target_role = "current" if source_role == "reference" else "reference"
        self._canvas_for(target_role).apply_external_view_state(
            zoom_factor,
            center_x,
            center_y,
        )

    def _reset_views(self) -> None:
        self.reference_pane.canvas.reset_view()
        self.current_pane.canvas.reset_view()
        self._mark_workspace_dirty()

    def _composition_guide_changed(self, _index: int = -1) -> None:
        guide = composition_guide(
            str(self.composition_guide_combo.currentData() or "none")
        )
        spec = (
            None
            if guide is None
            else GuideOverlaySpec(
                guide_id=guide.guide_id,
                label=guide.display_name,
                lines=guide.lines,
            )
        )
        self.reference_pane.canvas.set_guide_overlay(spec)
        self.current_pane.canvas.set_guide_overlay(spec)
        self._mark_workspace_dirty()

    def _mark_workspace_dirty(self, _value=None) -> None:
        if (
            self._project_store is None
            or self._project_store.read_only
            or self._restoring_workspace
        ):
            return
        self._workspace_dirty = True
        if hasattr(self, "_autosave_timer"):
            self._autosave_timer.start()

    def _autosave_workspace(self) -> None:
        self._save_workspace(show_error=False)

    def _save_workspace(self, show_error: bool) -> bool:
        store = self._project_store
        if store is None or not self._workspace_dirty:
            return True
        state = replace(
            self._workspace_template,
            current_shot_id=self._active_shot_id,
            current_version_id=self._active_version_id,
            display_mode=str(self.mode_combo.currentData()),
            comparison_mode=str(self.comparison_combo.currentData()),
            ab_role=self._ab_role,
            sync_views=self.sync_checkbox.isChecked(),
            blur_sigma=self.blur_slider.value() / 10.0,
            silhouette_threshold=self.silhouette_slider.value() / 100.0,
            composition_guide=str(
                self.composition_guide_combo.currentData() or "none"
            ),
            three_threshold_low=self.comparison_panel.thresholds()[0],
            three_threshold_high=self.comparison_panel.thresholds()[1],
            active_analysis_tab=(
                (
                    "reference",
                    "current",
                    "comparison",
                    "tasks",
                    "optimization",
                )[
                    self.analysis_tabs.currentIndex()
                ]
                if 0 <= self.analysis_tabs.currentIndex() < 5
                else "reference"
            ),
        )
        try:
            if self._active_shot_id is not None:
                if self.reference_pane.canvas.has_image:
                    zoom, center_x, center_y = (
                        self.reference_pane.canvas.current_view_state()
                    )
                    store.save_canvas_state(
                        CanvasState(
                            "reference",
                            self._active_shot_id,
                            None,
                            zoom,
                            center_x,
                            center_y,
                        )
                    )
                if (
                    self._active_version_id is not None
                    and self.current_pane.canvas.has_image
                ):
                    zoom, center_x, center_y = (
                        self.current_pane.canvas.current_view_state()
                    )
                    store.save_canvas_state(
                        CanvasState(
                            "current",
                            self._active_shot_id,
                            self._active_version_id,
                            zoom,
                            center_x,
                            center_y,
                        )
                    )
            store.save_workspace_state(state)
            self._workspace_template = state
            self._workspace_dirty = False
            self.statusBar().showMessage("项目已自动保存")
            return True
        except (StorageError, OSError, ValueError) as exc:
            LOGGER.exception("Autosave failed")
            self._workspace_dirty = True
            self.statusBar().showMessage("自动保存失败；内存中的修改仍保留")
            if show_error:
                self._show_storage_error("项目保存失败", exc)
            return False

    def _flush_autosave(self, show_error: bool) -> bool:
        if hasattr(self, "_autosave_timer"):
            self._autosave_timer.stop()
        return self._save_workspace(show_error)

    def _clear_role(self, role: str) -> None:
        self._images.pop(role, None)
        self._measurements.pop(role, None)
        self._asset_ids[role] = None
        self._clear_palette_mask()
        self._shared_palette_result = None
        self._active_region_analysis = None
        self._safe_grade_preview = None
        self._safe_grade_recipe = None
        self._concept_preview_rgb = None
        self._last_concept_preview = None
        self._last_preview_validation = None
        self._optimization_preview_visible = False
        self._match_generation += 1
        self._grade_generation += 1
        self._concept_generation += 1
        self._region_analysis_generation += 1
        if hasattr(self, "comparison_panel"):
            self.comparison_panel.clear()
        if hasattr(self, "region_panel"):
            self.region_panel.clear_analysis()
        if hasattr(self, "optimization_panel"):
            self.optimization_panel.reset_transient_state()
        self._canvas_for(role).clear_image()
        self.analysis_widgets[role].clear(
            "尚未导入参考图"
            if role == "reference"
            else "尚未导入当前截图"
        )

    def _invalidate_image_jobs(self) -> None:
        if self._ai_cancellation is not None:
            self._ai_cancellation.cancel()
            self._ai_cancellation = None
        self._ai_review_generation += 1
        if self._concept_cancellation is not None:
            self._concept_cancellation.cancel()
            self._concept_cancellation = None
        self._concept_generation += 1
        self._match_generation += 1
        self._grade_generation += 1
        if hasattr(self, "ai_review_panel"):
            self.ai_review_panel.set_running(False)
        if hasattr(self, "optimization_panel"):
            self.optimization_panel.show_concept_running(False)
        self._brief_generation += 1
        self._comparison_generation += 1
        self._region_analysis_generation += 1
        self._mask_generation += 1
        if hasattr(self, "_comparison_timer"):
            self._comparison_timer.stop()
        for role in ("reference", "current"):
            self._load_generation[role] += 1
            self._render_generation[role] += 1
            self._measure_generation[role] += 1
            self._import_generation[role] += 1
            self._load_context[role].clear()
            self._measure_context[role].clear()
            self._import_context[role].clear()

    def _canvas_for(self, role: str) -> ImageCanvas:
        return (
            self.reference_pane.canvas
            if role == "reference"
            else self.current_pane.canvas
        )

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str, fallback: str) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findData(fallback)
        combo.setCurrentIndex(max(0, index))

    @staticmethod
    def _is_valid_project_folder_name(name: str) -> bool:
        return bool(
            name
            and not any(character in INVALID_WINDOWS_NAME_CHARS for character in name)
            and not name.endswith((" ", "."))
        )

    def _show_storage_error(self, title: str, error: Exception) -> None:
        LOGGER.exception("%s: %s", title, error)
        QMessageBox.warning(self, title, str(error))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._flush_autosave(show_error=False):
            self._cancel_ai_review()
            self._review_coordinator.close()
            if self._project_store is not None:
                self._project_store.close()
            event.accept()
            return
        choice = QMessageBox.warning(
            self,
            "项目尚未保存",
            "自动保存失败。内存中的修改仍在。要重试、放弃未保存状态，还是取消关闭？",
            QMessageBox.StandardButton.Retry
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Retry,
        )
        if choice == QMessageBox.StandardButton.Retry:
            if self._flush_autosave(show_error=True):
                self._cancel_ai_review()
                self._review_coordinator.close()
                if self._project_store is not None:
                    self._project_store.close()
                event.accept()
            else:
                event.ignore()
        elif choice == QMessageBox.StandardButton.Discard:
            self._cancel_ai_review()
            self._review_coordinator.close()
            if self._project_store is not None:
                self._project_store.close()
            event.accept()
        else:
            event.ignore()
