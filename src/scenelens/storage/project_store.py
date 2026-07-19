from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from scenelens import __version__
from scenelens.analysis.models import ImageMeasurements, PaletteColour
from scenelens.analysis.palette import (
    DEFAULT_MAX_SAMPLE_PIXELS,
    DEFAULT_RANDOM_SEED,
)
from scenelens.imaging.loader import (
    LoadedImage,
    is_supported_image,
    load_image,
)
from scenelens.storage.atomic import (
    StagedAsset,
    atomic_write_json,
    cache_key_for,
    canonical_json,
    load_json,
    stage_asset_copy,
)
from scenelens.storage.errors import (
    ProjectFormatError,
    ProjectReadOnlyError,
    ProjectSaveError,
    ProjectVersionError,
    StorageError,
)
from scenelens.storage.migrations import (
    connect_database,
    create_database,
    database_version,
    migrate_database,
)
from scenelens.storage.models import (
    DATABASE_SCHEMA_VERSION,
    MANIFEST_FORMAT,
    MANIFEST_FORMAT_VERSION,
    ArtBrief,
    BriefDocumentRecord,
    BriefDocumentType,
    BriefFieldValue,
    CanvasState,
    ComparisonAnalysisRecord,
    FieldSource,
    ImageAssetRecord,
    ProjectManifest,
    ShotRecord,
    VersionRecord,
    WorkspaceState,
)
from scenelens.storage.project_lock import ProjectWriteLock


MEASUREMENT_ALGORITHM_ID = "scenelens.basic_measurements"
MEASUREMENT_ALGORITHM_VERSION = "1"
VISUAL_REVIEW_MODULE_ID = "scenelens.visual_review"
MEASUREMENT_ANALYZER_ID = "basic_image_measurements"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def default_measurement_parameters(
    palette_colours: int = 8,
    palette_seed: int = DEFAULT_RANDOM_SEED,
    palette_max_samples: int = DEFAULT_MAX_SAMPLE_PIXELS,
) -> dict[str, Any]:
    return {
        "histogram_bins": 256,
        "luminance": "linear-srgb-rec709-to-display-srgb-v1",
        "palette_colours": int(palette_colours),
        "palette_seed": int(palette_seed),
        "palette_max_samples": int(palette_max_samples),
        "palette_space": "Oklab",
    }


class ProjectStore:
    def __init__(
        self,
        root: Path,
        manifest: ProjectManifest,
        *,
        read_only: bool = False,
        write_lock: ProjectWriteLock | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.manifest = manifest
        self.read_only = bool(read_only)
        self._write_lock = write_lock

    @property
    def manifest_path(self) -> Path:
        return self.root / "project.json"

    @property
    def database_path(self) -> Path:
        return self._resolve_relative(self.manifest.database_path)

    @property
    def assets_directory(self) -> Path:
        return self._resolve_relative(self.manifest.assets_path)

    @property
    def artifacts_directory(self) -> Path:
        return self._resolve_relative(self.manifest.artifacts_path)

    @property
    def recovered_stale_lock(self) -> bool:
        return bool(
            self._write_lock is not None
            and self._write_lock.recovered_stale_lock
        )

    @classmethod
    def create(cls, root: Path, name: str) -> ProjectStore:
        project_name = name.strip()
        if not project_name:
            raise ProjectSaveError("项目名称不能为空。")

        target = Path(root).expanduser().resolve()
        if target.exists():
            raise ProjectSaveError("目标项目目录已存在，请选择一个新目录。")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.creating-{uuid.uuid4().hex}")
        now = utc_now()
        manifest = ProjectManifest(
            format=MANIFEST_FORMAT,
            format_version=MANIFEST_FORMAT_VERSION,
            project_id=str(uuid.uuid4()),
            name=project_name,
            created_at=now,
            updated_at=now,
            app_version=__version__,
        )
        try:
            temporary.mkdir()
            for relative in (
                manifest.assets_path,
                manifest.artifacts_path,
                manifest.exports_path,
                manifest.backups_path,
            ):
                (temporary / relative).mkdir(parents=True, exist_ok=True)
            atomic_write_json(temporary / "project.json", manifest.to_dict())
            create_database(
                temporary / manifest.database_path,
                manifest.project_id,
                now,
                __version__,
            )
            os.replace(temporary, target)
        except Exception as exc:
            if temporary.exists():
                shutil.rmtree(temporary)
            if isinstance(exc, ProjectSaveError):
                raise
            raise ProjectSaveError(f"无法创建项目：{exc}") from exc
        try:
            write_lock = ProjectWriteLock.acquire(
                target,
                manifest.project_id,
                utc_now(),
            )
        except Exception as exc:
            raise ProjectSaveError(
                f"项目已创建，但无法取得写锁：{exc}"
            ) from exc
        return cls(target, manifest, write_lock=write_lock)

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        read_only: bool = False,
    ) -> ProjectStore:
        selected = Path(path).expanduser().resolve()
        manifest_path = selected / "project.json" if selected.is_dir() else selected
        if manifest_path.name.lower() != "project.json" or not manifest_path.is_file():
            raise ProjectFormatError("请选择 SceneLens 项目中的 project.json。")
        root = manifest_path.parent
        try:
            manifest = ProjectManifest.from_dict(load_json(manifest_path))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ProjectFormatError(f"无法读取项目清单：{exc}") from exc
        if manifest.format != MANIFEST_FORMAT:
            raise ProjectFormatError("该文件不是 SceneLens 项目清单。")
        if manifest.format_version > MANIFEST_FORMAT_VERSION:
            raise ProjectVersionError(
                "该项目清单来自更高版本的 SceneLens，当前版本不会写入它。"
            )
        if manifest.format_version < 1:
            raise ProjectFormatError("不支持该项目清单版本。")

        store = cls(root, manifest, read_only=read_only)
        store._validate_manifest_paths()
        if not store.database_path.is_file():
            raise ProjectFormatError("项目缺少 project.db。")
        if not read_only:
            store._write_lock = ProjectWriteLock.acquire(
                root,
                manifest.project_id,
                utc_now(),
            )
        try:
            if read_only:
                with connect_database(
                    store.database_path,
                    read_only=True,
                ) as connection:
                    actual_version = database_version(connection)
                if actual_version != DATABASE_SCHEMA_VERSION:
                    raise ProjectVersionError(
                        "该项目需要数据库迁移，不能以只读模式打开；"
                        "请等待拥有写权限的进程完成打开。"
                    )
            else:
                actual_version = migrate_database(
                    store.database_path,
                    manifest.project_id,
                    store.root,
                    manifest.backups_path,
                    utc_now(),
                    __version__,
                )
            store._validate_database_identity()
        except (ProjectVersionError, ProjectFormatError):
            store.close()
            raise
        except Exception as exc:
            store.close()
            raise ProjectFormatError(f"无法打开项目数据库：{exc}") from exc

        if (
            not read_only
            and actual_version != manifest.database_schema_version
        ):
            store.manifest = replace(
                manifest,
                database_schema_version=actual_version,
                updated_at=utc_now(),
                app_version=__version__,
            )
            try:
                atomic_write_json(store.manifest_path, store.manifest.to_dict())
            except OSError as exc:
                raise ProjectSaveError(
                    "数据库已迁移，但无法更新 project.json；备份已保留。"
                ) from exc
        return store

    def save(self) -> None:
        self._ensure_writable()
        self._touch_manifest()

    def rename_project(self, name: str) -> None:
        self._ensure_writable()
        cleaned = name.strip()
        if not cleaned:
            raise ProjectSaveError("项目名称不能为空。")
        previous = self.manifest
        self.manifest = replace(previous, name=cleaned)
        try:
            self._touch_manifest()
        except Exception:
            self.manifest = previous
            raise

    def get_art_brief(self) -> ArtBrief:
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT scene_type, production_stage, target_style, time_weather,
                       target_mood, primary_focus, secondary_focus,
                       preserve_content, main_issues, excluded_review, constraints
                FROM art_briefs
                WHERE project_id = ? AND shot_id IS NULL
                """,
                (self.manifest.project_id,),
            ).fetchone()
        if row is None:
            return ArtBrief()
        return ArtBrief(**dict(row))

    def save_art_brief(self, brief: ArtBrief) -> None:
        self._ensure_writable()
        now = utc_now()
        fields = brief.to_dict()
        with self._write_connection() as connection:
            row = connection.execute(
                """
                SELECT id FROM art_briefs
                WHERE project_id = ? AND shot_id IS NULL
                """,
                (self.manifest.project_id,),
            ).fetchone()
            values = (*fields.values(), now)
            if row is None:
                connection.execute(
                    """
                    INSERT INTO art_briefs(
                        id, project_id, shot_id,
                        scene_type, production_stage, target_style, time_weather,
                        target_mood, primary_focus, secondary_focus,
                        preserve_content, main_issues, excluded_review, constraints,
                        created_at, updated_at
                    ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        self.manifest.project_id,
                        *fields.values(),
                        now,
                        now,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE art_briefs SET
                        scene_type = ?, production_stage = ?, target_style = ?,
                        time_weather = ?, target_mood = ?, primary_focus = ?,
                        secondary_focus = ?, preserve_content = ?, main_issues = ?,
                        excluded_review = ?, constraints = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, row["id"]),
                )
            document = self._ensure_brief_document(
                connection,
                BriefDocumentType.CREATIVE_INTENT,
                now,
            )
            migrated_fields = {
                "scene_type": brief.scene_type,
                "production_stage": brief.production_stage,
                "target_style": brief.target_style,
                "target_moods": brief.target_mood,
                "primary_focus": brief.primary_focus,
                "secondary_focus": brief.secondary_focus,
                "preserve_content": brief.preserve_content,
                "main_issues": brief.main_issues,
                "excluded_review": brief.excluded_review,
                "constraints": brief.constraints,
                "additional_notes": (
                    f"M1A 时间与天气（未拆分）：{brief.time_weather}"
                    if brief.time_weather
                    else ""
                ),
            }
            for field_key, value in migrated_fields.items():
                self._upsert_brief_field(
                    connection,
                    document.id,
                    field_key,
                    BriefFieldValue(
                        value=value,
                        source=FieldSource.USER_REVISION,
                        evidence=(
                            {
                                "legacy_field": "time_weather",
                                "original_value": brief.time_weather,
                            }
                            if field_key == "additional_notes"
                            and brief.time_weather
                            else {"legacy_editor": True}
                        ),
                        user_confirmed=True,
                        updated_at=now,
                    ),
                )
        self._touch_manifest()

    def get_creative_intent_document(
        self,
        shot_id: str | None = None,
    ) -> BriefDocumentRecord | None:
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM visual_review_brief_documents
                WHERE document_type = 'creative_intent'
                  AND project_id = ?
                  AND (
                      (? IS NULL AND shot_id IS NULL)
                      OR shot_id = ?
                  )
                """,
                (self.manifest.project_id, shot_id, shot_id),
            ).fetchone()
        return None if row is None else self._brief_document_from_row(row)

    def ensure_creative_intent_document(
        self,
        shot_id: str | None = None,
    ) -> BriefDocumentRecord:
        self._ensure_writable()
        now = utc_now()
        with self._write_connection() as connection:
            return self._ensure_brief_document(
                connection,
                BriefDocumentType.CREATIVE_INTENT,
                now,
                shot_id=shot_id,
            )

    def get_reference_visual_brief(
        self,
        shot_id: str,
    ) -> BriefDocumentRecord | None:
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT documents.*
                FROM shots
                JOIN visual_review_brief_documents AS documents
                  ON documents.shot_id = shots.id
                 AND documents.asset_id = shots.reference_asset_id
                 AND documents.document_type = 'reference_visual'
                WHERE shots.id = ?
                """,
                (shot_id,),
            ).fetchone()
        return None if row is None else self._brief_document_from_row(row)

    def list_brief_fields(
        self,
        document_id: str,
    ) -> dict[str, BriefFieldValue]:
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT field_key, value_json, source, confidence,
                       evidence_json, user_confirmed, updated_at
                FROM visual_review_brief_fields
                WHERE document_id = ?
                ORDER BY field_key
                """,
                (document_id,),
            ).fetchall()
        result: dict[str, BriefFieldValue] = {}
        for row in rows:
            try:
                value = json.loads(row["value_json"])
                evidence = (
                    None
                    if row["evidence_json"] is None
                    else json.loads(row["evidence_json"])
                )
                source = FieldSource(row["source"])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            result[str(row["field_key"])] = BriefFieldValue(
                value=value,
                source=source,
                confidence=(
                    None
                    if row["confidence"] is None
                    else float(row["confidence"])
                ),
                evidence=evidence,
                user_confirmed=bool(row["user_confirmed"]),
                updated_at=str(row["updated_at"]),
            )
        return result

    def save_brief_field(
        self,
        document_id: str,
        field_key: str,
        field: BriefFieldValue,
    ) -> bool:
        self._ensure_writable()
        cleaned_key = field_key.strip()
        if not cleaned_key:
            raise ProjectSaveError("Brief 字段键不能为空。")
        if field.confidence is not None and not 0.0 <= field.confidence <= 1.0:
            raise ProjectSaveError("Brief 字段可信度必须在 0 到 1 之间。")
        now = utc_now()
        stored = replace(field, updated_at=now)
        with self._write_connection() as connection:
            exists = connection.execute(
                """
                SELECT id FROM visual_review_brief_documents WHERE id = ?
                """,
                (document_id,),
            ).fetchone()
            if exists is None:
                raise ProjectSaveError("找不到要更新的 Brief 文档。")
            changed = self._upsert_brief_field(
                connection,
                document_id,
                cleaned_key,
                stored,
            )
        if changed:
            self._touch_manifest()
        return changed

    def save_brief_fields(
        self,
        document_id: str,
        fields: dict[str, BriefFieldValue],
    ) -> dict[str, bool]:
        self._ensure_writable()
        if any(not key.strip() for key in fields):
            raise ProjectSaveError("Brief 字段键不能为空。")
        for field in fields.values():
            if field.confidence is not None and not 0.0 <= field.confidence <= 1.0:
                raise ProjectSaveError("Brief 字段可信度必须在 0 到 1 之间。")
        now = utc_now()
        changes: dict[str, bool] = {}
        with self._write_connection() as connection:
            exists = connection.execute(
                "SELECT id FROM visual_review_brief_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if exists is None:
                raise ProjectSaveError("找不到要更新的 Brief 文档。")
            for field_key, field in fields.items():
                changes[field_key] = self._upsert_brief_field(
                    connection,
                    document_id,
                    field_key.strip(),
                    replace(field, updated_at=now),
                )
        if any(changes.values()):
            self._touch_manifest()
        return changes

    def mark_reference_brief_analyzed(
        self,
        document_id: str,
        *,
        analyzer_id: str,
        analyzer_version: str,
        analyzed_at: str,
    ) -> None:
        self._ensure_writable()
        with self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE visual_review_brief_documents
                SET analyzer_id = ?, analyzer_version = ?, analyzed_at = ?,
                    status = 'current', updated_at = ?
                WHERE id = ? AND document_type = 'reference_visual'
                """,
                (
                    analyzer_id,
                    analyzer_version,
                    analyzed_at,
                    analyzed_at,
                    document_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ProjectSaveError("找不到参考图视觉简报。")

    def create_shot(self, name: str) -> ShotRecord:
        self._ensure_writable()
        cleaned = name.strip()
        if not cleaned:
            raise ProjectSaveError("Shot 名称不能为空。")
        now = utc_now()
        shot_id = str(uuid.uuid4())
        with self._write_connection() as connection:
            sort_order = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM shots"
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO shots(
                    id, project_id, name, reference_asset_id, sort_order,
                    created_at, updated_at
                ) VALUES (?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    shot_id,
                    self.manifest.project_id,
                    cleaned,
                    sort_order,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE workspace_state
                SET current_shot_id = ?, current_version_id = NULL, updated_at = ?
                WHERE project_id = ?
                """,
                (shot_id, now, self.manifest.project_id),
            )
        self._touch_manifest()
        return ShotRecord(shot_id, cleaned, None, sort_order, now, now)

    def list_shots(self) -> tuple[ShotRecord, ...]:
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, name, reference_asset_id, sort_order, created_at, updated_at
                FROM shots ORDER BY sort_order, created_at
                """
            ).fetchall()
        return tuple(ShotRecord(**dict(row)) for row in rows)

    def get_shot(self, shot_id: str) -> ShotRecord:
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT id, name, reference_asset_id, sort_order, created_at, updated_at
                FROM shots WHERE id = ?
                """,
                (shot_id,),
            ).fetchone()
        if row is None:
            raise ProjectSaveError("找不到指定的 Shot。")
        return ShotRecord(**dict(row))

    def list_versions(self, shot_id: str) -> tuple[VersionRecord, ...]:
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, shot_id, asset_id, ordinal, name, notes, created_at
                FROM versions WHERE shot_id = ? ORDER BY ordinal
                """,
                (shot_id,),
            ).fetchall()
        return tuple(VersionRecord(**dict(row)) for row in rows)

    def get_version(self, version_id: str) -> VersionRecord:
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT id, shot_id, asset_id, ordinal, name, notes, created_at
                FROM versions WHERE id = ?
                """,
                (version_id,),
            ).fetchone()
        if row is None:
            raise ProjectSaveError("找不到指定的 Version。")
        return VersionRecord(**dict(row))

    def import_reference(self, shot_id: str, source: Path) -> ImageAssetRecord:
        self._ensure_writable()
        staged, loaded = self._stage_and_load(source)
        try:
            now = utc_now()
            with self._write_connection() as connection:
                self._require_shot(connection, shot_id)
                asset = self._store_staged_asset(
                    connection,
                    Path(source),
                    staged,
                    loaded,
                    now,
                )
                connection.execute(
                    """
                    UPDATE shots SET reference_asset_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (asset.id, now, shot_id),
                )
                connection.execute(
                    """
                    UPDATE visual_review_brief_documents
                    SET status = 'stale', updated_at = ?
                    WHERE document_type = 'reference_visual'
                      AND shot_id = ? AND asset_id <> ? AND status = 'current'
                    """,
                    (now, shot_id, asset.id),
                )
                connection.execute(
                    """
                    UPDATE visual_review_comparison_analyses
                    SET status = 'stale'
                    WHERE shot_id = ? AND reference_asset_id <> ?
                      AND status = 'complete'
                    """,
                    (shot_id, asset.id),
                )
                connection.execute(
                    """
                    UPDATE visual_review_region_analyses
                    SET status = 'stale'
                    WHERE pair_id IN (
                        SELECT id FROM visual_review_region_pairs
                        WHERE shot_id = ?
                    ) AND reference_image_hash <> ?
                      AND status = 'complete'
                    """,
                    (shot_id, asset.sha256),
                )
                self._ensure_brief_document(
                    connection,
                    BriefDocumentType.REFERENCE_VISUAL,
                    now,
                    shot_id=shot_id,
                    asset=asset,
                )
        finally:
            if staged.temporary_path.exists():
                staged.temporary_path.unlink()
        self._touch_manifest()
        return asset

    def add_version(
        self,
        shot_id: str,
        source: Path,
        name: str | None = None,
        notes: str = "",
    ) -> VersionRecord:
        self._ensure_writable()
        staged, loaded = self._stage_and_load(source)
        try:
            now = utc_now()
            with self._write_connection() as connection:
                self._require_shot(connection, shot_id)
                asset = self._store_staged_asset(
                    connection,
                    Path(source),
                    staged,
                    loaded,
                    now,
                )
                ordinal = int(
                    connection.execute(
                        """
                        SELECT COALESCE(MAX(ordinal), 0) + 1
                        FROM versions WHERE shot_id = ?
                        """,
                        (shot_id,),
                    ).fetchone()[0]
                )
                version_name = (name or f"版本 {ordinal}").strip()
                version_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO versions(
                        id, shot_id, asset_id, ordinal, name, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version_id,
                        shot_id,
                        asset.id,
                        ordinal,
                        version_name,
                        notes,
                        now,
                    ),
                )
                connection.execute(
                    """
                    UPDATE workspace_state
                    SET current_shot_id = ?, current_version_id = ?, updated_at = ?
                    WHERE project_id = ?
                    """,
                    (shot_id, version_id, now, self.manifest.project_id),
                )
        finally:
            if staged.temporary_path.exists():
                staged.temporary_path.unlink()
        self._touch_manifest()
        return VersionRecord(
            version_id,
            shot_id,
            asset.id,
            ordinal,
            version_name,
            notes,
            now,
        )

    def get_asset(self, asset_id: str) -> ImageAssetRecord:
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM image_assets WHERE id = ?",
                (asset_id,),
            ).fetchone()
        if row is None:
            raise ProjectFormatError("项目引用的图片资源不存在。")
        return self._asset_from_row(row)

    def asset_path(self, asset_id: str) -> Path:
        asset = self.get_asset(asset_id)
        path = self._resolve_relative(asset.stored_relpath)
        if not path.is_file():
            raise ProjectFormatError(f"项目资源缺失：{asset.original_filename}")
        return path

    def save_comparison_analysis(
        self,
        shot_id: str,
        version_id: str,
        *,
        module_id: str,
        analyzer_id: str,
        analyzer_version: str,
        parameters: dict[str, Any],
        result: dict[str, Any],
        evidence_type: str,
    ) -> ComparisonAnalysisRecord:
        self._ensure_writable()
        if evidence_type not in {"measurement", "algorithm_inference"}:
            raise ProjectSaveError("对比分析来源类型无效。")
        shot = self.get_shot(shot_id)
        version = self.get_version(version_id)
        if version.shot_id != shot_id or shot.reference_asset_id is None:
            raise ProjectSaveError("对比分析需要同一 Shot 的参考图和截图版本。")
        reference_asset = self.get_asset(shot.reference_asset_id)
        current_asset = self.get_asset(version.asset_id)
        input_hashes = {
            "reference": reference_asset.sha256,
            "current": current_asset.sha256,
        }
        key = cache_key_for(
            {
                "module_id": module_id,
                "analyzer_id": analyzer_id,
                "analyzer_version": analyzer_version,
                "input_hashes": input_hashes,
                "parameters": parameters,
            }
        )
        existing = self.load_comparison_analysis(
            shot_id,
            version_id,
            module_id=module_id,
            analyzer_id=analyzer_id,
            analyzer_version=analyzer_version,
            parameters=parameters,
        )
        if existing is not None:
            return existing
        now = utc_now()
        record_id = str(uuid.uuid4())
        with self._write_connection() as connection:
            connection.execute(
                """
                INSERT INTO visual_review_comparison_analyses(
                    id, shot_id, version_id, module_id, analyzer_id,
                    analyzer_version, reference_asset_id, current_asset_id,
                    reference_sha256, current_sha256, parameters_json,
                    input_hashes_json, cache_key, result_json, evidence_type,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'complete', ?)
                """,
                (
                    record_id,
                    shot_id,
                    version_id,
                    module_id,
                    analyzer_id,
                    analyzer_version,
                    reference_asset.id,
                    current_asset.id,
                    reference_asset.sha256,
                    current_asset.sha256,
                    canonical_json(parameters),
                    canonical_json(input_hashes),
                    key,
                    canonical_json(result),
                    evidence_type,
                    now,
                ),
            )
        return ComparisonAnalysisRecord(
            id=record_id,
            shot_id=shot_id,
            version_id=version_id,
            module_id=module_id,
            analyzer_id=analyzer_id,
            analyzer_version=analyzer_version,
            reference_asset_id=reference_asset.id,
            current_asset_id=current_asset.id,
            reference_sha256=reference_asset.sha256,
            current_sha256=current_asset.sha256,
            parameters=dict(parameters),
            cache_key=key,
            result=dict(result),
            evidence_type=evidence_type,
            status="complete",
            created_at=now,
        )

    def load_comparison_analysis(
        self,
        shot_id: str,
        version_id: str,
        *,
        module_id: str,
        analyzer_id: str,
        analyzer_version: str,
        parameters: dict[str, Any],
    ) -> ComparisonAnalysisRecord | None:
        shot = self.get_shot(shot_id)
        version = self.get_version(version_id)
        if version.shot_id != shot_id or shot.reference_asset_id is None:
            return None
        reference_asset = self.get_asset(shot.reference_asset_id)
        current_asset = self.get_asset(version.asset_id)
        key = cache_key_for(
            {
                "module_id": module_id,
                "analyzer_id": analyzer_id,
                "analyzer_version": analyzer_version,
                "input_hashes": {
                    "reference": reference_asset.sha256,
                    "current": current_asset.sha256,
                },
                "parameters": parameters,
            }
        )
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM visual_review_comparison_analyses
                WHERE cache_key = ? AND status = 'complete'
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        try:
            return ComparisonAnalysisRecord(
                id=str(row["id"]),
                shot_id=str(row["shot_id"]),
                version_id=str(row["version_id"]),
                module_id=str(row["module_id"]),
                analyzer_id=str(row["analyzer_id"]),
                analyzer_version=str(row["analyzer_version"]),
                reference_asset_id=str(row["reference_asset_id"]),
                current_asset_id=str(row["current_asset_id"]),
                reference_sha256=str(row["reference_sha256"]),
                current_sha256=str(row["current_sha256"]),
                parameters=json.loads(row["parameters_json"]),
                cache_key=str(row["cache_key"]),
                result=json.loads(row["result_json"]),
                evidence_type=str(row["evidence_type"]),
                status=str(row["status"]),
                created_at=str(row["created_at"]),
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def get_workspace_state(self) -> WorkspaceState:
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM workspace_state WHERE project_id = ?",
                (self.manifest.project_id,),
            ).fetchone()
        if row is None:
            return WorkspaceState()
        try:
            thresholds = tuple(
                float(value) for value in json.loads(row["five_thresholds_json"])
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            thresholds = WorkspaceState().five_thresholds
        if len(thresholds) != 4:
            thresholds = WorkspaceState().five_thresholds
        return WorkspaceState(
            current_shot_id=row["current_shot_id"],
            current_version_id=row["current_version_id"],
            display_mode=row["display_mode"],
            comparison_mode=row["comparison_mode"],
            ab_role=row["ab_role"],
            sync_views=bool(row["sync_views"]),
            blur_sigma=float(row["blur_sigma"]),
            silhouette_threshold=float(row["silhouette_threshold"]),
            three_threshold_low=float(row["three_threshold_low"]),
            three_threshold_high=float(row["three_threshold_high"]),
            five_thresholds=thresholds,  # type: ignore[arg-type]
            palette_colours=int(row["palette_colours"]),
            palette_seed=int(row["palette_seed"]),
            palette_max_samples=int(row["palette_max_samples"]),
            active_analysis_tab=str(row["active_analysis_tab"]),
            updated_at=row["updated_at"],
        )

    def save_workspace_state(self, state: WorkspaceState) -> None:
        self._ensure_writable()
        now = utc_now()
        with self._write_connection() as connection:
            self._validate_active_selection(
                connection,
                state.current_shot_id,
                state.current_version_id,
            )
            connection.execute(
                """
                UPDATE workspace_state SET
                    current_shot_id = ?, current_version_id = ?,
                    display_mode = ?, comparison_mode = ?, ab_role = ?,
                    sync_views = ?, blur_sigma = ?, silhouette_threshold = ?,
                    three_threshold_low = ?, three_threshold_high = ?,
                    five_thresholds_json = ?, palette_colours = ?,
                    palette_seed = ?, palette_max_samples = ?,
                    active_analysis_tab = ?, updated_at = ?
                WHERE project_id = ?
                """,
                (
                    state.current_shot_id,
                    state.current_version_id,
                    state.display_mode,
                    state.comparison_mode,
                    state.ab_role,
                    int(state.sync_views),
                    float(state.blur_sigma),
                    float(state.silhouette_threshold),
                    float(state.three_threshold_low),
                    float(state.three_threshold_high),
                    canonical_json(list(state.five_thresholds)),
                    int(state.palette_colours),
                    int(state.palette_seed),
                    int(state.palette_max_samples),
                    state.active_analysis_tab,
                    now,
                    self.manifest.project_id,
                ),
            )
        self._touch_manifest()

    def get_canvas_state(
        self,
        role: str,
        shot_id: str,
        version_id: str | None,
    ) -> CanvasState | None:
        query = (
            """
            SELECT role, shot_id, version_id, zoom_factor, center_x, center_y,
                   updated_at
            FROM canvas_states
            WHERE role = 'reference' AND shot_id = ?
            """
            if role == "reference"
            else """
            SELECT role, shot_id, version_id, zoom_factor, center_x, center_y,
                   updated_at
            FROM canvas_states
            WHERE role = 'current' AND version_id = ?
            """
        )
        value = shot_id if role == "reference" else version_id
        if value is None:
            return None
        with self._read_connection() as connection:
            row = connection.execute(query, (value,)).fetchone()
        return None if row is None else CanvasState(**dict(row))

    def save_canvas_state(self, state: CanvasState) -> None:
        self._ensure_writable()
        if state.role not in {"reference", "current"}:
            raise ProjectSaveError("未知画布类型。")
        if state.role == "reference" and state.version_id is not None:
            raise ProjectSaveError("参考画布状态不能绑定 Version。")
        if state.role == "current" and state.version_id is None:
            raise ProjectSaveError("截图画布状态必须绑定 Version。")
        now = utc_now()
        with self._write_connection() as connection:
            existing = connection.execute(
                """
                SELECT id FROM canvas_states
                WHERE (role = 'reference' AND ? = 'reference' AND shot_id = ?)
                   OR (role = 'current' AND ? = 'current' AND version_id = ?)
                """,
                (state.role, state.shot_id, state.role, state.version_id),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO canvas_states(
                        id, shot_id, version_id, role, zoom_factor,
                        center_x, center_y, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        state.shot_id,
                        state.version_id,
                        state.role,
                        float(state.zoom_factor),
                        float(state.center_x),
                        float(state.center_y),
                        now,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE canvas_states SET zoom_factor = ?, center_x = ?,
                        center_y = ?, updated_at = ? WHERE id = ?
                    """,
                    (
                        float(state.zoom_factor),
                        float(state.center_x),
                        float(state.center_y),
                        now,
                        existing["id"],
                    ),
                )

    def save_measurements(
        self,
        asset_id: str,
        measurements: ImageMeasurements,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        self._ensure_writable()
        parameters = parameters or default_measurement_parameters()
        asset = self.get_asset(asset_id)
        key_parts = {
            "module_id": VISUAL_REVIEW_MODULE_ID,
            "analyzer_id": MEASUREMENT_ANALYZER_ID,
            "analyzer_version": MEASUREMENT_ALGORITHM_VERSION,
            "algorithm_id": MEASUREMENT_ALGORITHM_ID,
            "algorithm_version": MEASUREMENT_ALGORITHM_VERSION,
            "input_sha256": asset.sha256,
            "parameters": parameters,
        }
        cache_key = cache_key_for(key_parts)
        with self._read_connection() as connection:
            existing = connection.execute(
                """
                SELECT id FROM analysis_runs
                WHERE cache_key = ? AND status = 'complete'
                """,
                (cache_key,),
            ).fetchone()
        if existing is not None:
            return str(existing["id"])

        run_id = str(uuid.uuid4())
        histogram_payload = {
            "bins": len(measurements.luminance_histogram),
            "values": [
                float(value) for value in measurements.luminance_histogram
            ],
        }
        palette_payload = {
            "sampled_pixel_count": int(measurements.sampled_pixel_count),
            "colours": [
                {
                    "rgb": list(item.rgb),
                    "oklab": list(item.oklab),
                    "proportion": float(item.proportion),
                }
                for item in measurements.palette
            ],
        }
        artifact_relative = (
            Path(self.manifest.artifacts_path)
            / asset_id
            / run_id
            / "measurements.json"
        )
        artifact_payload = {
            "format_version": 1,
            "run_id": run_id,
            "asset_id": asset_id,
            "cache_key": cache_key,
            "parameters": parameters,
            "results": {
                "luminance_histogram": histogram_payload,
                "oklab_palette": palette_payload,
            },
        }
        try:
            atomic_write_json(self.root / artifact_relative, artifact_payload)
        except OSError as exc:
            raise ProjectSaveError(f"无法保存分析产物：{exc}") from exc
        now = utc_now()
        with self._write_connection() as connection:
            connection.execute(
                """
                INSERT INTO analysis_runs(
                    id, asset_id, algorithm_id, algorithm_version,
                    parameters_json, input_sha256, cache_key, status, created_at,
                    module_id, analyzer_id, analyzer_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'complete', ?, ?, ?, ?)
                """,
                (
                    run_id,
                    asset_id,
                    MEASUREMENT_ALGORITHM_ID,
                    MEASUREMENT_ALGORITHM_VERSION,
                    canonical_json(parameters),
                    asset.sha256,
                    cache_key,
                    now,
                    VISUAL_REVIEW_MODULE_ID,
                    MEASUREMENT_ANALYZER_ID,
                    MEASUREMENT_ALGORITHM_VERSION,
                ),
            )
            relative_text = artifact_relative.as_posix()
            connection.executemany(
                """
                INSERT INTO analysis_results(
                    id, analysis_run_id, result_key, evidence_type,
                    payload_json, artifact_relpath
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        str(uuid.uuid4()),
                        run_id,
                        "luminance_histogram",
                        "measurement",
                        canonical_json(histogram_payload),
                        relative_text,
                    ),
                    (
                        str(uuid.uuid4()),
                        run_id,
                        "oklab_palette",
                        "algorithm_inference",
                        canonical_json(palette_payload),
                        relative_text,
                    ),
                ),
            )
        return run_id

    def load_measurements(
        self,
        asset_id: str,
        parameters: dict[str, Any] | None = None,
    ) -> ImageMeasurements | None:
        parameters = parameters or default_measurement_parameters()
        asset = self.get_asset(asset_id)
        cache_key = cache_key_for(
            {
                "module_id": VISUAL_REVIEW_MODULE_ID,
                "analyzer_id": MEASUREMENT_ANALYZER_ID,
                "analyzer_version": MEASUREMENT_ALGORITHM_VERSION,
                "algorithm_id": MEASUREMENT_ALGORITHM_ID,
                "algorithm_version": MEASUREMENT_ALGORITHM_VERSION,
                "input_sha256": asset.sha256,
                "parameters": parameters,
            }
        )
        legacy_cache_key = cache_key_for(
            {
                "algorithm_id": MEASUREMENT_ALGORITHM_ID,
                "algorithm_version": MEASUREMENT_ALGORITHM_VERSION,
                "input_sha256": asset.sha256,
                "parameters": parameters,
            }
        )
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT analysis_results.result_key,
                       analysis_results.payload_json,
                       analysis_results.artifact_relpath,
                       analysis_runs.id AS run_id,
                       analysis_runs.cache_key,
                       analysis_runs.parameters_json
                FROM analysis_results
                JOIN analysis_runs
                  ON analysis_runs.id = analysis_results.analysis_run_id
                WHERE analysis_results.analysis_run_id = (
                    SELECT id FROM analysis_runs
                    WHERE cache_key IN (?, ?) AND status = 'complete'
                    ORDER BY CASE cache_key WHEN ? THEN 0 ELSE 1 END
                    LIMIT 1
                )
                """,
                (cache_key, legacy_cache_key, cache_key),
            ).fetchall()
        if not rows:
            return None
        try:
            payloads = {
                str(row["result_key"]): json.loads(row["payload_json"])
                for row in rows
            }
            histogram = np.asarray(
                payloads["luminance_histogram"]["values"],
                dtype=np.float64,
            )
            palette_data = payloads["oklab_palette"]
            palette = tuple(
                PaletteColour(
                    rgb=tuple(int(value) for value in item["rgb"]),
                    oklab=tuple(float(value) for value in item["oklab"]),
                    proportion=float(item["proportion"]),
                )
                for item in palette_data["colours"]
            )
            measurements = ImageMeasurements(
                luminance_histogram=histogram,
                palette=palette,
                sampled_pixel_count=int(palette_data["sampled_pixel_count"]),
            )
            artifact_relpath = rows[0]["artifact_relpath"]
            if artifact_relpath:
                artifact_path = self._resolve_relative(str(artifact_relpath))
                artifact_valid = False
                if artifact_path.is_file():
                    try:
                        artifact_data = load_json(artifact_path)
                        artifact_valid = (
                            artifact_data.get("cache_key") == rows[0]["cache_key"]
                        )
                    except (OSError, ValueError, json.JSONDecodeError):
                        artifact_valid = False
                if not artifact_valid:
                    atomic_write_json(
                        artifact_path,
                        {
                            "format_version": 1,
                            "run_id": rows[0]["run_id"],
                            "asset_id": asset_id,
                            "cache_key": rows[0]["cache_key"],
                            "parameters": json.loads(
                                rows[0]["parameters_json"]
                            ),
                            "results": payloads,
                        },
                    )
            return measurements
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
            return None

    def _stage_and_load(self, source: Path) -> tuple[StagedAsset, LoadedImage]:
        source_path = Path(source)
        if not source_path.is_file():
            raise ProjectSaveError("找不到要导入的图片。")
        if not is_supported_image(source_path):
            raise ProjectSaveError("仅支持 PNG、JPG、JPEG 和 WebP 图片。")
        staging = self.assets_directory / "originals" / ".staging"
        staged: StagedAsset | None = None
        try:
            staged = stage_asset_copy(source_path, staging)
            loaded = load_image(staged.temporary_path)
            return staged, loaded
        except Exception as exc:
            if staged is not None and staged.temporary_path.exists():
                staged.temporary_path.unlink()
            raise ProjectSaveError(f"无法导入图片：{exc}") from exc

    def _store_staged_asset(
        self,
        connection: sqlite3.Connection,
        source: Path,
        staged: StagedAsset,
        loaded: LoadedImage,
        now: str,
    ) -> ImageAssetRecord:
        existing = connection.execute(
            "SELECT * FROM image_assets WHERE sha256 = ?",
            (staged.sha256,),
        ).fetchone()
        if existing is not None:
            return self._asset_from_row(existing)

        relative = (
            Path(self.manifest.assets_path)
            / "originals"
            / staged.sha256[:2]
            / f"{staged.sha256}{staged.normalized_extension}"
        )
        final_path = self.root / relative
        final_path.parent.mkdir(parents=True, exist_ok=True)
        if final_path.exists():
            staged.temporary_path.unlink()
        else:
            os.replace(staged.temporary_path, final_path)

        asset = ImageAssetRecord(
            id=str(uuid.uuid4()),
            sha256=staged.sha256,
            original_filename=source.name,
            stored_relpath=relative.as_posix(),
            byte_size=staged.byte_size,
            media_type=self._media_type(loaded.source_format),
            source_format=loaded.source_format,
            width=loaded.working_size[0],
            height=loaded.working_size[1],
            exif_orientation=loaded.exif_orientation,
            icc_status=(
                "converted_to_srgb"
                if loaded.icc_converted_to_srgb
                else "assumed_srgb"
            ),
            imported_at=now,
        )
        connection.execute(
            """
            INSERT INTO image_assets(
                id, sha256, original_filename, stored_relpath, byte_size,
                media_type, source_format, width, height, exif_orientation,
                icc_status, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset.id,
                asset.sha256,
                asset.original_filename,
                asset.stored_relpath,
                asset.byte_size,
                asset.media_type,
                asset.source_format,
                asset.width,
                asset.height,
                asset.exif_orientation,
                asset.icc_status,
                asset.imported_at,
            ),
        )
        return asset

    def _ensure_brief_document(
        self,
        connection: sqlite3.Connection,
        document_type: BriefDocumentType,
        now: str,
        *,
        shot_id: str | None = None,
        asset: ImageAssetRecord | None = None,
    ) -> BriefDocumentRecord:
        if document_type is BriefDocumentType.REFERENCE_VISUAL:
            if shot_id is None or asset is None:
                raise ProjectSaveError("参考图视觉简报必须绑定 Shot 和参考图片。")
            row = connection.execute(
                """
                SELECT * FROM visual_review_brief_documents
                WHERE document_type = 'reference_visual'
                  AND shot_id = ? AND asset_id = ?
                """,
                (shot_id, asset.id),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT * FROM visual_review_brief_documents
                WHERE document_type = 'creative_intent'
                  AND project_id = ?
                  AND (
                      (? IS NULL AND shot_id IS NULL)
                      OR shot_id = ?
                  )
                """,
                (self.manifest.project_id, shot_id, shot_id),
            ).fetchone()
        if row is not None:
            return self._brief_document_from_row(row)

        document_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO visual_review_brief_documents(
                id, document_type, project_id, shot_id, asset_id, asset_sha256,
                analyzer_id, analyzer_version, analyzed_at, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 'current', ?, ?)
            """,
            (
                document_id,
                document_type.value,
                self.manifest.project_id,
                shot_id,
                None if asset is None else asset.id,
                None if asset is None else asset.sha256,
                now,
                now,
            ),
        )
        created = connection.execute(
            "SELECT * FROM visual_review_brief_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if created is None:
            raise ProjectSaveError("创建 Brief 文档失败。")
        return self._brief_document_from_row(created)

    @staticmethod
    def _upsert_brief_field(
        connection: sqlite3.Connection,
        document_id: str,
        field_key: str,
        field: BriefFieldValue,
    ) -> bool:
        existing = connection.execute(
            """
            SELECT source, user_confirmed
            FROM visual_review_brief_fields
            WHERE document_id = ? AND field_key = ?
            """,
            (document_id, field_key),
        ).fetchone()
        generated_sources = {
            FieldSource.AUTOMATIC_MEASUREMENT.value,
            FieldSource.ALGORITHM_INFERENCE.value,
            FieldSource.AI_ANALYSIS.value,
        }
        if (
            existing is not None
            and field.source.value in generated_sources
            and (
                bool(existing["user_confirmed"])
                or existing["source"]
                in {
                    FieldSource.USER_INPUT.value,
                    FieldSource.USER_REVISION.value,
                }
            )
        ):
            return False
        value_json = canonical_json(field.value)
        evidence_json = (
            None if field.evidence is None else canonical_json(field.evidence)
        )
        if existing is None:
            connection.execute(
                """
                INSERT INTO visual_review_brief_fields(
                    id, document_id, field_key, value_json, source, confidence,
                    evidence_json, user_confirmed, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    document_id,
                    field_key,
                    value_json,
                    field.source.value,
                    field.confidence,
                    evidence_json,
                    int(field.user_confirmed),
                    field.updated_at,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE visual_review_brief_fields
                SET value_json = ?, source = ?, confidence = ?,
                    evidence_json = ?, user_confirmed = ?, updated_at = ?
                WHERE document_id = ? AND field_key = ?
                """,
                (
                    value_json,
                    field.source.value,
                    field.confidence,
                    evidence_json,
                    int(field.user_confirmed),
                    field.updated_at,
                    document_id,
                    field_key,
                ),
            )
        connection.execute(
            """
            UPDATE visual_review_brief_documents
            SET updated_at = ? WHERE id = ?
            """,
            (field.updated_at, document_id),
        )
        return True

    @staticmethod
    def _brief_document_from_row(row: sqlite3.Row) -> BriefDocumentRecord:
        return BriefDocumentRecord(
            id=str(row["id"]),
            document_type=BriefDocumentType(str(row["document_type"])),
            project_id=str(row["project_id"]),
            shot_id=row["shot_id"],
            asset_id=row["asset_id"],
            asset_sha256=row["asset_sha256"],
            analyzer_id=row["analyzer_id"],
            analyzer_version=row["analyzer_version"],
            analyzed_at=row["analyzed_at"],
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _media_type(source_format: str) -> str:
        return {
            "PNG": "image/png",
            "JPEG": "image/jpeg",
            "JPG": "image/jpeg",
            "WEBP": "image/webp",
        }.get(source_format.upper(), "application/octet-stream")

    @staticmethod
    def _asset_from_row(row: sqlite3.Row) -> ImageAssetRecord:
        return ImageAssetRecord(
            id=row["id"],
            sha256=row["sha256"],
            original_filename=row["original_filename"],
            stored_relpath=row["stored_relpath"],
            byte_size=int(row["byte_size"]),
            media_type=row["media_type"],
            source_format=row["source_format"],
            width=int(row["width"]),
            height=int(row["height"]),
            exif_orientation=row["exif_orientation"],
            icc_status=row["icc_status"],
            imported_at=row["imported_at"],
        )

    def _require_shot(
        self, connection: sqlite3.Connection, shot_id: str
    ) -> None:
        row = connection.execute(
            "SELECT 1 FROM shots WHERE id = ?",
            (shot_id,),
        ).fetchone()
        if row is None:
            raise ProjectSaveError("找不到指定的 Shot。")

    @staticmethod
    def _validate_active_selection(
        connection: sqlite3.Connection,
        shot_id: str | None,
        version_id: str | None,
    ) -> None:
        if version_id is None:
            return
        row = connection.execute(
            "SELECT shot_id FROM versions WHERE id = ?",
            (version_id,),
        ).fetchone()
        if row is None or shot_id is None or row["shot_id"] != shot_id:
            raise ProjectSaveError("当前 Version 不属于所选 Shot。")

    def _validate_database_identity(self) -> None:
        with self._read_connection() as connection:
            row = connection.execute(
                "SELECT id FROM project_identity WHERE singleton = 1"
            ).fetchone()
            current = database_version(connection)
        if row is None or row["id"] != self.manifest.project_id:
            raise ProjectFormatError("project.json 与 project.db 的项目 ID 不一致。")
        if current != DATABASE_SCHEMA_VERSION:
            raise ProjectFormatError("项目数据库迁移未完成。")

    def _validate_manifest_paths(self) -> None:
        for relative in (
            self.manifest.database_path,
            self.manifest.assets_path,
            self.manifest.artifacts_path,
            self.manifest.exports_path,
            self.manifest.backups_path,
        ):
            self._resolve_relative(relative)

    def _resolve_relative(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ProjectFormatError("项目清单包含不安全的路径。")
        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ProjectFormatError("项目清单路径逃逸项目目录。") from exc
        return resolved

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = connect_database(
                self.database_path,
                read_only=self.read_only,
            )
        except (OSError, sqlite3.Error) as exc:
            raise ProjectFormatError(f"无法读取项目数据库：{exc}") from exc
        try:
            yield connection
        except (OSError, sqlite3.Error) as exc:
            raise ProjectFormatError(f"无法读取项目数据库：{exc}") from exc
        finally:
            connection.close()

    @contextmanager
    def module_read_connection(
        self,
        module_id: str,
    ) -> Iterator[sqlite3.Connection]:
        with self._read_connection() as connection:
            self._require_registered_module(connection, module_id)
            yield connection

    @contextmanager
    def module_write_connection(
        self,
        module_id: str,
    ) -> Iterator[sqlite3.Connection]:
        with self._write_connection() as connection:
            try:
                self._require_registered_module(connection, module_id)
            except ProjectFormatError as exc:
                raise ProjectSaveError(str(exc)) from exc
            yield connection

    @contextmanager
    def workspace_read_connection(self) -> Iterator[sqlite3.Connection]:
        with self._read_connection() as connection:
            yield connection

    @contextmanager
    def workspace_write_connection(self) -> Iterator[sqlite3.Connection]:
        with self._write_connection() as connection:
            yield connection

    @staticmethod
    def _require_registered_module(
        connection: sqlite3.Connection,
        module_id: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT 1 FROM module_schema_versions WHERE module_id = ?
            """,
            (module_id,),
        ).fetchone()
        if row is None:
            raise ProjectFormatError(f"项目未注册模块：{module_id}")

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        self._ensure_writable()
        try:
            connection = connect_database(self.database_path)
        except (OSError, sqlite3.Error) as exc:
            raise ProjectSaveError(f"无法写入项目数据库：{exc}") from exc
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if isinstance(exc, StorageError):
                raise
            raise ProjectSaveError(f"项目数据保存失败：{exc}") from exc
        finally:
            connection.close()

    def _touch_manifest(self) -> None:
        self._ensure_writable()
        previous = self.manifest
        self.manifest = replace(
            previous,
            updated_at=utc_now(),
            app_version=__version__,
            database_schema_version=DATABASE_SCHEMA_VERSION,
        )
        try:
            atomic_write_json(self.manifest_path, self.manifest.to_dict())
        except OSError as exc:
            self.manifest = previous
            raise ProjectSaveError(
                "项目数据已写入，但 project.json 更新失败；请检查磁盘和权限后重试保存。"
            ) from exc

    def close(self) -> None:
        if self._write_lock is not None:
            self._write_lock.release()
            self._write_lock = None

    def __enter__(self) -> ProjectStore:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    def _ensure_writable(self) -> None:
        if self.read_only:
            raise ProjectReadOnlyError(
                "项目以只读模式打开，当前操作不会写入任何项目文件。"
            )
        if self._write_lock is None:
            raise ProjectReadOnlyError(
                "项目写锁已释放，当前操作不会写入任何项目文件。"
            )
