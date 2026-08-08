from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
from typing import Iterable
import uuid

from PIL import Image

from scenelens.modules.knowledge_base.models import (
    KnowledgeCollection,
    KnowledgeItem,
    KnowledgeLibraryState,
    KnowledgeProjectReference,
    VisualBoardSnapshot,
    VisualReferenceBoard,
)
from scenelens.imaging.loader import load_image
from scenelens.storage.atomic import atomic_write_json, load_json, stage_asset_copy
from scenelens.storage.project_store import utc_now


FORMAT_ID = "gatalk.knowledge_library"
FORMAT_VERSION = 3
ENTRY_FILENAME = "library.json"


class KnowledgeLibraryStore:
    def __init__(self, root: Path, state: KnowledgeLibraryState) -> None:
        self.root = Path(root)
        self.state = state

    @classmethod
    def create(cls, root: str | Path, title: str) -> KnowledgeLibraryStore:
        folder = Path(root)
        if folder.exists() and any(folder.iterdir()):
            raise ValueError("所选资料库目录不是空目录。")
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("assets", "derived", "documents", "exports", "backups"):
            (folder / name).mkdir(exist_ok=True)
        now = utc_now()
        inbox = KnowledgeCollection(
            collection_id=str(uuid.uuid4()),
            domain_id="art_reference",
            name="待整理",
            created_at=now,
            updated_at=now,
        )
        state = KnowledgeLibraryState(
            library_id=str(uuid.uuid4()),
            title=title.strip() or "参考资料库",
            collections=(inbox,),
            selected_collection_id=inbox.collection_id,
            created_at=now,
            updated_at=now,
        )
        store = cls(folder, state)
        store.save()
        return store

    @classmethod
    def open(cls, root: str | Path) -> KnowledgeLibraryStore:
        folder = Path(root)
        data = load_json(folder / ENTRY_FILENAME)
        if data.get("format") != FORMAT_ID:
            raise ValueError("所选目录不是 GATalk 参考资料库。")
        version = int(data.get("format_version", 0))
        if version > FORMAT_VERSION:
            raise ValueError("资料库由更高版本 GATalk 创建，当前版本不能写入。")
        store = cls(folder, KnowledgeLibraryState.from_dict(data["state"]))
        issues = store.integrity_issues()
        if issues:
            raise ValueError("资料库完整性检查失败：" + "；".join(issues[:3]))
        if version < FORMAT_VERSION:
            backup = folder / "backups" / f"pre-migration-v{version}-library.json"
            backup.parent.mkdir(exist_ok=True)
            if not backup.exists():
                shutil.copy2(folder / ENTRY_FILENAME, backup)
            store.save()
        return store

    def save(self, state: KnowledgeLibraryState | None = None) -> None:
        if state is not None:
            self.state = state
        self.state = replace(self.state, updated_at=utc_now())
        atomic_write_json(
            self.root / ENTRY_FILENAME,
            {
                "format": FORMAT_ID,
                "format_version": FORMAT_VERSION,
                "state": self.state.to_dict(),
            },
        )

    def backup(self, label: str = "manual") -> Path:
        stamp = utc_now().replace(":", "-")
        destination = self.root / "backups" / f"{stamp}-{label}-library.json"
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(self.root / ENTRY_FILENAME, destination)
        return destination

    def add_collection(
        self,
        name: str,
        *,
        domain_id: str = "art_reference",
        parent_id: str | None = None,
    ) -> KnowledgeCollection:
        if parent_id and parent_id not in {
            item.collection_id for item in self.state.collections
        }:
            raise ValueError("上级集合不存在。")
        now = utc_now()
        collection = KnowledgeCollection(
            collection_id=str(uuid.uuid4()),
            domain_id=domain_id,
            name=name.strip() or "未命名集合",
            parent_id=parent_id,
            created_at=now,
            updated_at=now,
        )
        self.save(
            replace(
                self.state,
                collections=(*self.state.collections, collection),
                selected_collection_id=collection.collection_id,
            )
        )
        return collection

    def import_file(
        self,
        source: str | Path,
        *,
        domain_id: str = "art_reference",
        collection_ids: Iterable[str] = (),
        title: str = "",
    ) -> KnowledgeItem:
        source_path = Path(source)
        staged = stage_asset_copy(source_path, self.root / "assets" / ".staging")
        destination = self.root / "assets" / (
            f"{staged.sha256}{staged.normalized_extension}"
        )
        try:
            if destination.exists():
                if _sha256(destination) != staged.sha256:
                    raise OSError("资料库资产哈希冲突。")
                staged.temporary_path.unlink()
            else:
                staged.temporary_path.replace(destination)
        finally:
            staging = self.root / "assets" / ".staging"
            if staging.exists() and not any(staging.iterdir()):
                staging.rmdir()
        existing = next(
            (item for item in self.state.items if item.sha256 == staged.sha256),
            None,
        )
        if existing is not None:
            self.set_memberships(
                existing.item_id,
                set(self.state.memberships.get(existing.item_id, ()))
                | set(collection_ids),
            )
            return existing
        now = utc_now()
        item_type = (
            "image"
            if staged.normalized_extension in {".png", ".jpg", ".webp"}
            else "document"
        )
        item = KnowledgeItem(
            item_id=str(uuid.uuid4()),
            domain_id=domain_id,
            item_type=item_type,
            title=title.strip() or source_path.stem,
            source_kind="local_file",
            source_type=(
                "original_artwork" if item_type == "image" else "document"
            ),
            source_value=source_path.name,
            local_relative_path=destination.relative_to(self.root).as_posix(),
            sha256=staged.sha256,
            original_filename=source_path.name,
            provenance_status="local_import",
            created_at=now,
            updated_at=now,
        )
        memberships = dict(self.state.memberships)
        memberships[item.item_id] = tuple(dict.fromkeys(collection_ids))
        self.save(
            replace(
                self.state,
                items=(*self.state.items, item),
                memberships=memberships,
            )
        )
        return item

    def add_link(
        self,
        url: str,
        title: str,
        *,
        domain_id: str = "art_reference",
        collection_ids: Iterable[str] = (),
        source_type: str = "webpage",
    ) -> KnowledgeItem:
        value = url.strip()
        if not value.startswith(("https://", "http://")):
            raise ValueError("来源链接必须以 http:// 或 https:// 开头。")
        now = utc_now()
        item = KnowledgeItem(
            item_id=str(uuid.uuid4()),
            domain_id=domain_id,
            item_type="web_source",
            title=title.strip() or value,
            source_kind="url",
            source_type=source_type.strip() or "webpage",
            source_value=value,
            provenance_status="unverified",
            created_at=now,
            updated_at=now,
        )
        memberships = dict(self.state.memberships)
        memberships[item.item_id] = tuple(dict.fromkeys(collection_ids))
        self.save(replace(self.state, items=(*self.state.items, item), memberships=memberships))
        return item

    def add_note(
        self,
        title: str,
        *,
        body: str = "",
        collection_ids: Iterable[str] = (),
        project_name: str = "",
    ) -> KnowledgeItem:
        now = utc_now()
        item = KnowledgeItem(
            item_id=str(uuid.uuid4()),
            domain_id="art_reference",
            item_type="project_note",
            title=title.strip() or "未命名项目笔记",
            source_kind="user_note",
            source_type="project_note",
            project_name=project_name.strip(),
            notes=body.strip(),
            provenance_status="user_created",
            created_at=now,
            updated_at=now,
        )
        memberships = dict(self.state.memberships)
        memberships[item.item_id] = tuple(dict.fromkeys(collection_ids))
        self.save(
            replace(
                self.state,
                items=(*self.state.items, item),
                memberships=memberships,
            )
        )
        return item

    def create_image_excerpt(
        self,
        parent_item_id: str,
        normalized_rect: tuple[float, float, float, float],
        *,
        title: str = "",
    ) -> KnowledgeItem:
        parent = next(
            (item for item in self.state.items if item.item_id == parent_item_id),
            None,
        )
        if parent is None or parent.item_type != "image":
            raise ValueError("只有资料库中的图片可以建立局部截图。")
        x, y, width, height = _validated_rect(normalized_rect)
        source = self.resolve_item_path(parent)
        if source is None:
            raise ValueError("原始图片文件不存在。")
        loaded = load_image(source)
        image_height, image_width = loaded.rgb.shape[:2]
        left = max(0, min(image_width - 1, round(x * image_width)))
        top = max(0, min(image_height - 1, round(y * image_height)))
        right = max(left + 1, min(image_width, round((x + width) * image_width)))
        bottom = max(top + 1, min(image_height, round((y + height) * image_height)))
        cropped = loaded.rgb[top:bottom, left:right]
        excerpt_id = str(uuid.uuid4())
        destination = self.root / "derived" / f"{excerpt_id}.png"
        destination.parent.mkdir(exist_ok=True)
        Image.fromarray(cropped, mode="RGB").save(destination, format="PNG")
        digest = _sha256(destination)
        now = utc_now()
        item = KnowledgeItem(
            item_id=excerpt_id,
            domain_id=parent.domain_id,
            item_type="image",
            title=title.strip() or f"{parent.title} · 局部",
            source_kind="derived_crop",
            source_type="image_excerpt",
            source_value=parent.title,
            local_relative_path=destination.relative_to(self.root).as_posix(),
            sha256=digest,
            original_filename=destination.name,
            creator=parent.creator,
            project_name=parent.project_name,
            description=f"来自“{parent.title}”的局部截图。",
            tags=parent.tags,
            provenance_status="local_derived",
            parent_item_id=parent.item_id,
            normalized_rect=(x, y, width, height),
            derived_kind="image_excerpt",
            created_at=now,
            updated_at=now,
        )
        memberships = dict(self.state.memberships)
        memberships[item.item_id] = tuple(
            self.state.memberships.get(parent.item_id, ())
        )
        self.save(
            replace(
                self.state,
                items=(*self.state.items, item),
                memberships=memberships,
            )
        )
        return item

    def add_project_reference(
        self,
        item_id: str,
        *,
        project_type: str,
        project_id: str,
        project_title: str,
        project_path: str,
        module_id: str = "",
        entity_type: str = "project",
        entity_id: str = "",
        note: str = "",
    ) -> KnowledgeProjectReference:
        if item_id not in {item.item_id for item in self.state.items}:
            raise ValueError("资料条目不存在。")
        reference = KnowledgeProjectReference(
            reference_id=str(uuid.uuid4()),
            item_id=item_id,
            project_type=project_type,
            project_id=project_id,
            project_title=project_title,
            project_path=project_path,
            module_id=module_id,
            entity_type=entity_type,
            entity_id=entity_id,
            note=note,
            created_at=utc_now(),
        )
        self.save(
            replace(
                self.state,
                project_references=(*self.state.project_references, reference),
            )
        )
        return reference

    def remove_project_reference(self, reference_id: str) -> None:
        self.save(
            replace(
                self.state,
                project_references=tuple(
                    item
                    for item in self.state.project_references
                    if item.reference_id != reference_id
                ),
            )
        )

    def update_item(self, item: KnowledgeItem) -> None:
        if item.item_id not in {value.item_id for value in self.state.items}:
            raise ValueError("资料条目不存在。")
        updated = replace(item, updated_at=utc_now())
        self.save(
            replace(
                self.state,
                items=tuple(
                    updated if value.item_id == item.item_id else value
                    for value in self.state.items
                ),
            )
        )

    def delete_items(self, item_ids: Iterable[str]) -> None:
        selected = set(item_ids)
        changed = True
        while changed:
            changed = False
            for item in self.state.items:
                if item.parent_item_id in selected and item.item_id not in selected:
                    selected.add(item.item_id)
                    changed = True
        memberships = {
            key: value
            for key, value in self.state.memberships.items()
            if key not in selected
        }
        self.save(
            replace(
                self.state,
                items=tuple(
                    item for item in self.state.items if item.item_id not in selected
                ),
                memberships=memberships,
                project_references=tuple(
                    item
                    for item in self.state.project_references
                    if item.item_id not in selected
                ),
                visual_boards=tuple(
                    replace(
                        board,
                        cards=tuple(
                            card
                            for card in board.cards
                            if card.knowledge_item_id not in selected
                        ),
                        links=tuple(
                            link
                            for link in board.links
                            if link.source_card_id
                            not in {
                                card.card_id
                                for card in board.cards
                                if card.knowledge_item_id in selected
                            }
                            and link.target_card_id
                            not in {
                                card.card_id
                                for card in board.cards
                                if card.knowledge_item_id in selected
                            }
                        ),
                        updated_at=utc_now(),
                    )
                    for board in self.state.visual_boards
                ),
            )
        )

    def add_visual_board(
        self,
        title: str,
        *,
        purpose: str = "",
    ) -> VisualReferenceBoard:
        now = utc_now()
        board = VisualReferenceBoard(
            board_id=str(uuid.uuid4()),
            title=title.strip() or "未命名资料板",
            purpose=purpose.strip(),
            created_at=now,
            updated_at=now,
        )
        self.save(
            replace(
                self.state,
                visual_boards=(*self.state.visual_boards, board),
                selected_board_id=board.board_id,
            )
        )
        return board

    def update_visual_board(
        self,
        board: VisualReferenceBoard,
    ) -> VisualReferenceBoard:
        if board.board_id not in {
            item.board_id for item in self.state.visual_boards
        }:
            raise ValueError("视觉资料板不存在。")
        self._validate_board(board)
        updated = replace(board, updated_at=utc_now())
        self.save(
            replace(
                self.state,
                visual_boards=tuple(
                    updated if item.board_id == board.board_id else item
                    for item in self.state.visual_boards
                ),
                selected_board_id=board.board_id,
            )
        )
        return updated

    def delete_visual_board(self, board_id: str) -> None:
        values = tuple(
            item for item in self.state.visual_boards
            if item.board_id != board_id
        )
        self.save(
            replace(
                self.state,
                visual_boards=values,
                selected_board_id=(values[0].board_id if values else None),
            )
        )

    def snapshot_visual_board(
        self,
        board_id: str,
        title: str,
    ) -> VisualBoardSnapshot:
        board = next(
            (
                item for item in self.state.visual_boards
                if item.board_id == board_id
            ),
            None,
        )
        if board is None:
            raise ValueError("视觉资料板不存在。")
        snapshot = VisualBoardSnapshot(
            snapshot_id=str(uuid.uuid4()),
            title=title.strip() or f"快照 {len(board.snapshots) + 1}",
            cards=board.cards,
            links=board.links,
            created_at=utc_now(),
        )
        self.update_visual_board(
            replace(board, snapshots=(*board.snapshots, snapshot))
        )
        return snapshot

    def _validate_board(self, board: VisualReferenceBoard) -> None:
        item_ids = {item.item_id for item in self.state.items}
        card_ids = {item.card_id for item in board.cards}
        if len(card_ids) != len(board.cards):
            raise ValueError("视觉资料板包含重复卡片标识。")
        for card in board.cards:
            if (
                card.card_type == "knowledge_item"
                and card.knowledge_item_id not in item_ids
            ):
                raise ValueError("视觉资料板引用了不存在的资料。")
        for link in board.links:
            if (
                link.source_card_id not in card_ids
                or link.target_card_id not in card_ids
            ):
                raise ValueError("视觉资料板连线引用了不存在的卡片。")
            if link.source_card_id == link.target_card_id:
                raise ValueError("视觉资料板卡片不能连接自身。")

    def set_memberships(
        self,
        item_id: str,
        collection_ids: Iterable[str],
    ) -> None:
        if item_id not in {item.item_id for item in self.state.items}:
            raise ValueError("资料条目不存在。")
        valid = {item.collection_id for item in self.state.collections}
        requested = tuple(dict.fromkeys(str(value) for value in collection_ids))
        missing = set(requested) - valid
        if missing:
            raise ValueError("集合不存在。")
        memberships = dict(self.state.memberships)
        memberships[item_id] = requested
        self.save(replace(self.state, memberships=memberships))

    def items_for(
        self,
        *,
        domain_id: str | None = None,
        collection_id: str | None = None,
        search: str = "",
    ) -> tuple[KnowledgeItem, ...]:
        query = search.strip().casefold()
        result = []
        for item in self.state.items:
            if domain_id and item.domain_id != domain_id:
                continue
            if collection_id and collection_id not in self.state.memberships.get(
                item.item_id, ()
            ):
                continue
            haystack = " ".join(
                (
                    item.title,
                    item.creator,
                    item.project_name,
                    item.description,
                    item.notes,
                    item.original_text,
                    item.translation_text,
                    item.source_type,
                    *item.tags,
                )
            ).casefold()
            if query and query not in haystack:
                continue
            result.append(item)
        return tuple(sorted(result, key=lambda item: item.updated_at, reverse=True))

    def resolve_item_path(self, item: KnowledgeItem) -> Path | None:
        if not item.local_relative_path:
            return None
        target = (self.root / item.local_relative_path).resolve()
        root = self.root.resolve()
        if target != root and root not in target.parents:
            raise ValueError("资料路径越出资料库。")
        return target

    def integrity_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        item_ids = {item.item_id for item in self.state.items}
        collection_ids = {
            collection.collection_id for collection in self.state.collections
        }
        for collection in self.state.collections:
            if collection.parent_id and collection.parent_id not in collection_ids:
                issues.append(f"集合 {collection.name} 的上级不存在")
        for item_id, memberships in self.state.memberships.items():
            if item_id not in item_ids:
                issues.append(f"集合成员引用了不存在的资料 {item_id}")
            if set(memberships) - collection_ids:
                issues.append(f"资料 {item_id} 引用了不存在的集合")
        for item in self.state.items:
            if item.parent_item_id and item.parent_item_id not in item_ids:
                issues.append(f"局部截图 {item.title} 的来源资料不存在")
            path = self.resolve_item_path(item)
            if path is not None and not path.is_file():
                issues.append(f"资料文件缺失：{item.title}")
        for reference in self.state.project_references:
            if reference.item_id not in item_ids:
                issues.append("跨项目引用指向不存在的资料")
        for board in self.state.visual_boards:
            try:
                self._validate_board(board)
            except ValueError as exc:
                issues.append(f"视觉资料板 {board.title}：{exc}")
        return tuple(issues)

    def export_catalog(self, destination: str | Path) -> Path:
        path = Path(destination)
        atomic_write_json(
            path,
            {
                "format": "gatalk.knowledge_catalog_export",
                "format_version": 2,
                "library_id": self.state.library_id,
                "title": self.state.title,
                "items": [item.to_dict() for item in self.state.items],
                "collections": [item.to_dict() for item in self.state.collections],
                "memberships": {
                    key: list(value)
                    for key, value in self.state.memberships.items()
                },
                "project_references": [
                    item.to_dict() for item in self.state.project_references
                ],
                "visual_boards": [
                    item.to_dict() for item in self.state.visual_boards
                ],
            },
        )
        return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_rect(
    value: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if len(value) != 4:
        raise ValueError("局部截图区域必须包含四个归一化数值。")
    x, y, width, height = (float(item) for item in value)
    if (
        x < 0.0
        or y < 0.0
        or width <= 0.0
        or height <= 0.0
        or x + width > 1.000001
        or y + height > 1.000001
    ):
        raise ValueError("局部截图区域必须位于图片范围内。")
    if width < 0.01 or height < 0.01:
        raise ValueError("局部截图区域过小。")
    return x, y, width, height
