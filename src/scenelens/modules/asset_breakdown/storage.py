from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import uuid

from scenelens.imaging.loader import load_image
from scenelens.modules.asset_breakdown.models import (
    AssetPromptSession,
    AutomaticAssetRun,
    AssetBreakdownState,
    AssetItem,
    GenerationRecord,
    SourceImage,
)
from scenelens.storage.atomic import atomic_write_json, load_json, stage_asset_copy
from scenelens.storage.project_lock import ProjectWriteLock
from scenelens.storage.project_store import utc_now


FORMAT_ID = "scenelens.asset_breakdown"
FORMAT_VERSION = 3
ENTRY_FILENAME = "asset_project.json"


class AssetBreakdownStore:
    def __init__(
        self,
        root: Path,
        state: AssetBreakdownState,
        write_lock: ProjectWriteLock,
    ) -> None:
        self.root = Path(root)
        self.state = state
        self._write_lock = write_lock

    @classmethod
    def create(
        cls,
        root: str | Path,
        title: str,
    ) -> AssetBreakdownStore:
        folder = Path(root)
        if folder.exists() and any(folder.iterdir()):
            raise ValueError("所选资产拆分项目目录不是空目录。")
        folder.mkdir(parents=True, exist_ok=True)
        for name in (
            "assets",
            "artifacts/masks",
            "artifacts/generated",
            "artifacts/boards",
            "artifacts/automatic",
            "backups",
            "exports",
        ):
            (folder / name).mkdir(parents=True, exist_ok=True)
        now = utc_now()
        state = AssetBreakdownState(
            project_id=str(uuid.uuid4()),
            title=title.strip() or "未命名资产拆分项目",
            created_at=now,
            updated_at=now,
        )
        write_lock = ProjectWriteLock.acquire(
            folder,
            state.project_id,
            now,
        )
        store = cls(folder, state, write_lock)
        try:
            store.save()
        except Exception:
            write_lock.release()
            raise
        return store

    @classmethod
    def open(cls, root: str | Path) -> AssetBreakdownStore:
        folder = Path(root)
        data = load_json(folder / ENTRY_FILENAME)
        if data.get("format") != FORMAT_ID:
            raise ValueError("所选目录不是 GATalk 资产拆分项目。")
        version = int(data.get("format_version", 0))
        if version > FORMAT_VERSION:
            raise ValueError(
                "资产拆分项目由更高版本 GATalk 创建，当前版本不能写入。"
            )
        state = AssetBreakdownState.from_dict(data["state"])
        write_lock = ProjectWriteLock.acquire(
            folder,
            state.project_id,
            utc_now(),
        )
        store = cls(folder, state, write_lock)
        try:
            for name in (
                "artifacts/automatic",
                "backups",
            ):
                (folder / name).mkdir(parents=True, exist_ok=True)
            if version < FORMAT_VERSION:
                timestamp = utc_now().replace(":", "-")
                backup = (
                    folder
                    / "backups"
                    / f"asset_project.v{version}.{timestamp}.json"
                )
                shutil.copyfile(folder / ENTRY_FILENAME, backup)
                store.save()
        except Exception:
            write_lock.release()
            raise
        return store

    @property
    def recovered_stale_lock(self) -> bool:
        return self._write_lock.recovered_stale_lock

    def close(self) -> None:
        self._write_lock.release()

    def save(self, state: AssetBreakdownState | None = None) -> None:
        if state is not None:
            self.state = state
        self.state = replace(self.state, updated_at=utc_now())
        atomic_write_json(
            self.root / ENTRY_FILENAME,
            {
                "format": FORMAT_ID,
                "format_version": FORMAT_VERSION,
                "module_schema_version": 3,
                "state": self.state.to_dict(),
            },
        )

    def import_image(
        self,
        source: str | Path,
        role: str,
    ) -> SourceImage:
        if role not in {"main", "reference"}:
            raise ValueError("图片角色只能是 main 或 reference。")
        source_path = Path(source)
        staged = stage_asset_copy(
            source_path,
            self.root / "assets" / ".staging",
        )
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
        loaded = load_image(destination)
        width, height = loaded.working_size
        record = SourceImage(
            image_id=str(uuid.uuid4()),
            role=role,
            relative_path=destination.relative_to(self.root).as_posix(),
            sha256=staged.sha256,
            original_filename=source_path.name,
            width=width,
            height=height,
            imported_at=utc_now(),
        )
        images = list(self.state.source_images)
        if role == "main":
            images = [image for image in images if image.role != "main"]
            self.state = replace(
                self.state,
                assets=(),
                generations=(),
                automatic_runs=(),
                prompt_sessions=(),
                ai_runs=(),
                selected_asset_id="",
                selected_prompt_session_id="",
            )
        images.append(record)
        self.state = replace(self.state, source_images=tuple(images))
        self.save()
        return record

    def image_path(self, image: SourceImage) -> Path:
        return self._safe_path(image.relative_path)

    def artifact_path(self, relative: str) -> Path:
        return self._safe_path(relative)

    def add_or_replace_asset(self, asset: AssetItem) -> None:
        assets = list(self.state.assets)
        for index, existing in enumerate(assets):
            if existing.asset_id == asset.asset_id:
                assets[index] = asset
                break
        else:
            assets.append(asset)
        self.state = replace(self.state, assets=tuple(assets))
        self.save()

    def replace_assets(self, assets: tuple[AssetItem, ...]) -> None:
        self.state = replace(self.state, assets=tuple(assets))
        self.save()

    def delete_asset(self, asset_id: str) -> None:
        retained = tuple(
            replace(asset, parent_asset_id="")
            if asset.parent_asset_id == asset_id
            else asset
            for asset in self.state.assets
            if asset.asset_id != asset_id
        )
        generations = tuple(
            item for item in self.state.generations if item.asset_id != asset_id
        )
        self.state = replace(
            self.state,
            assets=retained,
            generations=generations,
            selected_asset_id=(
                "" if self.state.selected_asset_id == asset_id
                else self.state.selected_asset_id
            ),
        )
        self.save()

    def append_ai_run(self, run: dict) -> None:
        self.state = replace(
            self.state,
            ai_runs=(*self.state.ai_runs, dict(run)),
        )
        self.save()

    def append_generation(self, record: GenerationRecord) -> None:
        self.state = replace(
            self.state,
            generations=(*self.state.generations, record),
        )
        self.save()

    def append_automatic_run(self, run: AutomaticAssetRun) -> None:
        self.state = replace(
            self.state,
            automatic_runs=(*self.state.automatic_runs, run),
        )
        self.save()

    def add_or_replace_prompt_session(
        self,
        session: AssetPromptSession,
    ) -> None:
        sessions = list(self.state.prompt_sessions)
        for index, existing in enumerate(sessions):
            if existing.session_id == session.session_id:
                sessions[index] = session
                break
        else:
            sessions.append(session)
        self.state = replace(
            self.state,
            prompt_sessions=tuple(sessions),
            selected_prompt_session_id=session.session_id,
        )
        self.save()

    def select_prompt_session(self, session_id: str) -> None:
        if session_id and not any(
            item.session_id == session_id
            for item in self.state.prompt_sessions
        ):
            raise ValueError("提示语会话不存在。")
        self.state = replace(
            self.state,
            selected_prompt_session_id=session_id,
        )
        self.save()

    def append_export(self, record: dict) -> None:
        self.state = replace(
            self.state,
            exports=(*self.state.exports, dict(record)),
        )
        self.save()

    def save_artifact(self, relative: str, data: bytes) -> Path:
        path = self._safe_path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
        return path

    def copy_export(self, source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.{uuid.uuid4().hex}.tmp"
        )
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
        return destination

    def _safe_path(self, relative: str) -> Path:
        root = self.root.resolve()
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise ValueError("资产拆分项目路径越出项目目录。")
        return path

    def __enter__(self) -> AssetBreakdownStore:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
