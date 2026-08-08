from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
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
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scenelens.modules.knowledge_base.domains import built_in_knowledge_domains
from scenelens.modules.knowledge_base.models import KnowledgeItem
from scenelens.modules.knowledge_base.project_refs import detect_gatalk_project
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.modules.knowledge_base.translation import (
    create_translation_request,
    validate_translation_output,
)
from scenelens.modules.knowledge_base.ui.crop_dialog import ImageExcerptDialog
from scenelens.modules.knowledge_base.ui.board_window import VisualBoardWindow
from scenelens.providers.contracts import ProviderCapability, ProviderError
from scenelens.providers.credentials import (
    MemoryCredentialStore,
    WindowsCredentialStore,
)
from scenelens.providers.execution import ProviderExecutionService
from scenelens.providers.factory import create_default_provider_registry
from scenelens.storage.project_store import utc_now
from scenelens.storage.workspace_catalog import WorkspaceCatalogStore


LIBRARY_SUFFIX = ".gatalk-library"
SOURCE_TYPES = (
    ("original_artwork", "原画 / 概念图"),
    ("artstation", "ArtStation 作品"),
    ("article", "文章"),
    ("tutorial", "教程"),
    ("project_note", "项目笔记"),
    ("image_excerpt", "局部截图"),
    ("webpage", "网页来源"),
    ("document", "文档"),
    ("other", "其他"),
)
SOURCE_TYPE_LABELS = dict(SOURCE_TYPES)


class KnowledgeBaseWindow(QMainWindow):
    workspace_home_requested = Signal()
    comparative_study_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GATalk — 参考资料与知识库")
        self.resize(1520, 900)
        self.setMinimumSize(1100, 680)
        self._store: KnowledgeLibraryStore | None = None
        self._current_item_id: str | None = None
        self._loaded_translation_text = ""
        self._provider_registry = create_default_provider_registry()
        self._execution = ProviderExecutionService(max_workers=2)
        self._translation_job = None
        self._board_windows: list[VisualBoardWindow] = []
        try:
            self._credential_store = WindowsCredentialStore()
        except OSError:
            self._credential_store = MemoryCredentialStore()
        self._build_ui()

    def _build_ui(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        home = QAction("工作台首页", self)
        home.setShortcut(QKeySequence("Ctrl+Shift+H"))
        home.triggered.connect(self.workspace_home_requested)
        file_menu.addAction(home)
        new_action = QAction("新建资料库…", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._new_library)
        file_menu.addAction(new_action)
        open_action = QAction("打开资料库…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_library)
        file_menu.addAction(open_action)
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_current)
        file_menu.addAction(save_action)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("参考资料与知识库")
        title.setObjectName("heroTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.library_label = QLabel("尚未打开资料库")
        self.library_label.setProperty("role", "muted")
        header.addWidget(self.library_label)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_navigation())
        splitter.addWidget(self._build_catalog())
        splitter.addWidget(self._build_details())
        splitter.setSizes([250, 760, 430])
        outer.addWidget(splitter, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage(
            "资料只在主动导入时复制；网页链接只记录地址，不自动下载内容。"
        )

    def _build_navigation(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("资料领域与集合")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        self.collection_tree = QTreeWidget()
        self.collection_tree.setHeaderHidden(True)
        self.collection_tree.currentItemChanged.connect(self._refresh_items)
        layout.addWidget(self.collection_tree, 1)
        row = QHBoxLayout()
        add = QPushButton("新建集合")
        add.clicked.connect(self._add_collection)
        row.addWidget(add)
        layout.addLayout(row)
        notice = QLabel("关卡设计与策划资料域已预留，待对应业务模块建立后启用。")
        notice.setWordWrap(True)
        notice.setProperty("role", "muted")
        layout.addWidget(notice)
        return panel

    def _build_catalog(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 8, 0)
        tools = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索标题、作者、项目、标签或笔记…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._refresh_items)
        tools.addWidget(self.search_edit, 1)
        import_button = QPushButton("导入文件…")
        import_button.setProperty("primary", True)
        import_button.clicked.connect(self._import_files)
        tools.addWidget(import_button)
        link_button = QPushButton("添加来源链接…")
        link_button.clicked.connect(self._add_link)
        tools.addWidget(link_button)
        note_button = QPushButton("新建项目笔记")
        note_button.clicked.connect(self._add_note)
        tools.addWidget(note_button)
        layout.addLayout(tools)
        self.item_list = QListWidget()
        self.item_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.item_list.currentItemChanged.connect(self._show_item)
        self.item_list.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.item_list, 1)
        bottom = QHBoxLayout()
        self.count_label = QLabel("0 项")
        self.count_label.setProperty("role", "muted")
        bottom.addWidget(self.count_label)
        bottom.addStretch(1)
        self.compare_button = QPushButton("用所选资料建立对照研究")
        self.compare_button.setEnabled(False)
        self.compare_button.clicked.connect(self._start_comparison)
        bottom.addWidget(self.compare_button)
        self.board_button = QPushButton("打开视觉资料板")
        self.board_button.clicked.connect(self._open_visual_board)
        bottom.addWidget(self.board_button)
        delete = QPushButton("移除所选")
        delete.clicked.connect(self._delete_selected)
        bottom.addWidget(delete)
        layout.addLayout(bottom)
        return panel

    def _build_details(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 0, 4, 12)
        heading = QLabel("资料详情")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        self.preview = QLabel("选择一项资料查看详情")
        self.preview.setMinimumHeight(220)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("border: 1px solid palette(mid); border-radius: 8px;")
        layout.addWidget(self.preview)
        self.crop_button = QPushButton("从当前图片建立局部截图…")
        self.crop_button.setEnabled(False)
        self.crop_button.clicked.connect(self._create_excerpt)
        layout.addWidget(self.crop_button)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.creator_edit = QLineEdit()
        self.project_edit = QLineEdit()
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("用逗号分隔")
        self.source_edit = QLineEdit()
        self.source_edit.setReadOnly(True)
        self.provenance_label = QLabel("—")
        self.source_type_combo = QComboBox()
        for source_id, label in SOURCE_TYPES:
            self.source_type_combo.addItem(label, source_id)
        form.addRow("标题", self.title_edit)
        form.addRow("作者 / 团队", self.creator_edit)
        form.addRow("项目 / 出处", self.project_edit)
        form.addRow("标签", self.tags_edit)
        form.addRow("资料类型", self.source_type_combo)
        form.addRow("来源", self.source_edit)
        form.addRow("来源状态", self.provenance_label)
        layout.addLayout(form)
        layout.addWidget(QLabel("资料说明"))
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("记录画面用途、主题或检索说明。")
        self.description_edit.setMaximumHeight(110)
        layout.addWidget(self.description_edit)
        layout.addWidget(QLabel("研究笔记"))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("记录观察、引用范围与待核实信息。")
        layout.addWidget(self.notes_edit, 1)

        translation_group = QGroupBox("原文与翻译")
        translation_layout = QVBoxLayout(translation_group)
        self.original_text_edit = QPlainTextEdit()
        self.original_text_edit.setPlaceholderText(
            "粘贴文章、教程说明或作品介绍中的原文。"
        )
        self.original_text_edit.setMaximumHeight(110)
        translation_layout.addWidget(self.original_text_edit)
        self.translation_text_edit = QPlainTextEdit()
        self.translation_text_edit.setPlaceholderText(
            "可手动翻译，也可在确认发送后调用所选供应商。"
        )
        self.translation_text_edit.setMaximumHeight(130)
        translation_layout.addWidget(self.translation_text_edit)
        translation_form = QFormLayout()
        self.translation_provider = QComboBox()
        for provider in self._provider_registry.for_capability(
            ProviderCapability.STRUCTURED_OUTPUT
        ):
            self.translation_provider.addItem(
                provider.manifest.display_name,
                provider.manifest.provider_id,
            )
        self.translation_provider.currentIndexChanged.connect(
            self._translation_provider_changed
        )
        self.translation_model = QLineEdit()
        self.translation_key = QLineEdit()
        self.translation_key.setEchoMode(QLineEdit.EchoMode.Password)
        translation_form.addRow("翻译供应商", self.translation_provider)
        translation_form.addRow("模型 ID", self.translation_model)
        translation_form.addRow("API Key", self.translation_key)
        translation_layout.addLayout(translation_form)
        translation_actions = QHBoxLayout()
        save_key = QPushButton("存入系统凭据")
        save_key.clicked.connect(self._save_translation_credential)
        translation_actions.addWidget(save_key)
        self.translate_button = QPushButton("检查发送内容并翻译")
        self.translate_button.setProperty("primary", True)
        self.translate_button.clicked.connect(self._start_translation)
        translation_actions.addWidget(self.translate_button)
        self.cancel_translation_button = QPushButton("取消")
        self.cancel_translation_button.setEnabled(False)
        self.cancel_translation_button.clicked.connect(self._cancel_translation)
        translation_actions.addWidget(self.cancel_translation_button)
        translation_layout.addLayout(translation_actions)
        self.translation_status = QLabel("翻译不会自动发送；手动编辑始终可用。")
        self.translation_status.setWordWrap(True)
        self.translation_status.setProperty("role", "muted")
        translation_layout.addWidget(self.translation_status)
        layout.addWidget(translation_group)

        reference_group = QGroupBox("跨项目引用")
        reference_layout = QVBoxLayout(reference_group)
        self.project_reference_list = QListWidget()
        self.project_reference_list.setMaximumHeight(125)
        reference_layout.addWidget(self.project_reference_list)
        reference_actions = QHBoxLayout()
        add_reference = QPushButton("关联 GATalk 项目…")
        add_reference.clicked.connect(self._add_project_reference)
        reference_actions.addWidget(add_reference)
        remove_reference = QPushButton("移除引用")
        remove_reference.clicked.connect(self._remove_project_reference)
        reference_actions.addWidget(remove_reference)
        reference_layout.addLayout(reference_actions)
        layout.addWidget(reference_group)
        actions = QHBoxLayout()
        self.assign_button = QPushButton("管理所属集合…")
        self.assign_button.clicked.connect(self._assign_current_collection)
        actions.addWidget(self.assign_button)
        save = QPushButton("保存资料详情")
        save.setProperty("primary", True)
        save.clicked.connect(self._save_item_details)
        actions.addWidget(save)
        layout.addLayout(actions)
        scroll.setWidget(body)
        self._translation_provider_changed()
        return scroll

    def _new_library(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择新的资料库目录")
        if not path:
            return
        title, accepted = QInputDialog.getText(self, "新建资料库", "资料库名称")
        if not accepted:
            return
        try:
            self._store = KnowledgeLibraryStore.create(path, title)
        except Exception as exc:
            QMessageBox.warning(self, "无法新建资料库", str(exc))
            return
        self._load_state()

    def _open_library(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "打开资料库")
        if not path:
            return
        try:
            self._store = KnowledgeLibraryStore.open(path)
        except Exception as exc:
            QMessageBox.warning(self, "无法打开资料库", str(exc))
            return
        self._load_state()

    def open_path(self, path: str | Path) -> bool:
        try:
            self._store = KnowledgeLibraryStore.open(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法打开资料库", str(exc))
            return False
        self._load_state()
        return True

    def _load_state(self) -> None:
        if self._store is None:
            return
        try:
            WorkspaceCatalogStore().remember(self._store.root)
        except (OSError, ValueError):
            pass
        self.library_label.setText(
            f"{self._store.state.title}  ·  {self._store.root}"
        )
        self._refresh_tree()
        self._refresh_items()

    def _refresh_tree(self) -> None:
        self.collection_tree.clear()
        if self._store is None:
            return
        collection_nodes: dict[str, QTreeWidgetItem] = {}
        for domain in built_in_knowledge_domains():
            root = QTreeWidgetItem([domain.display_name])
            root.setData(0, Qt.ItemDataRole.UserRole, ("domain", domain.domain_id))
            if not domain.enabled:
                root.setDisabled(True)
                root.setToolTip(0, "该资料域已预留，当前版本尚未启用。")
            self.collection_tree.addTopLevelItem(root)
            if domain.enabled:
                all_items = QTreeWidgetItem(["全部资料"])
                all_items.setData(
                    0, Qt.ItemDataRole.UserRole, ("domain", domain.domain_id)
                )
                root.addChild(all_items)
                for collection in self._store.state.collections:
                    if collection.domain_id != domain.domain_id:
                        continue
                    node = QTreeWidgetItem([collection.name])
                    node.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        ("collection", collection.collection_id),
                    )
                    collection_nodes[collection.collection_id] = node
                for collection in self._store.state.collections:
                    node = collection_nodes.get(collection.collection_id)
                    if node is None:
                        continue
                    parent = collection_nodes.get(collection.parent_id or "", root)
                    parent.addChild(node)
                root.setExpanded(True)
        if self.collection_tree.topLevelItemCount():
            root = self.collection_tree.topLevelItem(0)
            self.collection_tree.setCurrentItem(root.child(0) if root.childCount() else root)

    def _current_filter(self) -> tuple[str, str | None]:
        node = self.collection_tree.currentItem()
        if node is None:
            return "art_reference", None
        value = node.data(0, Qt.ItemDataRole.UserRole)
        if not value:
            return "art_reference", None
        kind, identity = value
        if kind == "domain":
            return str(identity), None
        collection = next(
            (
                item
                for item in self._store.state.collections
                if item.collection_id == identity
            ),
            None,
        ) if self._store else None
        return (
            collection.domain_id if collection else "art_reference",
            str(identity),
        )

    def _refresh_items(self, *_args) -> None:
        self.item_list.clear()
        if self._store is None:
            self.count_label.setText("0 项")
            return
        domain_id, collection_id = self._current_filter()
        items = self._store.items_for(
            domain_id=domain_id,
            collection_id=collection_id,
            search=self.search_edit.text(),
        )
        for item in items:
            row = QListWidgetItem(
                f"{item.title}\n"
                f"{SOURCE_TYPE_LABELS.get(item.source_type, item.source_type)} · "
                f"{', '.join(item.tags) if item.tags else '未添加标签'}"
            )
            row.setData(Qt.ItemDataRole.UserRole, item.item_id)
            row.setToolTip(item.source_value or item.original_filename or "本地记录")
            self.item_list.addItem(row)
        self.count_label.setText(f"{len(items)} 项")
        if items and self.item_list.currentRow() < 0:
            self.item_list.setCurrentRow(0)
        self._selection_changed()

    def _show_item(self, row: QListWidgetItem | None, _previous=None) -> None:
        if row is None or self._store is None:
            self._current_item_id = None
            return
        item_id = str(row.data(Qt.ItemDataRole.UserRole))
        item = next(value for value in self._store.state.items if value.item_id == item_id)
        self._current_item_id = item_id
        self.title_edit.setText(item.title)
        self.creator_edit.setText(item.creator)
        self.project_edit.setText(item.project_name)
        self.tags_edit.setText("，".join(item.tags))
        source_index = self.source_type_combo.findData(item.source_type)
        self.source_type_combo.setCurrentIndex(max(0, source_index))
        self.source_edit.setText(item.source_value or item.original_filename or "手动记录")
        status_labels = {
            "local_import": "本地导入",
            "local_derived": "本地派生截图",
            "user_created": "用户创建",
            "verified": "用户已核实",
            "unverified": "尚未核实",
        }
        self.provenance_label.setText(status_labels.get(item.provenance_status, item.provenance_status))
        self.description_edit.setPlainText(item.description)
        self.notes_edit.setPlainText(item.notes)
        self.original_text_edit.setPlainText(item.original_text)
        self.translation_text_edit.setPlainText(item.translation_text)
        self._loaded_translation_text = item.translation_text
        if item.translation_source:
            self.translation_status.setText(
                f"当前译文：{item.translation_source}"
                + (
                    f" · {item.translation_provider_id}/{item.translation_model_id}"
                    if item.translation_provider_id
                    else ""
                )
            )
        else:
            self.translation_status.setText("尚未保存译文。")
        self._refresh_project_references(item.item_id)
        path = self._store.resolve_item_path(item)
        if item.item_type == "image" and path is not None and path.is_file():
            self.crop_button.setEnabled(True)
            pixmap = QPixmap(str(path))
            self.preview.setPixmap(
                pixmap.scaled(
                    390,
                    240,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.crop_button.setEnabled(False)
            self.preview.setPixmap(QPixmap())
            self.preview.setText(item.source_value or "无图片预览")

    def _selection_changed(self) -> None:
        image_count = 0
        if self._store:
            ids = {
                str(row.data(Qt.ItemDataRole.UserRole))
                for row in self.item_list.selectedItems()
            }
            image_count = sum(
                item.item_type == "image" and item.item_id in ids
                for item in self._store.state.items
            )
        self.compare_button.setEnabled(2 <= image_count <= 6)
        self.compare_button.setText(
            f"用所选 {image_count} 项建立对照研究"
            if image_count
            else "用所选资料建立对照研究"
        )

    def _open_visual_board(self) -> None:
        if self._store is None:
            QMessageBox.information(self, "尚未打开资料库", "请先新建或打开资料库。")
            return
        item_ids = tuple(
            str(row.data(Qt.ItemDataRole.UserRole))
            for row in self.item_list.selectedItems()
        )
        window = VisualBoardWindow(self._store, item_ids, self)
        window.destroyed.connect(
            lambda *_args, value=window: (
                self._board_windows.remove(value)
                if value in self._board_windows
                else None
            )
        )
        self._board_windows.append(window)
        window.show()

    def _selected_collection_id(self) -> str | None:
        _domain, collection = self._current_filter()
        return collection

    def _add_collection(self) -> None:
        if self._store is None:
            QMessageBox.information(self, "尚未打开资料库", "请先新建或打开资料库。")
            return
        parent_id = self._selected_collection_id()
        title = "新建子集合" if parent_id else "新建集合"
        name, accepted = QInputDialog.getText(self, title, "集合名称")
        if not accepted:
            return
        self._store.add_collection(name, parent_id=parent_id)
        self._refresh_tree()

    def _import_files(self) -> None:
        if self._store is None:
            QMessageBox.information(self, "尚未打开资料库", "请先新建或打开资料库。")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入参考资料",
            "",
            "支持的资料 (*.png *.jpg *.jpeg *.webp *.pdf *.txt *.md);;所有文件 (*)",
        )
        collection = self._selected_collection_id()
        for path in paths:
            try:
                self._store.import_file(
                    path,
                    collection_ids=(collection,) if collection else (),
                )
            except Exception as exc:
                QMessageBox.warning(self, "部分资料未导入", f"{Path(path).name}：{exc}")
        self._refresh_items()

    def _add_link(self) -> None:
        if self._store is None:
            QMessageBox.information(self, "尚未打开资料库", "请先新建或打开资料库。")
            return
        url, accepted = QInputDialog.getText(self, "添加来源链接", "网页地址")
        if not accepted:
            return
        title, accepted = QInputDialog.getText(self, "添加来源链接", "资料标题")
        if not accepted:
            return
        source_label, accepted = QInputDialog.getItem(
            self,
            "添加来源链接",
            "资料类型",
            [label for _source_id, label in SOURCE_TYPES if _source_id not in {"project_note", "image_excerpt", "document"}],
            editable=False,
        )
        if not accepted:
            return
        source_type = next(
            source_id
            for source_id, label in SOURCE_TYPES
            if label == source_label
        )
        if "artstation.com" in url.casefold():
            source_type = "artstation"
        collection = self._selected_collection_id()
        try:
            self._store.add_link(
                url,
                title,
                collection_ids=(collection,) if collection else (),
                source_type=source_type,
            )
        except Exception as exc:
            QMessageBox.warning(self, "无法添加来源", str(exc))
            return
        self._refresh_items()

    def _add_note(self) -> None:
        if self._store is None:
            QMessageBox.information(self, "尚未打开资料库", "请先新建或打开资料库。")
            return
        title, accepted = QInputDialog.getText(self, "新建项目笔记", "笔记标题")
        if not accepted:
            return
        collection = self._selected_collection_id()
        item = self._store.add_note(
            title,
            collection_ids=(collection,) if collection else (),
        )
        self._refresh_items()
        self._select_item(item.item_id)

    def _save_item_details(self) -> None:
        if self._store is None or self._current_item_id is None:
            return
        item = next(
            value
            for value in self._store.state.items
            if value.item_id == self._current_item_id
        )
        tags = tuple(
            dict.fromkeys(
                value.strip()
                for value in self.tags_edit.text().replace("，", ",").split(",")
                if value.strip()
            )
        )
        self._store.update_item(
            replace(
                item,
                title=self.title_edit.text().strip() or item.title,
                creator=self.creator_edit.text().strip(),
                project_name=self.project_edit.text().strip(),
                tags=tags,
                source_type=str(self.source_type_combo.currentData() or "other"),
                description=self.description_edit.toPlainText().strip(),
                notes=self.notes_edit.toPlainText().strip(),
                original_text=self.original_text_edit.toPlainText().strip(),
                translation_text=self.translation_text_edit.toPlainText().strip(),
                translation_source=(
                    "用户修订"
                    if self.translation_text_edit.toPlainText().strip()
                    != self._loaded_translation_text.strip()
                    else item.translation_source
                ),
                translation_updated_at=(
                    item.translation_updated_at
                    if self.translation_text_edit.toPlainText().strip()
                    == self._loaded_translation_text.strip()
                    else utc_now()
                ),
            )
        )
        self._loaded_translation_text = self.translation_text_edit.toPlainText().strip()
        self.statusBar().showMessage("资料详情已保存。", 3000)
        self._refresh_items()

    def _assign_current_collection(self) -> None:
        if self._store is None or self._current_item_id is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("管理所属集合")
        dialog.resize(420, 440)
        layout = QVBoxLayout(dialog)
        explanation = QLabel("一项资料可以同时归入多个集合；文件只保留一份。")
        explanation.setWordWrap(True)
        explanation.setProperty("role", "muted")
        layout.addWidget(explanation)
        collection_list = QListWidget()
        current = set(self._store.state.memberships.get(self._current_item_id, ()))
        for collection in self._store.state.collections:
            row = QListWidgetItem(collection.name)
            row.setData(Qt.ItemDataRole.UserRole, collection.collection_id)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(
                Qt.CheckState.Checked
                if collection.collection_id in current
                else Qt.CheckState.Unchecked
            )
            collection_list.addItem(row)
        layout.addWidget(collection_list, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        memberships = [
            str(collection_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(collection_list.count())
            if collection_list.item(index).checkState() == Qt.CheckState.Checked
        ]
        self._store.set_memberships(self._current_item_id, memberships)
        self.statusBar().showMessage("所属集合已更新。", 3000)

    def _delete_selected(self) -> None:
        if self._store is None:
            return
        ids = [
            str(row.data(Qt.ItemDataRole.UserRole))
            for row in self.item_list.selectedItems()
        ]
        if not ids:
            return
        answer = QMessageBox.question(
            self,
            "移除资料",
            "从资料库移除所选条目？已导入的原始文件不会立即删除。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._store.delete_items(ids)
        self._refresh_items()

    def _start_comparison(self) -> None:
        if self._store is None:
            return
        ids = {
            str(row.data(Qt.ItemDataRole.UserRole))
            for row in self.item_list.selectedItems()
        }
        items = []
        for item in self._store.state.items:
            if item.item_id not in ids or item.item_type != "image":
                continue
            path = self._store.resolve_item_path(item)
            if path is not None:
                items.append(
                    {
                        "path": str(path),
                        "title": item.title,
                        "source_kind": "knowledge_library",
                        "source_reference": (
                            f"{self._store.state.library_id}:{item.item_id}"
                        ),
                    }
                )
        if not 2 <= len(items) <= 6:
            QMessageBox.information(self, "选择数量不合适", "请选择 2 至 6 项图片资料。")
            return
        self.comparative_study_requested.emit(
            {
                "library_path": str(self._store.root),
                "items": items,
            }
        )

    def _create_excerpt(self) -> None:
        if self._store is None or self._current_item_id is None:
            return
        item = next(
            value
            for value in self._store.state.items
            if value.item_id == self._current_item_id
        )
        path = self._store.resolve_item_path(item)
        if item.item_type != "image" or path is None:
            return
        dialog = ImageExcerptDialog(str(path), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        rect = dialog.normalized_rect()
        if rect is None:
            return
        title, accepted = QInputDialog.getText(
            self,
            "保存局部截图",
            "资料标题",
            text=f"{item.title} · 局部",
        )
        if not accepted:
            return
        try:
            excerpt = self._store.create_image_excerpt(
                item.item_id,
                rect,
                title=title,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法保存局部截图", str(exc))
            return
        self._refresh_items()
        self._select_item(excerpt.item_id)
        self.statusBar().showMessage("局部截图已保存，并保留原图区域引用。", 5000)

    def _refresh_project_references(self, item_id: str) -> None:
        self.project_reference_list.clear()
        if self._store is None:
            return
        for reference in self._store.state.project_references:
            if reference.item_id != item_id:
                continue
            row = QListWidgetItem(
                f"{reference.project_title or Path(reference.project_path).name}\n"
                f"{reference.module_id or reference.project_type}"
            )
            row.setData(Qt.ItemDataRole.UserRole, reference.reference_id)
            row.setToolTip(reference.project_path)
            self.project_reference_list.addItem(row)

    def _add_project_reference(self) -> None:
        if self._store is None or self._current_item_id is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "选择要引用的 GATalk 项目")
        if not folder:
            return
        try:
            project = detect_gatalk_project(folder)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法建立项目引用", str(exc))
            return
        note, accepted = QInputDialog.getText(
            self,
            "项目引用说明",
            "这项资料在该项目中的用途（可留空）",
        )
        if not accepted:
            return
        self._store.add_project_reference(
            self._current_item_id,
            project_type=project.project_type,
            project_id=project.project_id,
            project_title=project.title,
            project_path=project.path,
            module_id=project.module_id,
            note=note,
        )
        self._refresh_project_references(self._current_item_id)

    def _remove_project_reference(self) -> None:
        if self._store is None:
            return
        row = self.project_reference_list.currentItem()
        if row is None:
            return
        self._store.remove_project_reference(
            str(row.data(Qt.ItemDataRole.UserRole))
        )
        if self._current_item_id:
            self._refresh_project_references(self._current_item_id)

    def _translation_provider_changed(self, *_args) -> None:
        provider_id = str(self.translation_provider.currentData() or "")
        if not provider_id:
            return
        provider = self._provider_registry.get(provider_id)
        self.translation_model.setText(
            provider.manifest.model_for(ProviderCapability.STRUCTURED_OUTPUT)
        )
        try:
            credential = self._credential_store.get(
                provider.manifest.credential_target
            )
        except OSError:
            credential = None
        self.translation_key.setText(credential or "")

    def _save_translation_credential(self) -> None:
        provider_id = str(self.translation_provider.currentData() or "")
        if not provider_id:
            return
        provider = self._provider_registry.get(provider_id)
        credential = self.translation_key.text().strip()
        if provider_id == "mock":
            self.translation_status.setText("离线 Mock 不需要 API Key。")
            return
        if not credential:
            QMessageBox.information(self, "API Key 为空", "请先填写 API Key。")
            return
        try:
            self._credential_store.set(
                provider.manifest.credential_target,
                credential,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法保存系统凭据", str(exc))
            return
        self.translation_status.setText("API Key 已保存到 Windows 系统凭据。")

    def _start_translation(self) -> None:
        if self._store is None or self._current_item_id is None:
            QMessageBox.information(self, "尚未选择资料", "请先选择一项资料。")
            return
        text = self.original_text_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "没有待翻译原文", "请先粘贴需要翻译的原文。")
            return
        provider_id = str(self.translation_provider.currentData() or "")
        provider = self._provider_registry.get(provider_id)
        model_id = self.translation_model.text().strip()
        credential = self.translation_key.text().strip()
        if provider_id != "mock" and not credential:
            QMessageBox.information(self, "缺少 API Key", "请填写或从系统凭据加载 API Key。")
            return
        answer = QMessageBox.question(
            self,
            "确认发送翻译原文",
            f"将向 {provider.manifest.display_name} / {model_id} 发送 "
            f"{len(text)} 个字符。不会发送图片、资料库路径、项目路径或 API Key。\n\n"
            "继续发送？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        request = create_translation_request(
            text,
            model_id=model_id,
            user_initiated=True,
            disclosure_confirmed=True,
        )
        self._translation_item_id = self._current_item_id
        self._translation_job = self._execution.submit_structured(
            provider,
            request,
            credential,
        )
        self.translate_button.setEnabled(False)
        self.cancel_translation_button.setEnabled(True)
        self.translation_status.setText("正在翻译…")
        QTimer.singleShot(100, self._poll_translation)

    def _poll_translation(self) -> None:
        job = self._translation_job
        if job is None:
            return
        if not job.future.done():
            QTimer.singleShot(100, self._poll_translation)
            return
        self._translation_job = None
        self.translate_button.setEnabled(True)
        self.cancel_translation_button.setEnabled(False)
        try:
            response = job.future.result()
            result = validate_translation_output(response.output)
        except ProviderError as exc:
            self.translation_status.setText("翻译失败。")
            QMessageBox.warning(self, "翻译失败", exc.to_user_message())
            return
        except (OSError, ValueError) as exc:
            self.translation_status.setText("翻译结果无效。")
            QMessageBox.warning(self, "翻译失败", str(exc))
            return
        item_id = getattr(self, "_translation_item_id", "")
        item = next(
            (value for value in self._store.state.items if value.item_id == item_id),
            None,
        ) if self._store else None
        if item is None or self._store is None:
            return
        notes = []
        if result.terminology_notes:
            notes.append("术语说明：" + "；".join(result.terminology_notes))
        if result.uncertainties:
            notes.append("待确认：" + "；".join(result.uncertainties))
        translated = result.translation
        if notes:
            translated += "\n\n" + "\n".join(notes)
        self._store.update_item(
            replace(
                item,
                original_text=self.original_text_edit.toPlainText().strip()
                if item.item_id == self._current_item_id
                else item.original_text,
                translation_text=translated,
                translation_source="AI 翻译",
                translation_provider_id=response.provider_id,
                translation_model_id=response.model_id,
                translation_updated_at=utc_now(),
            )
        )
        if item.item_id == self._current_item_id:
            self.translation_text_edit.setPlainText(translated)
            self._loaded_translation_text = translated
            self.translation_status.setText(
                f"AI 翻译完成：{response.provider_id}/{response.model_id}。"
                "保存后仍可手动修订。"
            )

    def _cancel_translation(self) -> None:
        if self._translation_job is not None:
            self._translation_job.cancel()
        self.translation_status.setText("正在取消翻译…")

    def _select_item(self, item_id: str) -> None:
        for index in range(self.item_list.count()):
            row = self.item_list.item(index)
            if str(row.data(Qt.ItemDataRole.UserRole)) == item_id:
                self.item_list.setCurrentItem(row)
                return

    def focus_entity(self, entity_type: str, entity_id: str) -> None:
        if entity_type == "knowledge_item" and entity_id:
            self._select_item(entity_id)
        elif entity_type == "visual_board" and entity_id and self._store:
            if entity_id in {
                item.board_id for item in self._store.state.visual_boards
            }:
                self._store.save(
                    replace(self._store.state, selected_board_id=entity_id)
                )
                self._open_visual_board()

    def _save_current(self) -> None:
        if self._store is not None:
            self._save_item_details()
            self._store.save()
            self.statusBar().showMessage("资料库已保存。", 3000)

    def closeEvent(self, event) -> None:
        self._cancel_translation()
        self._execution.close()
        for window in tuple(self._board_windows):
            window.close()
        event.accept()
