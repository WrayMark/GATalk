from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from scenelens.modules.knowledge_base.models import (
    VisualBoardCard,
    VisualBoardLink,
    VisualReferenceBoard,
)
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.storage.project_store import utc_now


class BoardView(QGraphicsView):
    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            current = self.transform().m11()
            if 0.2 <= current * factor <= 4.0:
                self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)


class BoardCardItem(QGraphicsRectItem):
    def __init__(
        self,
        card: VisualBoardCard,
        image_path: Path | None,
        moved_callback,
    ) -> None:
        super().__init__(0, 0, card.width, card.height)
        self.card_id = card.card_id
        self._moved_callback = moved_callback
        self.setPos(card.x, card.y)
        self.setZValue(card.z_index)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        colour = QColor(card.colour)
        self.setPen(QPen(colour.lighter(130), 2))
        surface = QColor(colour)
        surface.setAlpha(52)
        self.setBrush(surface)
        title = QGraphicsSimpleTextItem(card.title, self)
        title.setBrush(QColor("#F3F5F7"))
        title.setPos(12, 10)
        if image_path is not None and image_path.is_file():
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    int(card.width - 24),
                    int(card.height - 54),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                image = QGraphicsPixmapItem(pixmap, self)
                image.setPos(
                    (card.width - pixmap.width()) / 2,
                    38,
                )
        elif card.note:
            note = QGraphicsSimpleTextItem(card.note[:180], self)
            note.setBrush(QColor("#C7CDD4"))
            note.setPos(12, 42)

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._moved_callback()
        return result


class KnowledgeItemPicker(QDialog):
    def __init__(self, store: KnowledgeLibraryStore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("向资料板添加资料")
        self.resize(680, 520)
        layout = QVBoxLayout(self)
        search = QLineEdit()
        search.setPlaceholderText("搜索标题、作者、标签或笔记…")
        layout.addWidget(search)
        self.list = QListWidget()
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        layout.addWidget(self.list, 1)
        self._store = store
        self._refresh("")
        search.textChanged.connect(self._refresh)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh(self, query: str) -> None:
        selected = set(self.selected_ids())
        self.list.clear()
        for item in self._store.items_for(search=query):
            row = QListWidgetItem(
                f"{item.title}  ·  {item.creator or item.source_type}"
            )
            row.setData(Qt.ItemDataRole.UserRole, item.item_id)
            self.list.addItem(row)
            if item.item_id in selected:
                row.setSelected(True)

    def selected_ids(self) -> tuple[str, ...]:
        return tuple(
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.list.selectedItems()
        )


class VisualBoardWindow(QMainWindow):
    def __init__(
        self,
        store: KnowledgeLibraryStore,
        initial_item_ids: tuple[str, ...] = (),
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._card_items: dict[str, BoardCardItem] = {}
        self._link_items: list[QGraphicsLineItem] = []
        self.setWindowTitle("GATalk — 视觉资料板")
        self.resize(1440, 900)
        self.setMinimumSize(980, 620)
        self._build_ui()
        self._refresh_board_list()
        if not self._store.state.visual_boards:
            self._create_board()
        if initial_item_ids:
            self._add_item_ids(initial_item_ids)

    def _build_ui(self) -> None:
        toolbar = QToolBar("资料板")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addWidget(QLabel("资料板  "))
        self.board_combo = QComboBox()
        self.board_combo.setMinimumWidth(240)
        self.board_combo.currentIndexChanged.connect(self._board_changed)
        toolbar.addWidget(self.board_combo)
        new = QAction("新建", self)
        new.triggered.connect(self._create_board)
        toolbar.addAction(new)
        rename = QAction("重命名", self)
        rename.triggered.connect(self._rename_board)
        toolbar.addAction(rename)
        delete_board = QAction("删除资料板", self)
        delete_board.triggered.connect(self._delete_board)
        toolbar.addAction(delete_board)
        toolbar.addSeparator()
        add_items = QAction("添加资料", self)
        add_items.triggered.connect(self._pick_items)
        toolbar.addAction(add_items)
        add_note = QAction("添加笔记", self)
        add_note.triggered.connect(self._add_note)
        toolbar.addAction(add_note)
        connect = QAction("连接所选", self)
        connect.triggered.connect(self._connect_selected)
        toolbar.addAction(connect)
        arrange = QAction("整理布局", self)
        arrange.triggered.connect(self._arrange_grid)
        toolbar.addAction(arrange)
        toolbar.addSeparator()
        snapshot = QAction("建立快照", self)
        snapshot.triggered.connect(self._snapshot)
        toolbar.addAction(snapshot)
        restore = QAction("恢复快照", self)
        restore.triggered.connect(self._restore_snapshot)
        toolbar.addAction(restore)
        export = QAction("导出 PNG", self)
        export.triggered.connect(self._export_png)
        toolbar.addAction(export)
        save = QAction("保存", self)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.triggered.connect(self._save_board)
        self.addAction(save)
        remove = QAction("删除所选", self)
        remove.setShortcut(QKeySequence.StandardKey.Delete)
        remove.triggered.connect(self._delete_selected)
        self.addAction(remove)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(QLabel("研究目的"))
        self.purpose_edit = QLineEdit()
        self.purpose_edit.setPlaceholderText(
            "例如：比较不同作品如何用雾和亮度层次建立远景。"
        )
        top.addWidget(self.purpose_edit, 1)
        save_button = QPushButton("保存资料板")
        save_button.setProperty("primary", True)
        save_button.clicked.connect(self._save_board)
        top.addWidget(save_button)
        layout.addLayout(top)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-2500, -1800, 5000, 3600)
        self.view = BoardView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        layout.addWidget(self.view, 1)
        help_text = QLabel(
            "拖动卡片排版；Shift 多选；拖动空白处框选；Ctrl+滚轮缩放；"
            "Delete 删除卡片；Ctrl+S 保存。资料原文件不会被修改。"
        )
        help_text.setProperty("role", "muted")
        layout.addWidget(help_text)
        self.setCentralWidget(root)

    def _board(self) -> VisualReferenceBoard | None:
        board_id = str(self.board_combo.currentData() or "")
        return next(
            (
                item for item in self._store.state.visual_boards
                if item.board_id == board_id
            ),
            None,
        )

    def _refresh_board_list(self, selected_id: str = "") -> None:
        target = selected_id or str(self.board_combo.currentData() or "")
        self.board_combo.blockSignals(True)
        self.board_combo.clear()
        for board in self._store.state.visual_boards:
            self.board_combo.addItem(board.title, board.board_id)
        index = self.board_combo.findData(
            target or self._store.state.selected_board_id
        )
        self.board_combo.setCurrentIndex(max(0, index))
        self.board_combo.blockSignals(False)
        self._load_board()

    def _board_changed(self, *_args) -> None:
        self._load_board()

    def _load_board(self) -> None:
        self.scene.clear()
        self._card_items.clear()
        self._link_items.clear()
        board = self._board()
        if board is None:
            self.purpose_edit.clear()
            return
        self.purpose_edit.setText(board.purpose)
        items = {item.item_id: item for item in self._store.state.items}
        for card in board.cards:
            image_path = None
            if card.knowledge_item_id in items:
                image_path = self._store.resolve_item_path(
                    items[card.knowledge_item_id]
                )
            item = BoardCardItem(card, image_path, self._update_links)
            self.scene.addItem(item)
            self._card_items[card.card_id] = item
        self._update_links()

    def _create_board(self) -> None:
        title, accepted = QInputDialog.getText(
            self,
            "新建视觉资料板",
            "资料板名称：",
        )
        if not accepted:
            return
        board = self._store.add_visual_board(title)
        self._refresh_board_list(board.board_id)

    def _rename_board(self) -> None:
        board = self._board()
        if board is None:
            return
        title, accepted = QInputDialog.getText(
            self,
            "重命名视觉资料板",
            "名称：",
            text=board.title,
        )
        if not accepted or not title.strip():
            return
        board = self._store.update_visual_board(
            replace(board, title=title.strip())
        )
        self._refresh_board_list(board.board_id)

    def _delete_board(self) -> None:
        board = self._board()
        if board is None:
            return
        if QMessageBox.question(
            self,
            "删除视觉资料板",
            "删除当前资料板及其快照？资料库中的原始资料不会删除。",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._store.delete_visual_board(board.board_id)
        self._refresh_board_list()

    def _pick_items(self) -> None:
        picker = KnowledgeItemPicker(self._store, self)
        if picker.exec() == QDialog.DialogCode.Accepted:
            self._add_item_ids(picker.selected_ids())

    def _add_item_ids(self, item_ids: tuple[str, ...]) -> None:
        board = self._board()
        if board is None:
            return
        known = {item.item_id: item for item in self._store.state.items}
        existing = {
            card.knowledge_item_id
            for card in board.cards
            if card.knowledge_item_id
        }
        cards = list(board.cards)
        for item_id in item_ids:
            item = known.get(item_id)
            if item is None or item_id in existing:
                continue
            index = len(cards)
            cards.append(
                VisualBoardCard(
                    card_id=str(uuid.uuid4()),
                    card_type="knowledge_item",
                    knowledge_item_id=item_id,
                    title=item.title,
                    note=item.description or item.notes,
                    x=float((index % 4) * 300),
                    y=float((index // 4) * 230),
                    colour="#2F7D8C",
                    z_index=index,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        self._store.update_visual_board(replace(board, cards=tuple(cards)))
        self._load_board()

    def _add_note(self) -> None:
        board = self._board()
        if board is None:
            return
        text, accepted = QInputDialog.getMultiLineText(
            self,
            "添加研究笔记",
            "笔记：",
        )
        if not accepted or not text.strip():
            return
        index = len(board.cards)
        card = VisualBoardCard(
            card_id=str(uuid.uuid4()),
            card_type="note",
            title=text.strip().splitlines()[0][:36],
            note=text.strip(),
            x=float((index % 4) * 300),
            y=float((index // 4) * 230),
            colour="#A86B2A",
            z_index=index,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._store.update_visual_board(
            replace(board, cards=(*board.cards, card))
        )
        self._load_board()

    def _connect_selected(self) -> None:
        board = self._board()
        selected = [
            item
            for item in self.scene.selectedItems()
            if isinstance(item, BoardCardItem)
        ]
        if board is None or len(selected) != 2:
            QMessageBox.information(
                self,
                "选择两张卡片",
                "请用 Shift 选择恰好两张卡片，再建立关系。",
            )
            return
        label, accepted = QInputDialog.getText(
            self,
            "建立资料关系",
            "关系说明（可选）：",
        )
        if not accepted:
            return
        pair = {selected[0].card_id, selected[1].card_id}
        if any(
            {item.source_card_id, item.target_card_id} == pair
            for item in board.links
        ):
            return
        link = VisualBoardLink(
            link_id=str(uuid.uuid4()),
            source_card_id=selected[0].card_id,
            target_card_id=selected[1].card_id,
            label=label.strip(),
            created_at=utc_now(),
        )
        self._store.update_visual_board(
            replace(board, links=(*board.links, link))
        )
        self._load_board()

    def _update_links(self) -> None:
        for item in self._link_items:
            self.scene.removeItem(item)
        self._link_items.clear()
        board = self._board()
        if board is None:
            return
        for link in board.links:
            source = self._card_items.get(link.source_card_id)
            target = self._card_items.get(link.target_card_id)
            if source is None or target is None:
                continue
            source_point = source.sceneBoundingRect().center()
            target_point = target.sceneBoundingRect().center()
            line = QGraphicsLineItem(
                source_point.x(),
                source_point.y(),
                target_point.x(),
                target_point.y(),
            )
            line.setPen(QPen(QColor("#7D8791"), 2, Qt.PenStyle.DashLine))
            line.setZValue(-10)
            self.scene.addItem(line)
            self._link_items.append(line)

    def _save_board(self) -> None:
        board = self._board()
        if board is None:
            return
        cards = []
        for card in board.cards:
            item = self._card_items.get(card.card_id)
            if item is None:
                continue
            cards.append(
                replace(
                    card,
                    x=float(item.pos().x()),
                    y=float(item.pos().y()),
                    updated_at=utc_now(),
                )
            )
        self._store.update_visual_board(
            replace(
                board,
                purpose=self.purpose_edit.text().strip(),
                cards=tuple(cards),
            )
        )
        self.statusBar().showMessage("视觉资料板已保存。", 3500)

    def _delete_selected(self) -> None:
        board = self._board()
        if board is None:
            return
        selected = {
            item.card_id
            for item in self.scene.selectedItems()
            if isinstance(item, BoardCardItem)
        }
        if not selected:
            return
        self._store.update_visual_board(
            replace(
                board,
                cards=tuple(
                    item for item in board.cards if item.card_id not in selected
                ),
                links=tuple(
                    item
                    for item in board.links
                    if item.source_card_id not in selected
                    and item.target_card_id not in selected
                ),
            )
        )
        self._load_board()

    def _arrange_grid(self) -> None:
        board = self._board()
        if board is None:
            return
        cards = tuple(
            replace(
                card,
                x=float((index % 4) * 300),
                y=float((index // 4) * 230),
                updated_at=utc_now(),
            )
            for index, card in enumerate(board.cards)
        )
        self._store.update_visual_board(replace(board, cards=cards))
        self._load_board()
        self.view.fitInView(
            self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _snapshot(self) -> None:
        board = self._board()
        if board is None:
            return
        self._save_board()
        title, accepted = QInputDialog.getText(
            self,
            "建立资料板快照",
            "快照名称：",
            text=f"阶段 {len(board.snapshots) + 1}",
        )
        if not accepted:
            return
        self._store.snapshot_visual_board(board.board_id, title)
        self._refresh_board_list(board.board_id)

    def _restore_snapshot(self) -> None:
        board = self._board()
        if board is None or not board.snapshots:
            QMessageBox.information(self, "没有快照", "当前资料板尚未建立快照。")
            return
        labels = [
            f"{item.title} · {item.created_at[:19].replace('T', ' ')}"
            for item in board.snapshots
        ]
        selected, accepted = QInputDialog.getItem(
            self,
            "恢复资料板快照",
            "快照：",
            labels,
            len(labels) - 1,
            False,
        )
        if not accepted:
            return
        snapshot = board.snapshots[labels.index(selected)]
        if QMessageBox.question(
            self,
            "确认恢复",
            "当前布局会被所选快照替换；历史快照仍会保留。",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._store.update_visual_board(
            replace(board, cards=snapshot.cards, links=snapshot.links)
        )
        self._load_board()

    def _export_png(self) -> None:
        board = self._board()
        if board is None or not board.cards:
            QMessageBox.information(self, "资料板为空", "请先添加资料或笔记。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出视觉资料板",
            f"{board.title}.png",
            "PNG (*.png)",
        )
        if not path:
            return
        bounds = self.scene.itemsBoundingRect().adjusted(-48, -48, 48, 48)
        scale = min(2.0, 4096.0 / max(bounds.width(), bounds.height(), 1.0))
        image = QImage(
            max(1, int(bounds.width() * scale)),
            max(1, int(bounds.height() * scale)),
            QImage.Format.Format_ARGB32,
        )
        image.fill(QColor("#161A20"))
        painter = QPainter(image)
        self.scene.render(painter, QRectF(image.rect()), bounds)
        painter.end()
        if not image.save(path, "PNG"):
            QMessageBox.warning(self, "导出失败", "无法写入所选文件。")
            return
        self.statusBar().showMessage(f"视觉资料板已导出：{path}", 5000)

    def closeEvent(self, event) -> None:
        self._save_board()
        super().closeEvent(event)
