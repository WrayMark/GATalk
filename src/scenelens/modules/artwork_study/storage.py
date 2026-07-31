from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import uuid

from scenelens.modules.artwork_study.models import ArtworkStudyState
from scenelens.storage.atomic import atomic_write_json, load_json, stage_asset_copy
from scenelens.storage.project_store import utc_now


FORMAT_ID = "scenelens.artwork_study"
FORMAT_VERSION = 1
ENTRY_FILENAME = "study.json"


class ArtworkStudyStore:
    def __init__(self, root: Path, state: ArtworkStudyState) -> None:
        self.root = Path(root)
        self.state = state

    @classmethod
    def create(cls, root: str | Path, title: str) -> ArtworkStudyStore:
        folder = Path(root)
        if folder.exists() and any(folder.iterdir()):
            raise ValueError("所选作品研究目录不是空目录。")
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("assets", "artifacts", "exports"):
            (folder / name).mkdir(exist_ok=True)
        now = utc_now()
        state = ArtworkStudyState(
            study_id=str(uuid.uuid4()),
            title=title.strip() or "未命名作品研究",
            created_at=now,
            updated_at=now,
        )
        store = cls(folder, state)
        store.save(state)
        return store

    @classmethod
    def open(cls, root: str | Path) -> ArtworkStudyStore:
        folder = Path(root)
        data = load_json(folder / ENTRY_FILENAME)
        if data.get("format") != FORMAT_ID:
            raise ValueError("所选目录不是 GATalk 作品研究。")
        version = int(data.get("format_version", 0))
        if version > FORMAT_VERSION:
            raise ValueError("作品研究由更高版本 GATalk 创建，当前版本不能打开。")
        return cls(folder, ArtworkStudyState.from_dict(data["state"]))

    def save(self, state: ArtworkStudyState | None = None) -> None:
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

    def import_image(self, source: str | Path) -> ArtworkStudyState:
        source_path = Path(source)
        staged = stage_asset_copy(source_path, self.root / "assets" / ".staging")
        destination = (
            self.root
            / "assets"
            / f"{staged.sha256}{staged.normalized_extension}"
        )
        try:
            if destination.exists():
                if _sha256(destination) != staged.sha256:
                    raise OSError("目标资产哈希冲突。")
                staged.temporary_path.unlink()
            else:
                staged.temporary_path.replace(destination)
        finally:
            staging = self.root / "assets" / ".staging"
            if staging.exists() and not any(staging.iterdir()):
                staging.rmdir()
        relative = destination.relative_to(self.root).as_posix()
        self.state = replace(
            self.state,
            image_relative_path=relative,
            image_sha256=staged.sha256,
            image_filename=source_path.name,
            local_analysis={},
            ai_review={},
            ai_run={},
        )
        self.save()
        return self.state

    def image_path(self) -> Path | None:
        relative = self.state.image_relative_path
        if not relative:
            return None
        path = (self.root / relative).resolve()
        root = self.root.resolve()
        if root != path and root not in path.parents:
            raise ValueError("作品研究图片路径越出研究目录。")
        return path

    def export_review_json(self, destination: str | Path) -> Path:
        path = Path(destination)
        atomic_write_json(
            path,
            {
                "format": "scenelens.artwork_study.review",
                "format_version": 1,
                "study_id": self.state.study_id,
                "title": self.state.title,
                "image_sha256": self.state.image_sha256,
                "local_analysis": dict(self.state.local_analysis),
                "ai_review": dict(self.state.ai_review),
                "ai_run": dict(self.state.ai_run),
                "personal_notes": self.state.personal_notes,
            },
        )
        return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
