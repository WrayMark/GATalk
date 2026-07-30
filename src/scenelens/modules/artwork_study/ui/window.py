from __future__ import annotations

from dataclasses import replace
import logging
from pathlib import Path
from typing import Any, Callable, Mapping

from PySide6.QtCore import QThread, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scenelens.analysis.artwork_study import (
    ArtworkLocalAnalysis,
    analyze_artwork,
    format_local_analysis_summary,
)
from scenelens.analysis.models import ImageMeasurements, RenderSettings
from scenelens.analysis.pipeline import measure_image, render_image
from scenelens.analysis.shared_palette import (
    palette_membership_mask,
    render_palette_source_mask,
)
from scenelens.imaging.loader import LoadedImage, load_image
from scenelens.imaging.provider_export import (
    ProviderImageExportOptions,
    prepare_provider_image,
)
from scenelens.imaging.qt import numpy_to_qimage
from scenelens.modules.artwork_study.models import ArtworkStudyState
from scenelens.modules.artwork_study.presets import load_artwork_study_presets
from scenelens.modules.artwork_study.reviews import (
    ArtworkMasterStudyReview,
    ArtworkStudyContext,
    format_artwork_review_report,
)
from scenelens.modules.artwork_study.storage import ArtworkStudyStore
from scenelens.storage.project_store import utc_now
from scenelens.modules.visual_review.composition_guides import (
    COMPOSITION_GUIDES,
    composition_guide,
)
from scenelens.providers.contracts import (
    CancellationToken,
    DataDisclosurePreview,
    ProviderCapability,
    disclosure_preview,
)
from scenelens.providers.credentials import (
    MemoryCredentialStore,
    WindowsCredentialStore,
)
from scenelens.providers.execution import ProviderExecutionService
from scenelens.providers.factory import create_default_provider_registry
from scenelens.ui.analysis_widgets import AnalysisSummaryWidget
from scenelens.ui.image_canvas import (
    AnnotationOverlaySpec,
    GuideOverlaySpec,
    ImageCanvas,
)
from scenelens.ui.workers import FunctionWorker


LOGGER = logging.getLogger(__name__)
STUDY_SUFFIX = ".scenelens-study"


class ArtworkDisclosureDialog(QDialog):
    def __init__(self, preview: DataDisclosurePreview, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("确认发送作品研究数据")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "SceneLens 不会自动上传。继续后，一张图片副本、研究目标、"
            "已知背景、图片元数据和本地测量将发送给所选供应商。"
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        layout.addWidget(
            QLabel(
                f"供应商：{preview.provider_id}\n"
                f"模型：{preview.model_id}\n"
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
        privacy = QLabel(
            "商业保密图片是否允许上传由你的团队政策决定。发送副本默认移除"
            " EXIF、ICC、本地路径并限制分辨率。"
        )
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color: #E6B450;")
        layout.addWidget(privacy)
        if preview.provider_id == "google_gemini":
            repair = QLabel(
                "Gemini 若首次返回 JSON 损坏、截断或结构不完整，SceneLens"
                " 最多自动纠错一次；可能再次发送同一研究副本并增加费用。"
            )
            repair.setWordWrap(True)
            repair.setStyleSheet("color: #E6B450;")
            layout.addWidget(repair)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认并发送")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ArtworkStudyWindow(QMainWindow):
    workspace_home_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SceneLens — 作品研究")
        self.resize(1540, 920)
        self.setMinimumSize(1050, 680)

        self._store: ArtworkStudyStore | None = None
        self._state: ArtworkStudyState | None = None
        self._loaded: LoadedImage | None = None
        self._measurements: ImageMeasurements | None = None
        self._local_analysis: ArtworkLocalAnalysis | None = None
        self._active_mask_index: int | None = None
        self._generation: dict[str, int] = {
            "load": 0,
            "render": 0,
            "analysis": 0,
            "ai": 0,
            "mask": 0,
        }
        self._callbacks: dict[
            tuple[str, int], Callable[[object], None]
        ] = {}
        self._workers: set[FunctionWorker] = set()
        self._dirty = False
        self._restoring = False
        self._ai_cancellation: CancellationToken | None = None

        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(
            min(4, max(2, QThread.idealThreadCount()))
        )
        self._provider_registry = create_default_provider_registry()
        self._reviewer = ArtworkMasterStudyReview()
        self._execution = ProviderExecutionService()
        self._presets = load_artwork_study_presets()
        try:
            self._credential_store = WindowsCredentialStore()
        except OSError:
            self._credential_store = MemoryCredentialStore()

        self._build_actions()
        self._build_toolbar()
        self._build_central_ui()
        self._build_study_dock()
        self._build_status_bar()
        self._connect_signals()

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(700)
        self._autosave_timer.timeout.connect(self._save_state)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(120)
        self._render_timer.timeout.connect(self._render_current_view)
        self.statusBar().showMessage("新建或打开作品研究，然后导入一张作品。")

    def _build_actions(self) -> None:
        self.home_action = QAction("工作台首页", self)
        self.home_action.triggered.connect(
            lambda _checked=False: self.workspace_home_requested.emit()
        )
        self.new_action = QAction("新建作品研究…", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self._new_study)
        self.open_action = QAction("打开作品研究…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._open_study)
        self.save_action = QAction("保存", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(lambda: self._save_state(force=True))
        self.import_action = QAction("导入作品…", self)
        self.import_action.triggered.connect(self._choose_image)
        self.export_action = QAction("导出研究 JSON…", self)
        self.export_action.triggered.connect(self._export_review)

        file_menu = self.menuBar().addMenu("文件")
        for action in (
            self.home_action,
            self.new_action,
            self.open_action,
            self.save_action,
            self.import_action,
            self.export_action,
        ):
            file_menu.addAction(action)
        escape = QAction("退出遮罩或标注", self)
        escape.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        escape.triggered.connect(self._escape_tool)
        self.addAction(escape)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("作品研究工具", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction(self.home_action)
        toolbar.addSeparator()
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.import_action)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("观察："))
        self.mode_combo = QComboBox()
        for label, value in (
            ("原图", "original"),
            ("灰度", "grayscale"),
            ("三阶明度", "three_value"),
            ("五阶明度", "five_value"),
            ("曝光伪色（非真实 EV）", "exposure_false_colour"),
            ("高光 / 暗部溢出", "clipping_warning"),
            ("可调剪影", "silhouette"),
            ("缩略图观察", "thumbnail_observation"),
            ("明度模糊", "luminance_blur"),
            ("灯光明度代理图（非灰模）", "lighting_luminance_proxy"),
        ):
            self.mode_combo.addItem(label, value)
        toolbar.addWidget(self.mode_combo)
        toolbar.addWidget(QLabel("模糊："))
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setRange(0, 200)
        self.blur_slider.setFixedWidth(130)
        toolbar.addWidget(self.blur_slider)
        self.blur_label = QLabel("0.0")
        self.blur_label.setMinimumWidth(32)
        toolbar.addWidget(self.blur_label)
        toolbar.addWidget(QLabel("剪影："))
        self.silhouette_slider = QSlider(Qt.Orientation.Horizontal)
        self.silhouette_slider.setRange(5, 95)
        self.silhouette_slider.setValue(45)
        self.silhouette_slider.setFixedWidth(95)
        toolbar.addWidget(self.silhouette_slider)
        self.silhouette_label = QLabel("0.45")
        toolbar.addWidget(self.silhouette_label)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("构图辅助："))
        self.guide_combo = QComboBox()
        self.guide_combo.addItem("关闭", "none")
        for guide in COMPOSITION_GUIDES.values():
            self.guide_combo.addItem(guide.display_name, guide.guide_id)
        self.guide_combo.setToolTip(
            "仅用于人工观察，不代表软件自动判断作品采用了该构图。"
        )
        toolbar.addWidget(self.guide_combo)
        reset = QPushButton("重置视图")
        reset.clicked.connect(lambda: self.canvas.reset_view())
        toolbar.addWidget(reset)

    def _build_central_ui(self) -> None:
        self.canvas = ImageCanvas(
            "拖入一张作品\nPNG / JPG / JPEG / WebP"
        )
        self.tabs = QTabWidget()

        local_scroll = QScrollArea()
        local_scroll.setWidgetResizable(True)
        local_body = QWidget()
        local_layout = QVBoxLayout(local_body)
        self.summary_widget = AnalysisSummaryWidget("尚未导入作品")
        local_layout.addWidget(self.summary_widget)
        local_group = QGroupBox("形式证据与空间代理")
        local_group_layout = QVBoxLayout(local_group)
        self.local_summary = QPlainTextEdit()
        self.local_summary.setReadOnly(True)
        self.local_summary.setMinimumHeight(180)
        local_group_layout.addWidget(self.local_summary)
        self.spatial_tree = QTreeWidget()
        self.spatial_tree.setHeaderLabels(
            ["九宫格", "明度", "局部反差", "边缘", "彩度", "注意力代理"]
        )
        self.spatial_tree.setRootIsDecorated(False)
        self.spatial_tree.setMinimumHeight(230)
        local_group_layout.addWidget(self.spatial_tree)
        local_layout.addWidget(local_group)
        local_layout.addStretch(1)
        local_scroll.setWidget(local_body)
        self.tabs.addTab(local_scroll, "本地证据")

        self._build_ai_tab()

        notes = QWidget()
        notes_layout = QVBoxLayout(notes)
        notes_notice = QLabel(
            "记录你自己的判断、疑问和可迁移规律。AI 内容不会覆盖个人笔记。"
        )
        notes_notice.setWordWrap(True)
        notes_layout.addWidget(notes_notice)
        self.notes_edit = QPlainTextEdit()
        notes_layout.addWidget(self.notes_edit)
        self.tabs.addTab(notes, "学习笔记")

        report = QWidget()
        report_layout = QVBoxLayout(report)
        self.report_text = QPlainTextEdit()
        self.report_text.setReadOnly(True)
        report_layout.addWidget(self.report_text)
        export_button = QPushButton("导出研究 JSON")
        export_button.clicked.connect(self._export_review)
        report_layout.addWidget(export_button)
        self.tabs.addTab(report, "综合报告")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([900, 540])
        self.setCentralWidget(splitter)

    def _build_ai_tab(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        provider_group = QGroupBox("CG 主美作品深度研究")
        form = QFormLayout(provider_group)
        self.provider_combo = QComboBox()
        for provider in self._provider_registry.for_capability(
            ProviderCapability.VISION_REVIEW
        ):
            manifest = provider.manifest
            self.provider_combo.addItem(
                manifest.display_name, manifest.provider_id
            )
        form.addRow("供应商", self.provider_combo)
        self.model_edit = QLineEdit()
        form.addRow("模型 ID", self.model_edit)
        credential_row = QWidget()
        credential_layout = QHBoxLayout(credential_row)
        credential_layout.setContentsMargins(0, 0, 0, 0)
        self.credential_edit = QLineEdit()
        self.credential_edit.setEchoMode(QLineEdit.EchoMode.Password)
        credential_layout.addWidget(self.credential_edit, 1)
        self.save_credential_button = QPushButton("存入系统凭据")
        credential_layout.addWidget(self.save_credential_button)
        form.addRow("API Key", credential_row)
        self.maximum_side_combo = QComboBox()
        self.maximum_side_combo.addItem("最长边 1280 px", 1280)
        self.maximum_side_combo.addItem("最长边 2048 px", 2048)
        self.maximum_side_combo.addItem("最长边 4096 px", 4096)
        self.maximum_side_combo.addItem("原始尺寸", None)
        self.maximum_side_combo.setCurrentIndex(1)
        form.addRow("发送分辨率", self.maximum_side_combo)
        self.remove_metadata = QCheckBox("移除 EXIF、ICC、本地路径等元数据")
        self.remove_metadata.setChecked(True)
        form.addRow("", self.remove_metadata)
        layout.addWidget(provider_group)
        button_row = QHBoxLayout()
        self.run_ai_button = QPushButton("查看发送清单并开始深度研究")
        self.cancel_ai_button = QPushButton("取消")
        self.cancel_ai_button.setEnabled(False)
        button_row.addWidget(self.run_ai_button)
        button_row.addWidget(self.cancel_ai_button)
        layout.addLayout(button_row)
        self.ai_status = QLabel(
            "离线 Mock 只验证结构和界面，不执行本地视觉模型推理。"
        )
        self.ai_status.setWordWrap(True)
        layout.addWidget(self.ai_status)
        self.ai_dimension_tree = QTreeWidget()
        self.ai_dimension_tree.setHeaderLabels(
            ["研究维度", "评价状态", "证据摘要", "可信度"]
        )
        self.ai_dimension_tree.setRootIsDecorated(False)
        self.ai_dimension_tree.setMinimumHeight(250)
        layout.addWidget(self.ai_dimension_tree)
        self.ai_detail = QPlainTextEdit()
        self.ai_detail.setReadOnly(True)
        self.ai_detail.setMinimumHeight(260)
        layout.addWidget(self.ai_detail)
        self.causal_list = QListWidget()
        self.causal_list.setMinimumHeight(150)
        layout.addWidget(QLabel("跨维度因果链"))
        layout.addWidget(self.causal_list)
        scroll.setWidget(body)
        self.tabs.addTab(scroll, "专家拆解")

    def _build_study_dock(self) -> None:
        dock = QDockWidget("研究设置", self)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        dock.setMinimumWidth(280)
        body = QWidget()
        layout = QVBoxLayout(body)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        form.addRow("研究标题", self.title_edit)
        self.work_type_combo = QComboBox()
        self.work_type_combo.setEditable(True)
        for item in self._presets["work_types"]:
            self.work_type_combo.addItem(item["label"], item["id"])
        form.addRow("作品类型", self.work_type_combo)
        layout.addLayout(form)
        layout.addWidget(QLabel("本次想研究什么"))
        self.goal_edit = QPlainTextEdit()
        self.goal_edit.setPlaceholderText(
            "例如：重点理解它如何用雾、明度与建筑剪影组织空间。"
        )
        self.goal_edit.setMaximumHeight(130)
        layout.addWidget(self.goal_edit)
        layout.addWidget(QLabel("已知背景（可留空）"))
        self.context_edit = QPlainTextEdit()
        self.context_edit.setPlaceholderText(
            "作者、项目、用途等；无法确认的内容不要当作事实填写。"
        )
        self.context_edit.setMaximumHeight(130)
        layout.addWidget(self.context_edit)
        question_group = QGroupBox("研究方式")
        question_layout = QVBoxLayout(question_group)
        for question in self._presets["study_prompts"]:
            label = QLabel(f"• {question}")
            label.setWordWrap(True)
            question_layout.addWidget(label)
        layout.addWidget(question_group)
        layout.addStretch(1)
        dock.setWidget(body)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_status_bar(self) -> None:
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(150)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

    def _connect_signals(self) -> None:
        self.canvas.file_dropped.connect(self._import_image)
        self.canvas.view_state_changed.connect(self._view_changed)
        self.mode_combo.currentIndexChanged.connect(self._display_changed)
        self.blur_slider.valueChanged.connect(self._blur_changed)
        self.silhouette_slider.valueChanged.connect(self._silhouette_changed)
        self.guide_combo.currentIndexChanged.connect(self._guide_changed)
        self.summary_widget.palette.colour_selected.connect(
            self._palette_selected
        )
        self.title_edit.textChanged.connect(self._mark_dirty)
        self.work_type_combo.currentTextChanged.connect(self._mark_dirty)
        self.goal_edit.textChanged.connect(self._mark_dirty)
        self.context_edit.textChanged.connect(self._mark_dirty)
        self.notes_edit.textChanged.connect(self._mark_dirty)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self.save_credential_button.clicked.connect(self._save_credential)
        self.run_ai_button.clicked.connect(self._start_ai_review)
        self.cancel_ai_button.clicked.connect(self._cancel_ai_review)
        self.ai_dimension_tree.currentItemChanged.connect(
            self._dimension_selected
        )
        self._provider_changed()

    def _new_study(self) -> None:
        parent = QFileDialog.getExistingDirectory(
            self, "选择作品研究保存位置"
        )
        if not parent:
            return
        title, accepted = QInputDialog.getText(
            self, "新建作品研究", "研究标题："
        )
        if not accepted or not title.strip():
            return
        safe = "".join(
            "_" if character in '<>:"/\\|?*' else character
            for character in title.strip()
        ).rstrip(" .")
        try:
            store = ArtworkStudyStore.create(
                Path(parent) / f"{safe}{STUDY_SUFFIX}",
                title.strip(),
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法新建作品研究", str(exc))
            return
        self._set_store(store)

    def _open_study(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择 .scenelens-study 目录"
        )
        if not folder:
            return
        try:
            self._set_store(ArtworkStudyStore.open(folder))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法打开作品研究", str(exc))

    def _set_store(self, store: ArtworkStudyStore) -> None:
        self._store = store
        self._state = store.state
        self._restoring = True
        try:
            state = store.state
            self.title_edit.setText(state.title)
            index = self.work_type_combo.findData(state.work_type)
            if index >= 0:
                self.work_type_combo.setCurrentIndex(index)
            else:
                self.work_type_combo.setEditText(state.work_type)
            self.goal_edit.setPlainText(state.study_goal)
            self.context_edit.setPlainText(state.known_context)
            self.notes_edit.setPlainText(state.personal_notes)
            self._set_combo_data(self.mode_combo, state.display_mode, "original")
            self.blur_slider.setValue(round(state.blur_sigma * 10))
            self.silhouette_slider.setValue(
                round(state.silhouette_threshold * 100)
            )
            self._set_combo_data(
                self.guide_combo, state.composition_guide, "none"
            )
        finally:
            self._restoring = False
        self._dirty = False
        self.setWindowTitle(f"SceneLens — 作品研究 — {store.state.title}")
        image_path = store.image_path()
        if image_path is None:
            self._clear_image()
        else:
            self._load_image(image_path, reset_view=False)
        if state.ai_review:
            self._show_ai_output(state.ai_review)

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入研究作品",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if path:
            self._import_image(path)

    def _import_image(self, path: str) -> None:
        if self._store is None:
            QMessageBox.information(
                self,
                "请先新建作品研究",
                "作品研究会保存原图副本、测量与笔记。请先新建或打开研究。",
            )
            return
        try:
            self._state = self._store.import_image(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法导入图片", str(exc))
            return
        image_path = self._store.image_path()
        if image_path is not None:
            self._load_image(image_path, reset_view=True)

    def _load_image(self, path: Path, *, reset_view: bool) -> None:
        self._generation["load"] += 1
        generation = self._generation["load"]

        def operation():
            loaded = load_image(path)
            measurements = measure_image(
                loaded.rgb,
                loaded.alpha,
                palette_colours=8,
            )
            analysis = analyze_artwork(loaded.rgb, measurements)
            return loaded, measurements, analysis, reset_view

        self.statusBar().showMessage("正在读取作品并建立本地证据…")
        self._submit("load", generation, operation, self._apply_loaded)

    def _apply_loaded(self, result: object) -> None:
        loaded, measurements, analysis, reset_view = result
        self._loaded = loaded
        self._measurements = measurements
        self._local_analysis = analysis
        self.canvas.set_image(
            numpy_to_qimage(loaded.rgb, loaded.alpha),
            reset_view=bool(reset_view),
        )
        if not reset_view and self._state is not None:
            self.canvas.apply_external_view_state(
                self._state.zoom_factor,
                self._state.center_x,
                self._state.center_y,
            )
        self.summary_widget.set_loaded_image(
            loaded,
            self._state.image_filename if self._state else None,
        )
        self.summary_widget.set_measurements(measurements)
        self.local_summary.setPlainText(format_local_analysis_summary(analysis))
        self._populate_spatial_tree(analysis)
        if self._state is not None:
            self._state = replace(
                self._state,
                local_analysis=analysis.to_dict(),
            )
            self._dirty = True
            self._save_state()
        self._update_report()
        self._guide_changed()
        self.statusBar().showMessage(
            "本地证据已完成；注意力代理不是自动构图或优劣判断。"
        )

    def _populate_spatial_tree(self, analysis: ArtworkLocalAnalysis) -> None:
        self.spatial_tree.clear()
        for item in analysis.spatial_cells:
            node = QTreeWidgetItem(
                [
                    f"{item.row + 1}-{item.column + 1}",
                    f"{item.mean_linear_luminance:.3f}",
                    f"{item.luminance_contrast:.3f}",
                    f"{item.edge_density:.3f}",
                    f"{item.mean_oklab_chroma:.3f}",
                    f"{item.attention_proxy:.2f}",
                ]
            )
            node.setToolTip(
                5,
                "反差 45% + 边缘 35% + Oklab 彩度 20%；"
                "不等同于眼动或语义焦点。",
            )
            self.spatial_tree.addTopLevelItem(node)
        self.spatial_tree.resizeColumnToContents(0)

    def _render_current_view(self) -> None:
        if self._loaded is None:
            return
        self._generation["render"] += 1
        generation = self._generation["render"]
        settings = RenderSettings(
            mode=str(self.mode_combo.currentData()),
            blur_sigma=self.blur_slider.value() / 10.0,
            silhouette_threshold=self.silhouette_slider.value() / 100.0,
        )
        if settings.mode == "original" and settings.blur_sigma == 0.0:
            self.canvas.set_image(
                numpy_to_qimage(self._loaded.rgb, self._loaded.alpha),
                reset_view=False,
            )
            return
        self._submit(
            "render",
            generation,
            lambda: render_image(self._loaded.rgb, settings),
            lambda result: self.canvas.set_image(
                numpy_to_qimage(result, self._loaded.alpha),
                reset_view=False,
            ),
        )

    def _palette_selected(self, index: int) -> None:
        if self._loaded is None or self._measurements is None:
            return
        if self._active_mask_index == index:
            self._escape_tool()
            return
        self._generation["mask"] += 1
        generation = self._generation["mask"]
        centres = [
            item.oklab for item in self._measurements.palette
        ]
        self._active_mask_index = index
        self.summary_widget.palette.set_selected_index(index)

        def operation():
            import numpy as np

            centre_array = np.asarray(centres, dtype=np.float64)
            mask = palette_membership_mask(
                self._loaded.rgb, centre_array, index
            )
            return render_palette_source_mask(self._loaded.rgb, mask)

        self._submit(
            "mask",
            generation,
            operation,
            lambda result: self.canvas.set_overlay(
                numpy_to_qimage(result, self._loaded.alpha)
            ),
        )

    def _start_ai_review(self) -> None:
        if (
            self._loaded is None
            or self._state is None
            or self._local_analysis is None
        ):
            QMessageBox.information(
                self, "尚无作品", "请先导入并完成一张作品的本地分析。"
            )
            return
        provider_id = str(self.provider_combo.currentData())
        manifest = self._provider_registry.manifest(provider_id)
        model_id = self.model_edit.text().strip() or None
        credential = self.credential_edit.text().strip()
        if provider_id != "mock" and not credential:
            QMessageBox.information(
                self, "缺少 API Key", "请输入 API Key 或从系统凭据读取。"
            )
            return
        image = prepare_provider_image(
            self._loaded,
            "artwork",
            ProviderImageExportOptions(
                remove_metadata=self.remove_metadata.isChecked(),
                maximum_side=self.maximum_side_combo.currentData(),
            ),
        )
        context = ArtworkStudyContext(
            study_id=self._state.study_id,
            title=self.title_edit.text().strip(),
            work_type=self._work_type_value(),
            study_goal=self.goal_edit.toPlainText().strip(),
            known_context=self.context_edit.toPlainText().strip(),
            image_metadata={
                "filename_hidden": True,
                "width": self._loaded.working_size[0],
                "height": self._loaded.working_size[1],
                "format": self._loaded.source_format,
                "icc_converted_to_srgb": self._loaded.icc_converted_to_srgb,
                "assumed_srgb": self._loaded.assumed_srgb,
                "image_sha256": self._state.image_sha256,
            },
            local_evidence=self._local_analysis.to_dict(),
        )
        request = self._reviewer.create_request(
            context,
            (image,),
            model_id=model_id,
            user_initiated=True,
            disclosure_confirmed=True,
        )
        preview = disclosure_preview(manifest, request)
        if ArtworkDisclosureDialog(preview, self).exec() != QDialog.DialogCode.Accepted:
            return
        self._generation["ai"] += 1
        generation = self._generation["ai"]
        cancellation = CancellationToken()
        self._ai_cancellation = cancellation
        self.run_ai_button.setEnabled(False)
        self.cancel_ai_button.setEnabled(True)
        self.ai_status.setText("正在后台执行作品深度研究…")

        def operation():
            provider = self._provider_registry.get(provider_id)
            response = self._execution.run_review(
                provider,
                request,
                credential,
                cancellation,
            )
            return {
                "provider_id": response.provider_id,
                "model_id": response.model_id,
                "output": self._reviewer.validate_output(response.output),
            }

        self._submit("ai", generation, operation, self._apply_ai_result)

    def _apply_ai_result(self, result: object) -> None:
        value = dict(result)
        output = dict(value["output"])
        if self._state is not None:
            self._state = replace(
                self._state,
                ai_review=output,
                ai_run={
                    "provider_id": value["provider_id"],
                    "model_id": value["model_id"],
                    "reviewer_id": self._reviewer.descriptor.reviewer_id,
                    "reviewer_version": self._reviewer.descriptor.version,
                    "image_sha256": self._state.image_sha256,
                    "completed_at": utc_now(),
                },
            )
            self._dirty = True
            self._save_state()
        self._show_ai_output(output)
        self.tabs.setCurrentIndex(1)
        self.ai_status.setText(
            f"完成：{value['provider_id']} / {value['model_id']}"
        )
        self._update_report()

    def _show_ai_output(self, output: Mapping[str, Any]) -> None:
        labels = {
            "composition": "构图组织",
            "visual_hierarchy": "视觉层级",
            "value_structure": "明度结构",
            "colour_design": "色彩设计",
            "lighting": "光影组织",
            "spatial_depth": "空间层次",
            "shape_language": "形状语言",
            "edge_detail_control": "边缘与细节控制",
            "material_surface": "材质与表面",
            "environment_storytelling": "环境叙事",
            "style_technique": "风格与技法",
            "emotional_impact": "情绪作用",
        }
        self.ai_dimension_tree.clear()
        for item in output.get("dimension_studies", []):
            evidence = "；".join(item.get("visual_evidence", [])[:2])
            node = QTreeWidgetItem(
                [
                    labels.get(str(item["dimension_id"]), str(item["dimension_id"])),
                    str(item["evaluation_status"]),
                    evidence,
                    f"{float(item['confidence']):.2f}",
                ]
            )
            node.setData(0, Qt.ItemDataRole.UserRole, dict(item))
            self.ai_dimension_tree.addTopLevelItem(node)
        self.causal_list.clear()
        for item in output.get("causal_chains", []):
            self.causal_list.addItem(
                f"{item['cause']} → {item['mechanism']} → {item['effect']}"
            )
        annotations = []
        for item in output.get("annotations", []):
            rect = item["normalized_rect"]
            annotations.append(
                AnnotationOverlaySpec(
                    annotation_id=str(item["annotation_id"]),
                    kind="light_area",
                    points=(
                        (float(rect["x"]), float(rect["y"])),
                        (
                            float(rect["x"]) + float(rect["width"]),
                            float(rect["y"]) + float(rect["height"]),
                        ),
                    ),
                    label=str(item["label"]),
                    colour="#FFD166",
                )
            )
        self.canvas.set_annotation_overlays(annotations)
        if self.ai_dimension_tree.topLevelItemCount():
            self.ai_dimension_tree.setCurrentItem(
                self.ai_dimension_tree.topLevelItem(0)
            )

    def _dimension_selected(
        self, current: QTreeWidgetItem | None, _previous=None
    ) -> None:
        if current is None:
            self.ai_detail.clear()
            return
        item = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(item, Mapping):
            return
        self.ai_detail.setPlainText(
            f"观察\n{item.get('observation', '')}\n\n"
            f"画面证据\n{'；'.join(item.get('visual_evidence', []))}\n\n"
            f"测量证据\n{'；'.join(item.get('measurement_evidence', [])) or '无'}\n\n"
            f"解释\n{item.get('interpretation', '')}\n\n"
            f"观看效果\n{item.get('effect_on_viewer', '')}\n\n"
            f"评价与取舍\n{item.get('evaluation', '')}\n\n"
            f"与其他维度的关系\n{'；'.join(item.get('relationships', []))}\n\n"
            f"可迁移学习点\n{'；'.join(item.get('learning_points', []))}\n\n"
            f"不确定性\n{item.get('uncertainty', '')}"
        )

    def _update_report(self) -> None:
        parts = []
        if self._local_analysis is not None:
            parts.append(format_local_analysis_summary(self._local_analysis))
        if self._state is not None and self._state.ai_review:
            parts.append(format_artwork_review_report(self._state.ai_review))
        if self.notes_edit.toPlainText().strip():
            parts.append("个人学习笔记\n" + self.notes_edit.toPlainText().strip())
        self.report_text.setPlainText("\n\n".join(parts))

    def _export_review(self) -> None:
        if self._store is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出作品研究",
            str(self._store.root / "exports" / "artwork_study.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        self._save_state(force=True)
        try:
            self._store.export_review_json(path)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
        else:
            self.statusBar().showMessage(f"已导出：{path}")

    def _save_state(self, force: bool = False) -> None:
        if self._store is None or self._state is None:
            return
        if not self._dirty and not force:
            return
        zoom, center_x, center_y = self.canvas.current_view_state()
        self._state = replace(
            self._state,
            title=self.title_edit.text().strip() or "未命名作品研究",
            work_type=self._work_type_value(),
            study_goal=self.goal_edit.toPlainText(),
            known_context=self.context_edit.toPlainText(),
            personal_notes=self.notes_edit.toPlainText(),
            display_mode=str(self.mode_combo.currentData()),
            blur_sigma=self.blur_slider.value() / 10.0,
            silhouette_threshold=self.silhouette_slider.value() / 100.0,
            composition_guide=str(self.guide_combo.currentData()),
            zoom_factor=zoom,
            center_x=center_x,
            center_y=center_y,
        )
        try:
            self._store.save(self._state)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "作品研究保存失败",
                f"{exc}\n原图不会受影响；内存中的修改仍保留。",
            )
            return
        self._state = self._store.state
        self._dirty = False
        self.setWindowTitle(f"SceneLens — 作品研究 — {self._state.title}")
        self.statusBar().showMessage("作品研究已保存")

    def _mark_dirty(self, *_args) -> None:
        if self._restoring or self._state is None:
            return
        self._dirty = True
        self._autosave_timer.start()
        self._update_report()

    def _view_changed(self, *_args) -> None:
        self._mark_dirty()

    def _display_changed(self, *_args) -> None:
        self.silhouette_slider.setEnabled(
            self.mode_combo.currentData() == "silhouette"
        )
        self._mark_dirty()
        self._render_timer.start()

    def _blur_changed(self, value: int) -> None:
        self.blur_label.setText(f"{value / 10.0:.1f}")
        self._mark_dirty()
        self._render_timer.start()

    def _silhouette_changed(self, value: int) -> None:
        self.silhouette_label.setText(f"{value / 100.0:.2f}")
        self._mark_dirty()
        if self.mode_combo.currentData() == "silhouette":
            self._render_timer.start()

    def _guide_changed(self, *_args) -> None:
        guide = composition_guide(str(self.guide_combo.currentData() or "none"))
        self.canvas.set_guide_overlay(
            None
            if guide is None
            else GuideOverlaySpec(
                guide_id=guide.guide_id,
                label=guide.display_name,
                lines=guide.lines,
            )
        )
        self._mark_dirty()

    def _provider_changed(self, *_args) -> None:
        provider_id = str(self.provider_combo.currentData() or "")
        if not provider_id:
            return
        manifest = self._provider_registry.manifest(provider_id)
        self.model_edit.setPlaceholderText(
            manifest.model_for(ProviderCapability.VISION_REVIEW)
        )
        try:
            credential = self._credential_store.get(
                manifest.credential_target
            )
        except OSError:
            credential = None
        self.credential_edit.setText(credential or "")

    def _save_credential(self) -> None:
        provider_id = str(self.provider_combo.currentData())
        manifest = self._provider_registry.manifest(provider_id)
        secret = self.credential_edit.text().strip()
        if not secret:
            QMessageBox.information(self, "没有 API Key", "请输入 API Key。")
            return
        try:
            self._credential_store.set(manifest.credential_target, secret)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "系统凭据保存失败", str(exc))
        else:
            self.statusBar().showMessage("API Key 已保存到 Windows 系统凭据")

    def _cancel_ai_review(self) -> None:
        if self._ai_cancellation is not None:
            self._ai_cancellation.cancel()
        self._generation["ai"] += 1
        self.ai_status.setText("AI 作品研究已取消。")
        self.run_ai_button.setEnabled(True)
        self.cancel_ai_button.setEnabled(False)

    def _escape_tool(self) -> None:
        if self._active_mask_index is not None:
            self._active_mask_index = None
            self._generation["mask"] += 1
            self.canvas.clear_overlay()
            self.summary_widget.palette.set_selected_index(None)
            self.statusBar().showMessage("已退出色板来源遮罩")
            return
        if self.canvas.annotation_overlay_count:
            self.canvas.clear_annotation_overlays()
            self.statusBar().showMessage("已临时隐藏 AI 画面标注")
            return
        if self.guide_combo.currentData() != "none":
            self._set_combo_data(self.guide_combo, "none", "none")

    def _clear_image(self) -> None:
        self._loaded = None
        self._measurements = None
        self._local_analysis = None
        self.canvas.clear_image()
        self.summary_widget.clear("尚未导入作品")
        self.local_summary.clear()
        self.spatial_tree.clear()
        self.ai_dimension_tree.clear()
        self.ai_detail.clear()
        self.causal_list.clear()
        self.report_text.clear()

    def _submit(
        self,
        kind: str,
        generation: int,
        operation: Callable[[], object],
        callback: Callable[[object], None],
    ) -> None:
        self._callbacks[(kind, generation)] = callback
        worker = FunctionWorker("artwork", kind, generation, operation)
        self._workers.add(worker)
        worker.signals.result.connect(self._worker_result)
        worker.signals.error.connect(self._worker_error)
        worker.signals.finished.connect(
            lambda *_args, value=worker: self._worker_finished(value)
        )
        self.progress.show()
        self._thread_pool.start(worker)

    def _worker_result(
        self, _role: str, kind: str, generation: int, result: object
    ) -> None:
        if generation != self._generation.get(kind):
            return
        callback = self._callbacks.pop((kind, generation), None)
        if callback is not None:
            callback(result)

    def _worker_error(
        self,
        _role: str,
        kind: str,
        generation: int,
        message: str,
        technical: str,
    ) -> None:
        LOGGER.error("Artwork study worker failed:\n%s", technical)
        if generation != self._generation.get(kind):
            return
        if kind == "ai":
            self.ai_status.setText("作品研究失败；可检查服务状态或稍后重试。")
            self.run_ai_button.setEnabled(True)
            self.cancel_ai_button.setEnabled(False)
            self._ai_cancellation = None
            QMessageBox.warning(self, "AI 作品研究失败", message)
        else:
            QMessageBox.warning(self, "处理失败", message)

    def _worker_finished(self, worker: FunctionWorker) -> None:
        self._callbacks.pop((worker.kind, worker.generation), None)
        self._workers.discard(worker)
        if not self._workers:
            self.progress.hide()
        self.run_ai_button.setEnabled(True)
        self.cancel_ai_button.setEnabled(False)

    def _work_type_value(self) -> str:
        index = self.work_type_combo.currentIndex()
        data = self.work_type_combo.itemData(index) if index >= 0 else None
        label = self.work_type_combo.itemText(index) if index >= 0 else ""
        current = self.work_type_combo.currentText().strip()
        return str(data) if data and current == label else current

    @staticmethod
    def _set_combo_data(
        combo: QComboBox, value: str, fallback: str
    ) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findData(fallback)
        combo.setCurrentIndex(max(0, index))

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_state(force=True)
        self._cancel_ai_review()
        self._execution.close()
        event.accept()
