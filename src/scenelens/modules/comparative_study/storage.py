from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
from typing import Iterable, Mapping, Any
import uuid

from scenelens.modules.comparative_study.models import (
    ComparativeStudyItem,
    ComparativeStudyState,
)
from scenelens.storage.atomic import atomic_write_json, load_json, stage_asset_copy
from scenelens.storage.project_store import utc_now


FORMAT_ID = "gatalk.comparative_study"
FORMAT_VERSION = 1
ENTRY_FILENAME = "comparison.json"


class ComparativeStudyStore:
    def __init__(self, root: Path, state: ComparativeStudyState) -> None:
        self.root = Path(root)
        self.state = state

    @classmethod
    def create(cls, root: str | Path, title: str) -> ComparativeStudyStore:
        folder = Path(root)
        if folder.exists() and any(folder.iterdir()):
            raise ValueError("所选对照研究目录不是空目录。")
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("assets", "artifacts", "exports", "backups"):
            (folder / name).mkdir(exist_ok=True)
        now = utc_now()
        state = ComparativeStudyState(
            study_id=str(uuid.uuid4()),
            title=title.strip() or "未命名对照研究",
            created_at=now,
            updated_at=now,
        )
        store = cls(folder, state)
        store.save()
        return store

    @classmethod
    def open(cls, root: str | Path) -> ComparativeStudyStore:
        folder = Path(root)
        data = load_json(folder / ENTRY_FILENAME)
        if data.get("format") != FORMAT_ID:
            raise ValueError("所选目录不是 GATalk 对照研究。")
        version = int(data.get("format_version", 0))
        if version > FORMAT_VERSION:
            raise ValueError("对照研究由更高版本 GATalk 创建，当前版本不能写入。")
        store = cls(folder, ComparativeStudyState.from_dict(data["state"]))
        issues = store.integrity_issues()
        if issues:
            raise ValueError("对照研究完整性检查失败：" + "；".join(issues[:3]))
        return store

    def save(self, state: ComparativeStudyState | None = None) -> None:
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
        destination = self.root / "backups" / f"{stamp}-{label}-comparison.json"
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(self.root / ENTRY_FILENAME, destination)
        return destination

    def import_image(
        self,
        source: str | Path,
        *,
        title: str = "",
        source_kind: str = "local_file",
        source_reference: str = "",
    ) -> ComparativeStudyItem:
        source_path = Path(source)
        staged = stage_asset_copy(source_path, self.root / "assets" / ".staging")
        if staged.normalized_extension not in {".png", ".jpg", ".webp"}:
            staged.temporary_path.unlink(missing_ok=True)
            raise ValueError("对照研究只支持 PNG、JPG、JPEG 和 WebP 图片。")
        destination = self.root / "assets" / (
            f"{staged.sha256}{staged.normalized_extension}"
        )
        try:
            if destination.exists():
                if _sha256(destination) != staged.sha256:
                    raise OSError("对照研究资产哈希冲突。")
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
            return existing
        now = utc_now()
        item = ComparativeStudyItem(
            item_id=str(uuid.uuid4()),
            title=title.strip() or source_path.stem,
            relative_path=destination.relative_to(self.root).as_posix(),
            sha256=staged.sha256,
            original_filename=source_path.name,
            source_kind=source_kind,
            source_reference=source_reference,
            created_at=now,
            updated_at=now,
        )
        active = self.state.active_item_ids
        if len(active) < 4:
            active = (*active, item.item_id)
        self.save(
            replace(
                self.state,
                items=(*self.state.items, item),
                active_item_ids=active,
                local_comparison={},
                ai_comparison={},
                ai_run={},
            )
        )
        return item

    def update_item(self, item: ComparativeStudyItem) -> None:
        if item.item_id not in {value.item_id for value in self.state.items}:
            raise ValueError("研究作品不存在。")
        updated = replace(item, updated_at=utc_now())
        self.save(
            replace(
                self.state,
                items=tuple(
                    updated if value.item_id == updated.item_id else value
                    for value in self.state.items
                ),
                local_comparison={},
                ai_comparison={},
            )
        )

    def set_item_analysis(
        self,
        item_id: str,
        analysis: Mapping[str, Any],
    ) -> None:
        item = self.item(item_id)
        self.update_item(replace(item, local_analysis=dict(analysis)))

    def set_active_items(self, item_ids: Iterable[str]) -> None:
        ordered = tuple(dict.fromkeys(str(value) for value in item_ids))
        existing = {item.item_id for item in self.state.items}
        if set(ordered) - existing:
            raise ValueError("选择中包含不存在的作品。")
        if len(ordered) > 6:
            raise ValueError("一次对照最多选择六件作品。")
        self.save(
            replace(
                self.state,
                active_item_ids=ordered,
                local_comparison={},
                ai_comparison={},
                ai_run={},
            )
        )

    def remove_items(self, item_ids: Iterable[str]) -> None:
        selected = set(item_ids)
        self.save(
            replace(
                self.state,
                items=tuple(
                    item for item in self.state.items if item.item_id not in selected
                ),
                active_item_ids=tuple(
                    item_id
                    for item_id in self.state.active_item_ids
                    if item_id not in selected
                ),
                local_comparison={},
                ai_comparison={},
                ai_run={},
            )
        )

    def item(self, item_id: str) -> ComparativeStudyItem:
        try:
            return next(
                item for item in self.state.items if item.item_id == item_id
            )
        except StopIteration as exc:
            raise ValueError("研究作品不存在。") from exc

    def item_path(self, item: ComparativeStudyItem) -> Path:
        target = (self.root / item.relative_path).resolve()
        root = self.root.resolve()
        if target != root and root not in target.parents:
            raise ValueError("研究作品路径越出项目目录。")
        return target

    def integrity_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        item_ids = {item.item_id for item in self.state.items}
        if set(self.state.active_item_ids) - item_ids:
            issues.append("当前选择引用了不存在的作品")
        for item in self.state.items:
            path = self.item_path(item)
            if not path.is_file():
                issues.append(f"作品文件缺失：{item.title}")
            elif _sha256(path) != item.sha256:
                issues.append(f"作品文件哈希改变：{item.title}")
        return tuple(issues)

    def export_report(self, destination: str | Path) -> Path:
        path = Path(destination)
        atomic_write_json(
            path,
            {
                "format": "gatalk.comparative_study.report",
                "format_version": 1,
                "state": self.state.to_dict(),
            },
        )
        return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

