from __future__ import annotations

import logging
from functools import partial
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, QThreadPool
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
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
from scenelens.analysis.pipeline import measure_image, render_image
from scenelens.imaging.loader import LoadedImage, load_image
from scenelens.imaging.qt import numpy_to_qimage
from scenelens.ui.analysis_widgets import AnalysisSummaryWidget
from scenelens.ui.image_canvas import ImageCanvas
from scenelens.ui.workers import FunctionWorker


LOGGER = logging.getLogger(__name__)
ROLE_LABELS = {"reference": "参考图", "current": "当前截图"}


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
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SceneLens — M0.5 技术验证")
        self.resize(1500, 900)
        self.setMinimumSize(1000, 650)

        self._images: dict[str, LoadedImage] = {}
        self._load_generation = {"reference": 0, "current": 0}
        self._render_generation = {"reference": 0, "current": 0}
        self._measure_generation = {"reference": 0, "current": 0}
        self._active_jobs = 0
        self._ab_role = "reference"

        self._thread_pool = QThreadPool(self)
        ideal = max(2, QThread.idealThreadCount())
        self._thread_pool.setMaxThreadCount(min(4, ideal))

        self._build_toolbar()
        self._build_central_ui()
        self._build_status_bar()
        self._connect_canvas_sync()

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(140)
        self._render_timer.timeout.connect(self._refresh_rendered_images)

        ab_action = QAction("切换 A/B", self)
        ab_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        ab_action.triggered.connect(self._toggle_ab)
        self.addAction(ab_action)

        self.statusBar().showMessage(
            "将图片拖到对应画布，或使用左上角导入按钮。原图不会被修改。"
        )

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("M0.5 工具", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        reference_button = QPushButton("导入参考图")
        reference_button.clicked.connect(partial(self._choose_image, "reference"))
        toolbar.addWidget(reference_button)

        current_button = QPushButton("导入当前截图")
        current_button.clicked.connect(partial(self._choose_image, "current"))
        toolbar.addWidget(current_button)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("显示："))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("原图", "original")
        self.mode_combo.addItem("灰度", "grayscale")
        self.mode_combo.addItem("三阶明度", "three_value")
        self.mode_combo.addItem("五阶明度", "five_value")
        self.mode_combo.currentIndexChanged.connect(self._schedule_render)
        toolbar.addWidget(self.mode_combo)

        toolbar.addWidget(QLabel("  模糊："))
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setRange(0, 200)
        self.blur_slider.setValue(0)
        self.blur_slider.setFixedWidth(150)
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
            partial(self._load_path, "reference")
        )
        self.current_pane.canvas.file_dropped.connect(
            partial(self._load_path, "current")
        )

        self.image_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.image_splitter.addWidget(self.reference_pane)
        self.image_splitter.addWidget(self.current_pane)
        self.image_splitter.setSizes([700, 700])
        self.image_splitter.setChildrenCollapsible(False)

        self.analysis_tabs = QTabWidget()
        self.analysis_tabs.setMinimumWidth(310)
        self.analysis_tabs.setMaximumWidth(410)
        self.analysis_widgets = {
            "reference": AnalysisSummaryWidget("尚未导入参考图"),
            "current": AnalysisSummaryWidget("尚未导入当前截图"),
        }
        self.analysis_tabs.addTab(self.analysis_widgets["reference"], "参考图分析")
        self.analysis_tabs.addTab(self.analysis_widgets["current"], "截图分析")

        root_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_splitter.addWidget(self.image_splitter)
        root_splitter.addWidget(self.analysis_tabs)
        root_splitter.setSizes([1160, 340])
        root_splitter.setStretchFactor(0, 1)
        root_splitter.setStretchFactor(1, 0)
        root_splitter.setChildrenCollapsible(False)
        self.setCentralWidget(root_splitter)

    def _build_status_bar(self) -> None:
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(130)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)

    def _connect_canvas_sync(self) -> None:
        self.reference_pane.canvas.view_state_changed.connect(
            partial(self._sync_from, "reference")
        )
        self.current_pane.canvas.view_state_changed.connect(
            partial(self._sync_from, "current")
        )

    def _choose_image(self, role: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"选择{ROLE_LABELS[role]}",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if path:
            self._load_path(role, path)

    def _load_path(self, role: str, path: str) -> None:
        self._load_generation[role] += 1
        generation = self._load_generation[role]
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
        if kind == "load":
            if generation != self._load_generation[role]:
                return
            loaded = result
            if not isinstance(loaded, LoadedImage):
                return
            self._images[role] = loaded
            self.analysis_widgets[role].set_loaded_image(loaded)
            self._canvas_for(role).set_image(
                numpy_to_qimage(loaded.rgb, loaded.alpha),
                reset_view=True,
            )
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
        self._measure_generation[role] += 1
        generation = self._measure_generation[role]
        self._start_worker(
            role,
            "measure",
            generation,
            lambda: measure_image(loaded.rgb, loaded.alpha, palette_colours=8),
        )

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

    def _schedule_render(self, _value=None) -> None:
        self._render_timer.start()

    def _refresh_rendered_images(self) -> None:
        for role in tuple(self._images):
            self._start_render(role)

    def _blur_changed(self, value: int) -> None:
        self.blur_label.setText(f"{value / 10.0:.1f}")
        self._schedule_render()

    def _comparison_mode_changed(self, _index: int) -> None:
        is_ab = self.comparison_combo.currentData() == "ab"
        self.ab_button.setEnabled(is_ab)
        if not is_ab:
            self.reference_pane.show()
            self.current_pane.show()
            return
        self._apply_ab_visibility()

    def _toggle_ab(self) -> None:
        if self.comparison_combo.currentData() != "ab":
            self.comparison_combo.setCurrentIndex(
                self.comparison_combo.findData("ab")
            )
        self._ab_role = "current" if self._ab_role == "reference" else "reference"
        self._apply_ab_visibility()

    def _apply_ab_visibility(self) -> None:
        self.reference_pane.setVisible(self._ab_role == "reference")
        self.current_pane.setVisible(self._ab_role == "current")
        self.ab_button.setText(
            f"当前：{ROLE_LABELS[self._ab_role]}（Space 切换）"
        )
        if self._ab_role == "reference":
            self.analysis_tabs.setCurrentIndex(0)
        else:
            self.analysis_tabs.setCurrentIndex(1)

    def _sync_from(
        self,
        source_role: str,
        zoom_factor: float,
        center_x: float,
        center_y: float,
    ) -> None:
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

    def _canvas_for(self, role: str) -> ImageCanvas:
        if role == "reference":
            return self.reference_pane.canvas
        return self.current_pane.canvas
