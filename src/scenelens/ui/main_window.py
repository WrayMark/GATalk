from __future__ import annotations

import logging
from dataclasses import replace
from functools import partial
from pathlib import Path

from PySide6.QtCore import QThread, QThreadPool, QTimer, Qt
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

from scenelens.analysis.models import ImageMeasurements, RenderSettings
from scenelens.analysis.pipeline import render_image
from scenelens.core.analyzers import AnalyzerRequest
from scenelens.imaging.loader import LoadedImage, load_image
from scenelens.imaging.qt import numpy_to_qimage
from scenelens.modules.visual_review import MODULE_ID
from scenelens.modules.visual_review.analyzers import (
    BASIC_MEASUREMENTS_ANALYZER_ID,
)
from scenelens.modules.visual_review.registry import (
    create_visual_review_registry,
)
from scenelens.storage.errors import ProjectLockedError, StorageError
from scenelens.storage.models import (
    ArtBrief,
    CanvasState,
    ImageAssetRecord,
    VersionRecord,
    WorkspaceState,
)
from scenelens.storage.project_store import (
    ProjectStore,
    utc_now,
)
from scenelens.storage.recent_projects import RecentProjects
from scenelens.ui.analysis_widgets import AnalysisSummaryWidget
from scenelens.ui.image_canvas import ImageCanvas
from scenelens.ui.project_widgets import ArtBriefDialog, ProjectNavigator
from scenelens.ui.workers import FunctionWorker


LOGGER = logging.getLogger(__name__)
ROLE_LABELS = {"reference": "参考图", "current": "当前截图"}
INVALID_WINDOWS_NAME_CHARS = set('<>:"/\\|?*')


class ImagePane(QWidget):
    def __init__(self, title: str, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "padding: 6px 8px; font-weight: 600; background: #25282D;"
        )
        layout.addWidget(self.title_label)

        self.canvas = ImageCanvas(placeholder)
        layout.addWidget(self.canvas, 1)


class MainWindow(QMainWindow):
    def __init__(self, recent_projects: RecentProjects | None = None) -> None:
        super().__init__()
        self.setWindowTitle("SceneLens — M1B.0")
        self.resize(1550, 900)
        self.setMinimumSize(1050, 650)

        self._images: dict[str, LoadedImage] = {}
        self._asset_ids: dict[str, str | None] = {
            "reference": None,
            "current": None,
        }
        self._load_generation = {"reference": 0, "current": 0}
        self._render_generation = {"reference": 0, "current": 0}
        self._measure_generation = {"reference": 0, "current": 0}
        self._import_generation = {"reference": 0, "current": 0}
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

        self._thread_pool = QThreadPool(self)
        ideal = max(2, QThread.idealThreadCount())
        self._thread_pool.setMaxThreadCount(min(4, ideal))

        self._build_actions_and_menus()
        self._build_toolbar()
        self._build_central_ui()
        self._build_project_dock()
        self._build_status_bar()
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

        ab_action = QAction("切换 A/B", self)
        ab_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        ab_action.triggered.connect(self._toggle_ab)
        self.addAction(ab_action)

        self.statusBar().showMessage(
            "可先新建/打开项目，也可直接拖入图片继续使用 M0.5 工作台。"
        )

    def _build_actions_and_menus(self) -> None:
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
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addAction(self.save_project_action)
        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu("最近项目")

        self._view_menu = self.menuBar().addMenu("视图")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具", self)
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
        self.analysis_tabs.setMinimumWidth(300)
        self.analysis_widgets = {
            "reference": AnalysisSummaryWidget("尚未导入参考图"),
            "current": AnalysisSummaryWidget("尚未导入当前截图"),
        }
        self.analysis_tabs.addTab(self.analysis_widgets["reference"], "参考分析")
        self.analysis_tabs.addTab(self.analysis_widgets["current"], "截图分析")
        self.analysis_tabs.addTab(
            self._placeholder_panel("M1B 实现证据化对比后在此显示。"),
            "对比分析",
        )
        self.analysis_tabs.addTab(
            self._placeholder_panel("修改任务将在后续纵向功能中实现。"),
            "审阅任务",
        )

        self.root_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.root_splitter.addWidget(self.image_splitter)
        self.root_splitter.addWidget(self.analysis_tabs)
        self.root_splitter.setSizes([1180, 370])
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

    @staticmethod
    def _placeholder_panel(text: str) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #9AA0A6; padding: 24px;")
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
            "新建 SceneLens 项目",
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
            "打开 SceneLens 项目",
            "",
            "SceneLens 项目 (project.json);;JSON 文件 (*.json)",
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
        self._invalidate_image_jobs()
        self._clear_role("reference")
        self._clear_role("current")
        self.project_navigator.clear_project()
        self.save_project_action.setEnabled(False)
        self.reference_button.setEnabled(True)
        self.current_button.setEnabled(True)
        self.setWindowTitle("SceneLens — M1B")
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
        self.setWindowTitle(f"SceneLens — {store.manifest.name}{suffix}")
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
            self.blur_slider.setValue(
                max(0, min(200, int(round(state.blur_sigma * 10.0))))
            )
            self.sync_checkbox.setChecked(state.sync_views)
            self._comparison_mode_changed(self.comparison_combo.currentIndex())
            self._clear_role("reference")
            self._clear_role("current")
            self._refresh_project_navigator()
            self._load_active_project_images()
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
        dialog = ArtBriefDialog(store.get_art_brief(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.save_art_brief(dialog.art_brief())

    def save_art_brief(self, brief: ArtBrief) -> bool:
        store = self._project_store
        if store is None:
            return False
        try:
            store.save_art_brief(brief)
            self.statusBar().showMessage("Art Brief 已保存")
            return True
        except StorageError as exc:
            self._show_storage_error("Art Brief 保存失败", exc)
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
        self._clear_role("reference")
        self._clear_role("current")
        self._refresh_project_navigator()
        self._load_active_project_images()
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
        self._clear_role("reference")
        self._clear_role("current")
        self._refresh_project_navigator()
        self._load_active_project_images()
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
            if canvas_state is not None:
                self._canvas_for(role).apply_external_view_state(
                    canvas_state.zoom_factor,
                    canvas_state.center_x,
                    canvas_state.center_y,
                )
            cached = self._load_cached_measurements(asset_id)
            if cached is not None:
                self.analysis_widgets[role].set_measurements(cached)
                self.statusBar().showMessage(
                    f"{ROLE_LABELS[role]}已恢复历史分析结果"
                )
            else:
                self._start_measurement(role)
            self._start_render(role)
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
                self.statusBar().showMessage(f"{ROLE_LABELS[role]}分析完成")
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
        if kind in {"import_reference", "import_version"}:
            expected = self._import_generation[role]
        else:
            expected = {
                "load": self._load_generation,
                "measure": self._measure_generation,
                "render": self._render_generation,
            }[kind][role]
        if generation != expected:
            return
        LOGGER.error("%s %s failed:\n%s", role, kind, details)
        title = {
            "load": "图片读取失败",
            "measure": "图片分析失败",
            "render": "显示处理失败",
            "import_reference": "参考图导入失败",
            "import_version": "截图版本导入失败",
        }.get(kind, "SceneLens 操作失败")
        QMessageBox.warning(
            self,
            title,
            f"{ROLE_LABELS[role]}处理失败：\n{message}",
        )
        self.statusBar().showMessage(f"{ROLE_LABELS[role]}处理失败")

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

    def _current_render_settings(self) -> RenderSettings:
        return RenderSettings(
            mode=str(self.mode_combo.currentData()),
            blur_sigma=self.blur_slider.value() / 10.0,
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
        self._asset_ids[role] = None
        self._canvas_for(role).clear_image()
        self.analysis_widgets[role].clear(
            "尚未导入参考图"
            if role == "reference"
            else "尚未导入当前截图"
        )

    def _invalidate_image_jobs(self) -> None:
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
                if self._project_store is not None:
                    self._project_store.close()
                event.accept()
            else:
                event.ignore()
        elif choice == QMessageBox.StandardButton.Discard:
            if self._project_store is not None:
                self._project_store.close()
            event.accept()
        else:
            event.ignore()
