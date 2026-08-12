from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
import uuid

from PySide6.QtCore import QThreadPool, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
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
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from scenelens.analysis.artwork_study import analyze_artwork
from scenelens.analysis.pipeline import measure_image
from scenelens.imaging.loader import load_image
from scenelens.imaging.provider_export import (
    ProviderImageExportOptions,
    prepare_provider_image,
)
from scenelens.modules.comparative_study.analysis import (
    build_local_comparison,
    format_local_comparison,
)
from scenelens.modules.comparative_study.models import STUDY_AXES
from scenelens.modules.comparative_study.reviews import (
    ComparativeArtworkReview,
    ComparativeStudyContext,
    format_comparative_review,
)
from scenelens.modules.comparative_study.storage import ComparativeStudyStore
from scenelens.providers.contracts import CancellationToken, ProviderCapability
from scenelens.providers.credentials import WindowsCredentialStore
from scenelens.providers.execution import ProviderExecutionService
from scenelens.providers.factory import create_default_provider_registry
from scenelens.storage.project_store import utc_now
from scenelens.storage.workspace_catalog import WorkspaceCatalogStore
from scenelens.ui.workers import FunctionWorker


class ComparativeStudyWindow(QMainWindow):
    workspace_home_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GATalk — 作品研究集合与对照研究")
        self.resize(1580, 920)
        self.setMinimumSize(1120, 700)
        self._store: ComparativeStudyStore | None = None
        self._generation = 0
        self._thread_pool = QThreadPool.globalInstance()
        self._execution = ProviderExecutionService(max_workers=2)
        self._providers = create_default_provider_registry()
        self._reviewer = ComparativeArtworkReview()
        self._credential_store = WindowsCredentialStore()
        self._build_ui()
        self._provider_changed()

    def _build_ui(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        new_action = QAction("新建对照研究…", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._new_study)
        file_menu.addAction(new_action)
        open_action = QAction("打开对照研究…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_study)
        file_menu.addAction(open_action)
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_state)
        file_menu.addAction(save_action)

        root = QSplitter(Qt.Orientation.Horizontal)
        root.setChildrenCollapsible(False)
        root.addWidget(self._build_research_panel())
        root.addWidget(self._build_visual_panel())
        root.addWidget(self._build_analysis_panel())
        root.setSizes([310, 820, 470])
        self.setCentralWidget(root)
        self.statusBar().showMessage("新建研究后导入 2 至 6 件作品。原始图片保持只读。")

    def _build_research_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 6, 12)
        heading = QLabel("研究设置")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.question_edit = QPlainTextEdit()
        self.question_edit.setPlaceholderText(
            "例如：两件作品如何用不同的明度与空间组织建立同类情绪？"
        )
        self.question_edit.setMaximumHeight(100)
        self.context_edit = QPlainTextEdit()
        self.context_edit.setPlaceholderText("作者、项目、媒介等已核实背景；未知内容请留空。")
        self.context_edit.setMaximumHeight(90)
        form.addRow("研究标题", self.title_edit)
        form.addRow("核心问题", self.question_edit)
        form.addRow("已知背景", self.context_edit)
        layout.addLayout(form)
        axis_heading = QLabel("比较维度")
        axis_heading.setObjectName("sectionTitle")
        layout.addWidget(axis_heading)
        self.axis_list = QListWidget()
        self.axis_list.setMaximumHeight(235)
        for axis in STUDY_AXES:
            row = QListWidgetItem(axis)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Checked)
            self.axis_list.addItem(row)
        layout.addWidget(self.axis_list)
        works_header = QHBoxLayout()
        works_header.addWidget(QLabel("研究作品（勾选 2–6 件）"))
        works_header.addStretch(1)
        add = QPushButton("导入…")
        add.clicked.connect(self._import_images)
        works_header.addWidget(add)
        layout.addLayout(works_header)
        self.item_list = QListWidget()
        self.item_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.item_list.itemChanged.connect(self._active_selection_changed)
        self.item_list.currentItemChanged.connect(self._highlight_work)
        layout.addWidget(self.item_list, 1)
        row = QHBoxLayout()
        baseline = QPushButton("设为基准")
        baseline.setToolTip("将当前作品作为本地差异表和专家对照的第一基准。")
        baseline.clicked.connect(self._set_current_as_baseline)
        row.addWidget(baseline)
        remove = QPushButton("移除所选")
        remove.clicked.connect(self._remove_selected)
        row.addWidget(remove)
        self.analyze_button = QPushButton("运行本地对照")
        self.analyze_button.setProperty("primary", True)
        self.analyze_button.clicked.connect(self._start_local_analysis)
        row.addWidget(self.analyze_button)
        layout.addLayout(row)
        return panel

    def _build_visual_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.visual_body = QWidget()
        self.visual_grid = QGridLayout(self.visual_body)
        self.visual_grid.setContentsMargins(12, 12, 12, 12)
        self.visual_grid.setSpacing(12)
        placeholder = QLabel("导入作品后，这里会以同等权重并置显示。")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setProperty("role", "muted")
        self.visual_grid.addWidget(placeholder, 0, 0)
        scroll.setWidget(self.visual_body)
        return scroll

    def _build_analysis_panel(self) -> QWidget:
        tabs = QTabWidget()
        self.local_output = QPlainTextEdit()
        self.local_output.setReadOnly(True)
        self.local_output.setPlaceholderText(
            "本地对照只呈现可复核的明度、色彩和细节统计，不自动判断优劣。"
        )
        tabs.addTab(self.local_output, "本地证据")

        ai_scroll = QScrollArea()
        ai_scroll.setWidgetResizable(True)
        ai_body = QWidget()
        ai_layout = QVBoxLayout(ai_body)
        ai_layout.setContentsMargins(12, 12, 12, 12)
        provider_form = QFormLayout()
        self.provider_combo = QComboBox()
        for provider in self._providers.for_capability(
            ProviderCapability.VISION_REVIEW
        ):
            self.provider_combo.addItem(
                provider.manifest.display_name,
                provider.manifest.provider_id,
            )
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self.model_edit = QLineEdit()
        self.credential_edit = QLineEdit()
        self.credential_edit.setEchoMode(QLineEdit.EchoMode.Password)
        provider_form.addRow("AI 供应商", self.provider_combo)
        provider_form.addRow("模型 ID", self.model_edit)
        provider_form.addRow("API Key", self.credential_edit)
        ai_layout.addLayout(provider_form)
        key_row = QHBoxLayout()
        key_row.addStretch(1)
        save_key = QPushButton("存入系统凭据")
        save_key.clicked.connect(self._save_credential)
        key_row.addWidget(save_key)
        ai_layout.addLayout(key_row)
        self.run_ai_button = QPushButton("查看发送清单并开始对照研究")
        self.run_ai_button.setProperty("primary", True)
        self.run_ai_button.clicked.connect(self._start_ai_review)
        ai_layout.addWidget(self.run_ai_button)
        self.ai_status = QLabel("AI 研究只在用户确认发送后执行。")
        self.ai_status.setWordWrap(True)
        self.ai_status.setProperty("role", "muted")
        ai_layout.addWidget(self.ai_status)
        history_row = QHBoxLayout()
        history_row.addWidget(QLabel("研究记录"))
        self.ai_history_combo = QComboBox()
        self.ai_history_combo.setToolTip("默认显示最新一次完成的专家对照。")
        history_row.addWidget(self.ai_history_combo, 1)
        self.delete_ai_history_button = QPushButton("删除记录")
        self.delete_ai_history_button.setEnabled(False)
        history_row.addWidget(self.delete_ai_history_button)
        ai_layout.addLayout(history_row)
        self.ai_history_combo.currentIndexChanged.connect(
            self._show_selected_ai_history
        )
        self.delete_ai_history_button.clicked.connect(
            self._delete_selected_ai_history
        )
        self.ai_output = QPlainTextEdit()
        self.ai_output.setReadOnly(True)
        self.ai_output.setMinimumHeight(420)
        ai_layout.addWidget(self.ai_output, 1)
        ai_scroll.setWidget(ai_body)
        tabs.addTab(ai_scroll, "专家对照")

        notes = QWidget()
        notes_layout = QVBoxLayout(notes)
        notes_layout.addWidget(QLabel("综合笔记"))
        self.synthesis_edit = QPlainTextEdit()
        self.synthesis_edit.setPlaceholderText("归纳共同策略、关键差异与自己的判断。")
        notes_layout.addWidget(self.synthesis_edit)
        notes_layout.addWidget(QLabel("可迁移规律"))
        self.principles_edit = QPlainTextEdit()
        self.principles_edit.setPlaceholderText("写明适用条件，不复制作品表面造型。")
        notes_layout.addWidget(self.principles_edit)
        notes_layout.addWidget(QLabel("研究边界与待核实内容"))
        self.limitations_edit = QPlainTextEdit()
        notes_layout.addWidget(self.limitations_edit)
        save_notes = QPushButton("保存研究笔记")
        save_notes.clicked.connect(self._save_state)
        notes_layout.addWidget(save_notes)
        tabs.addTab(notes, "研究结论")
        return tabs

    def _new_study(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择新的对照研究目录")
        if not path:
            return
        title, accepted = QInputDialog.getText(self, "新建对照研究", "研究标题")
        if not accepted:
            return
        try:
            self._store = ComparativeStudyStore.create(path, title)
        except Exception as exc:
            QMessageBox.warning(self, "无法新建对照研究", str(exc))
            return
        self._load_state()

    def _open_study(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "打开对照研究")
        if not path:
            return
        try:
            self._store = ComparativeStudyStore.open(path)
        except Exception as exc:
            QMessageBox.warning(self, "无法打开对照研究", str(exc))
            return
        self._load_state()

    def open_path(self, path: str | Path) -> bool:
        try:
            self._store = ComparativeStudyStore.open(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法打开对照研究", str(exc))
            return False
        self._load_state()
        return True

    def receive_knowledge_handoff(self, handoff: object) -> None:
        value = dict(handoff) if isinstance(handoff, dict) else {}
        path = QFileDialog.getExistingDirectory(self, "选择新的对照研究目录")
        if not path:
            return
        title, accepted = QInputDialog.getText(
            self, "建立对照研究", "研究标题", text="资料库对照研究"
        )
        if not accepted:
            return
        try:
            self._store = ComparativeStudyStore.create(path, title)
            for item in value.get("items", ()):
                self._store.import_image(
                    item["path"],
                    title=item.get("title", ""),
                    source_kind=item.get("source_kind", "knowledge_library"),
                    source_reference=item.get("source_reference", ""),
                )
            state = replace(
                self._store.state,
                knowledge_library_path=str(value.get("library_path", "")),
            )
            self._store.save(state)
        except Exception as exc:
            QMessageBox.warning(self, "无法建立对照研究", str(exc))
            return
        self._load_state()

    def _load_state(self) -> None:
        if self._store is None:
            return
        try:
            WorkspaceCatalogStore().remember(self._store.root)
        except (OSError, ValueError):
            pass
        state = self._store.state
        self.title_edit.setText(state.title)
        self.question_edit.setPlainText(state.research_question)
        self.context_edit.setPlainText(state.known_context)
        selected_axes = set(state.selected_axes)
        for index in range(self.axis_list.count()):
            row = self.axis_list.item(index)
            row.setCheckState(
                Qt.CheckState.Checked
                if row.text() in selected_axes
                else Qt.CheckState.Unchecked
            )
        self.synthesis_edit.setPlainText(state.synthesis_notes)
        self.principles_edit.setPlainText(state.transferable_principles)
        self.limitations_edit.setPlainText(state.limitations)
        self._refresh_items()
        self.local_output.setPlainText(
            format_local_comparison(state.local_comparison)
            if state.local_comparison
            else ""
        )
        self.ai_output.setPlainText(
            format_comparative_review(state.ai_comparison)
            if state.ai_comparison
            else ""
        )
        self._refresh_ai_history()
        self.setWindowTitle(f"GATalk — 对照研究 — {state.title}")

    def _refresh_items(self) -> None:
        self.item_list.blockSignals(True)
        self.item_list.clear()
        if self._store:
            active = set(self._store.state.active_item_ids)
            for item in self._store.state.items:
                row = QListWidgetItem(item.title)
                row.setData(Qt.ItemDataRole.UserRole, item.item_id)
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                row.setCheckState(
                    Qt.CheckState.Checked
                    if item.item_id in active
                    else Qt.CheckState.Unchecked
                )
                row.setToolTip(
                    f"来源：{item.source_kind}\nSHA-256：{item.sha256[:16]}…"
                )
                self.item_list.addItem(row)
        self.item_list.blockSignals(False)
        self._refresh_visuals()

    def focus_entity(self, entity_type: str, entity_id: str) -> None:
        if entity_type != "comparison_work" or not entity_id:
            return
        for index in range(self.item_list.count()):
            row = self.item_list.item(index)
            if str(row.data(Qt.ItemDataRole.UserRole)) == entity_id:
                self.item_list.setCurrentItem(row)
                return

    def _refresh_visuals(self) -> None:
        while self.visual_grid.count():
            item = self.visual_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        if self._store is None or not self._store.state.items:
            placeholder = QLabel("导入作品后，这里会以同等权重并置显示。")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.visual_grid.addWidget(placeholder, 0, 0)
            return
        active = set(self._store.state.active_item_ids)
        items = [item for item in self._store.state.items if item.item_id in active]
        for index, item in enumerate(items):
            card = QWidget()
            card.setObjectName("workspaceCard")
            layout = QVBoxLayout(card)
            heading = QLabel(f"{index + 1:02d}  {item.title}")
            heading.setObjectName("cardTitle")
            layout.addWidget(heading)
            image = QLabel()
            image.setMinimumSize(280, 220)
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(str(self._store.item_path(item)))
            image.setPixmap(
                pixmap.scaled(
                    520,
                    360,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            layout.addWidget(image, 1)
            source = QLabel(
                "来自资料库" if item.source_kind == "knowledge_library" else "本地导入"
            )
            source.setProperty("role", "muted")
            layout.addWidget(source)
            self.visual_grid.addWidget(card, index // 2, index % 2)

    def _import_images(self) -> None:
        if self._store is None:
            QMessageBox.information(self, "尚未建立研究", "请先新建或打开对照研究。")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入研究作品",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp)",
        )
        for path in paths:
            try:
                self._store.import_image(path)
            except Exception as exc:
                QMessageBox.warning(self, "部分作品未导入", f"{Path(path).name}：{exc}")
        self._refresh_items()

    def _active_selection_changed(self, _row: QListWidgetItem) -> None:
        if self._store is None:
            return
        ids = [
            str(self.item_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.item_list.count())
            if self.item_list.item(index).checkState() == Qt.CheckState.Checked
        ]
        if len(ids) > 6:
            _row.setCheckState(Qt.CheckState.Unchecked)
            QMessageBox.information(self, "选择数量已达上限", "一次对照最多选择六件作品。")
            return
        self._store.set_active_items(ids)
        self._refresh_visuals()

    def _highlight_work(self, row: QListWidgetItem | None, _previous=None) -> None:
        if row is not None:
            self.statusBar().showMessage(f"当前作品：{row.text()}", 2500)

    def _set_current_as_baseline(self) -> None:
        if self._store is None:
            return
        row = self.item_list.currentItem()
        if row is None:
            QMessageBox.information(self, "尚未选择作品", "请先在作品列表中选择一件作品。")
            return
        item_id = str(row.data(Qt.ItemDataRole.UserRole))
        item_title = row.text()
        active = list(self._store.state.active_item_ids)
        if item_id not in active:
            row.setCheckState(Qt.CheckState.Checked)
            active = list(self._store.state.active_item_ids)
        active = [item_id, *(value for value in active if value != item_id)]
        self._store.set_active_items(active)
        self._refresh_items()
        self.statusBar().showMessage(f"已将“{item_title}”设为对照基准。", 3000)

    def _remove_selected(self) -> None:
        if self._store is None:
            return
        ids = [
            str(row.data(Qt.ItemDataRole.UserRole))
            for row in self.item_list.selectedItems()
        ]
        if not ids:
            return
        if QMessageBox.question(self, "移除作品", "从本次研究移除所选作品？") != QMessageBox.StandardButton.Yes:
            return
        self._store.remove_items(ids)
        self._refresh_items()

    def _selected_axes(self) -> tuple[str, ...]:
        return tuple(
            self.axis_list.item(index).text()
            for index in range(self.axis_list.count())
            if self.axis_list.item(index).checkState() == Qt.CheckState.Checked
        )

    def _start_local_analysis(self) -> None:
        if self._store is None or len(self._store.state.active_item_ids) < 2:
            QMessageBox.information(self, "作品数量不足", "请勾选至少两件作品。")
            return
        self._save_state()
        self._generation += 1
        generation = self._generation
        snapshot = [self._store.item(item_id) for item_id in self._store.state.active_item_ids]
        self.analyze_button.setEnabled(False)
        self.statusBar().showMessage("正在后台计算本地证据…")

        def operation():
            analyses = []
            for item in snapshot:
                loaded = load_image(self._store.item_path(item))
                measurements = measure_image(loaded.rgb, palette_colours=8)
                analysis = analyze_artwork(loaded.rgb, measurements).to_dict()
                analyses.append((item.item_id, item.title, analysis))
            comparison = build_local_comparison(
                [(title, analysis) for _item_id, title, analysis in analyses]
            )
            return analyses, comparison

        worker = FunctionWorker("comparison", "local", generation, operation)
        worker.signals.result.connect(self._apply_local_result)
        worker.signals.error.connect(self._worker_error)
        worker.signals.finished.connect(lambda *_args: self.analyze_button.setEnabled(True))
        self._thread_pool.start(worker)

    def _apply_local_result(self, _role, _kind, generation, result) -> None:
        if generation != self._generation or self._store is None:
            return
        analyses, comparison = result
        items = []
        by_id = {item_id: analysis for item_id, _title, analysis in analyses}
        for item in self._store.state.items:
            items.append(
                replace(item, local_analysis=by_id.get(item.item_id, item.local_analysis))
            )
        self._store.save(
            replace(
                self._store.state,
                items=tuple(items),
                local_comparison=comparison,
                ai_comparison={},
                ai_run={},
            )
        )
        self.local_output.setPlainText(format_local_comparison(comparison))
        self.statusBar().showMessage("本地对照已完成。", 4000)

    def _provider_changed(self) -> None:
        provider_id = str(self.provider_combo.currentData() or "")
        if not provider_id:
            return
        manifest = self._providers.manifest(provider_id)
        self.model_edit.setText(
            manifest.model_for(ProviderCapability.VISION_REVIEW)
        )
        try:
            self.credential_edit.setText(
                self._credential_store.get(manifest.credential_target) or ""
            )
        except OSError:
            self.credential_edit.clear()

    def _save_credential(self) -> None:
        provider_id = str(self.provider_combo.currentData() or "")
        if not provider_id:
            return
        secret = self.credential_edit.text().strip()
        if not secret:
            QMessageBox.information(self, "没有可保存的凭据", "请先输入 API Key。")
            return
        manifest = self._providers.manifest(provider_id)
        try:
            self._credential_store.set(manifest.credential_target, secret)
        except OSError as exc:
            QMessageBox.warning(self, "无法保存系统凭据", str(exc))
            return
        self.statusBar().showMessage("API Key 已保存到 Windows 系统凭据。", 3500)

    def _start_ai_review(self) -> None:
        if self._store is None or len(self._store.state.active_item_ids) < 2:
            QMessageBox.information(self, "作品数量不足", "请勾选至少两件作品。")
            return
        if not self._store.state.local_comparison:
            QMessageBox.information(self, "缺少本地证据", "请先运行本地对照。")
            return
        provider_id = str(self.provider_combo.currentData())
        manifest = self._providers.manifest(provider_id)
        credential = self.credential_edit.text().strip()
        if provider_id != "mock" and not credential:
            QMessageBox.information(self, "缺少 API Key", "请输入 API Key 或从系统凭据读取。")
            return
        active = [self._store.item(value) for value in self._store.state.active_item_ids]
        loaded = [load_image(self._store.item_path(item)) for item in active]
        images = tuple(
            prepare_provider_image(
                value,
                f"artwork_{index + 1}",
                ProviderImageExportOptions(remove_metadata=True, maximum_side=2048),
            )
            for index, value in enumerate(loaded)
        )
        context = ComparativeStudyContext(
            study_id=self._store.state.study_id,
            title=self.title_edit.text().strip(),
            research_question=self.question_edit.toPlainText().strip(),
            known_context=self.context_edit.toPlainText().strip(),
            selected_axes=self._selected_axes(),
            items=tuple(
                {
                    "item_id": item.item_id,
                    "display_title": item.title,
                    "image_sha256": item.sha256,
                    "source_kind": item.source_kind,
                    "local_analysis": dict(item.local_analysis),
                }
                for item in active
            ),
            local_comparison=self._store.state.local_comparison,
        )
        request = self._reviewer.create_request(
            context,
            images,
            model_id=self.model_edit.text().strip() or None,
            user_initiated=True,
            disclosure_confirmed=True,
        )
        size_mib = sum(len(image.data) for image in images) / (1024 * 1024)
        answer = QMessageBox.question(
            self,
            "确认发送对照研究数据",
            f"将向 {manifest.display_name} 发送 {len(images)} 张已移除元数据、"
            f"最长边 2048 px 的图片副本（约 {size_mib:.1f} MiB），以及研究问题、"
            "已知背景和本地测量。是否继续？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._generation += 1
        generation = self._generation
        self.run_ai_button.setEnabled(False)
        self.ai_status.setText("正在后台执行作品对照研究…")
        cancellation = CancellationToken()

        def operation():
            provider = self._providers.get(provider_id)
            execution = self._execution.run_review_with_model_fallback(
                provider,
                request,
                credential,
                cancellation,
                manifest.fallback_models_for(
                    ProviderCapability.VISION_REVIEW,
                    request.model_id,
                ),
            )
            output = self._reviewer.validate_output(execution.response.output)
            return execution, output

        worker = FunctionWorker("comparison", "ai", generation, operation)
        worker.signals.result.connect(self._apply_ai_result)
        worker.signals.error.connect(self._worker_error)
        worker.signals.finished.connect(lambda *_args: self.run_ai_button.setEnabled(True))
        self._thread_pool.start(worker)

    def _apply_ai_result(self, _role, _kind, generation, result) -> None:
        if generation != self._generation or self._store is None:
            return
        execution, output = result
        response = execution.response
        completed_at = utc_now()
        run = {
            "provider_id": response.provider_id,
            "model_id": response.model_id,
            "reviewer_id": self._reviewer.descriptor.reviewer_id,
            "reviewer_version": self._reviewer.descriptor.version,
            "image_hashes": [
                self._store.item(value).sha256
                for value in self._store.state.active_item_ids
            ],
            "completed_at": completed_at,
        }
        history_entry = {
            "run_id": str(uuid.uuid4()),
            "completed_at": completed_at,
            "run": run,
            "output": output,
        }
        self._store.save(
            replace(
                self._store.state,
                ai_comparison=output,
                ai_run=run,
                ai_history=(*self._store.state.ai_history, history_entry),
            )
        )
        self.ai_output.setPlainText(format_comparative_review(output))
        self._refresh_ai_history(history_entry["run_id"])
        self.ai_status.setText(f"完成：{response.provider_id} / {response.model_id}")

    def _refresh_ai_history(self, selected_id: str | None = None) -> None:
        self.ai_history_combo.blockSignals(True)
        self.ai_history_combo.clear()
        history = () if self._store is None else self._store.state.ai_history
        for entry in reversed(history):
            run = entry.get("run", {})
            stamp = str(entry.get("completed_at", "")).replace("T", " ")[:19]
            self.ai_history_combo.addItem(
                f"{stamp} · {run.get('provider_id', '')} / {run.get('model_id', '')}",
                str(entry.get("run_id", "")),
            )
        if selected_id:
            index = self.ai_history_combo.findData(selected_id)
            if index >= 0:
                self.ai_history_combo.setCurrentIndex(index)
        self.ai_history_combo.blockSignals(False)
        self.delete_ai_history_button.setEnabled(bool(history))

    def _show_selected_ai_history(self, _index: int) -> None:
        if self._store is None:
            return
        run_id = str(self.ai_history_combo.currentData() or "")
        entry = next(
            (value for value in self._store.state.ai_history if value.get("run_id") == run_id),
            None,
        )
        if entry is None:
            return
        output = entry.get("output", {})
        if isinstance(output, dict):
            self.ai_output.setPlainText(format_comparative_review(output))
            run = entry.get("run", {})
            self.ai_status.setText(
                f"历史记录：{run.get('provider_id', '')} / {run.get('model_id', '')}"
            )

    def _delete_selected_ai_history(self) -> None:
        if self._store is None:
            return
        run_id = str(self.ai_history_combo.currentData() or "")
        if not run_id or QMessageBox.question(
            self, "删除研究记录", "删除这次专家对照记录？研究笔记不会受影响。"
        ) != QMessageBox.StandardButton.Yes:
            return
        remaining = tuple(
            value for value in self._store.state.ai_history
            if value.get("run_id") != run_id
        )
        latest = remaining[-1] if remaining else {}
        self._store.save(
            replace(
                self._store.state,
                ai_history=remaining,
                ai_comparison=dict(latest.get("output", {})),
                ai_run=dict(latest.get("run", {})),
            )
        )
        self._refresh_ai_history()
        self.ai_output.setPlainText(
            format_comparative_review(self._store.state.ai_comparison)
            if self._store.state.ai_comparison else ""
        )

    def _worker_error(self, _role, _kind, generation, message, _traceback) -> None:
        if generation != self._generation:
            return
        self.ai_status.setText("任务失败。详细错误已显示。")
        QMessageBox.warning(self, "对照研究失败", message)

    def _save_state(self) -> None:
        if self._store is None:
            return
        self._store.save(
            replace(
                self._store.state,
                title=self.title_edit.text().strip() or self._store.state.title,
                research_question=self.question_edit.toPlainText().strip(),
                known_context=self.context_edit.toPlainText().strip(),
                selected_axes=self._selected_axes(),
                synthesis_notes=self.synthesis_edit.toPlainText().strip(),
                transferable_principles=self.principles_edit.toPlainText().strip(),
                limitations=self.limitations_edit.toPlainText().strip(),
            )
        )
        self.statusBar().showMessage("对照研究已保存。", 3000)
