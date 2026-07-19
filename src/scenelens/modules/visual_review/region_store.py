from __future__ import annotations

import sqlite3
import uuid
import json
from dataclasses import replace
from typing import Any

from scenelens.modules.visual_review import MODULE_ID
from scenelens.modules.visual_review.regions import (
    NormalizedRect,
    RegionPairRecord,
    RegionPairView,
    RegionRecord,
    RegionAnalysisRecord,
    validate_region_size,
)
from scenelens.storage.errors import ProjectSaveError
from scenelens.storage.atomic import canonical_json
from scenelens.storage.project_store import ProjectStore, utc_now


class RegionStore:
    def __init__(self, project: ProjectStore) -> None:
        self.project = project

    def create_region(
        self,
        shot_id: str,
        image_role: str,
        version_id: str | None,
        name: str,
        semantic_type: str,
        rect: NormalizedRect,
    ) -> RegionRecord:
        validate_region_size(rect)
        self._validate_role_selection(shot_id, image_role, version_id)
        cleaned_name = name.strip()
        cleaned_semantic = semantic_type.strip()
        if not cleaned_name:
            raise ProjectSaveError("区域名称不能为空。")
        if not cleaned_semantic:
            raise ProjectSaveError("区域语义不能为空。")
        now = utc_now()
        region = RegionRecord(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            shot_id=shot_id,
            image_role=image_role,
            version_id=version_id,
            name=cleaned_name,
            semantic_type=cleaned_semantic,
            normalized_rect=rect,
            created_at=now,
            updated_at=now,
        )
        with self.project.module_write_connection(MODULE_ID) as connection:
            self._insert_region(connection, region)
        return region

    def list_regions(
        self,
        shot_id: str,
        *,
        version_id: str | None = None,
    ) -> tuple[RegionRecord, ...]:
        with self.project.module_read_connection(MODULE_ID) as connection:
            rows = connection.execute(
                """
                SELECT * FROM visual_review_regions
                WHERE shot_id = ?
                  AND (
                    image_role = 'reference'
                    OR (image_role = 'current' AND version_id = ?)
                  )
                ORDER BY image_role DESC, created_at, id
                """,
                (shot_id, version_id),
            ).fetchall()
        return tuple(self._region_from_row(row) for row in rows)

    def get_region(self, region_id: str) -> RegionRecord:
        with self.project.module_read_connection(MODULE_ID) as connection:
            row = connection.execute(
                "SELECT * FROM visual_review_regions WHERE id = ?",
                (region_id,),
            ).fetchone()
        if row is None:
            raise ProjectSaveError("找不到指定区域。")
        return self._region_from_row(row)

    def update_region(
        self,
        region_id: str,
        *,
        rect: NormalizedRect | None = None,
        name: str | None = None,
        semantic_type: str | None = None,
    ) -> RegionRecord:
        current = self.get_region(region_id)
        updated_rect = current.normalized_rect if rect is None else rect
        validate_region_size(updated_rect)
        updated = replace(
            current,
            normalized_rect=updated_rect,
            name=current.name if name is None else name.strip(),
            semantic_type=(
                current.semantic_type
                if semantic_type is None
                else semantic_type.strip()
            ),
            updated_at=utc_now(),
        )
        if not updated.name or not updated.semantic_type:
            raise ProjectSaveError("区域名称和语义不能为空。")
        with self.project.module_write_connection(MODULE_ID) as connection:
            connection.execute(
                """
                UPDATE visual_review_regions
                SET name = ?, semantic_type = ?, rect_x = ?, rect_y = ?,
                    rect_width = ?, rect_height = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.name,
                    updated.semantic_type,
                    updated.normalized_rect.x,
                    updated.normalized_rect.y,
                    updated.normalized_rect.width,
                    updated.normalized_rect.height,
                    updated.updated_at,
                    region_id,
                ),
            )
            self._mark_region_analyses_stale(connection, region_id)
        return updated

    def delete_region(self, region_id: str) -> None:
        with self.project.module_write_connection(MODULE_ID) as connection:
            cursor = connection.execute(
                "DELETE FROM visual_review_regions WHERE id = ?",
                (region_id,),
            )
            if cursor.rowcount != 1:
                raise ProjectSaveError("找不到要删除的区域。")

    def create_pair(
        self,
        reference_region_id: str,
        current_region_id: str,
        name: str,
        semantic_type: str,
        notes: str = "",
    ) -> RegionPairRecord:
        reference = self.get_region(reference_region_id)
        current = self.get_region(current_region_id)
        if reference.image_role != "reference" or current.image_role != "current":
            raise ProjectSaveError("区域对必须由一个参考区域和一个当前区域组成。")
        if reference.shot_id != current.shot_id:
            raise ProjectSaveError("区域对的两侧必须属于同一个 Shot。")
        now = utc_now()
        pair = RegionPairRecord(
            id=str(uuid.uuid4()),
            shot_id=reference.shot_id,
            reference_region_id=reference.id,
            current_region_id=current.id,
            name=name.strip(),
            semantic_type=semantic_type.strip(),
            notes=notes.strip(),
            created_at=now,
            updated_at=now,
        )
        if not pair.name or not pair.semantic_type:
            raise ProjectSaveError("区域对名称和语义不能为空。")
        try:
            with self.project.module_write_connection(MODULE_ID) as connection:
                connection.execute(
                    """
                    INSERT INTO visual_review_region_pairs(
                        id, shot_id, reference_region_id, current_region_id,
                        name, semantic_type, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pair.id,
                        pair.shot_id,
                        pair.reference_region_id,
                        pair.current_region_id,
                        pair.name,
                        pair.semantic_type,
                        pair.notes,
                        pair.created_at,
                        pair.updated_at,
                    ),
                )
        except ProjectSaveError as exc:
            if isinstance(exc.__cause__, sqlite3.IntegrityError):
                raise ProjectSaveError("所选区域已经属于其他区域对。") from exc
            raise
        return pair

    def list_pair_views(
        self,
        shot_id: str,
        version_id: str | None,
    ) -> tuple[RegionPairView, ...]:
        if version_id is None:
            return ()
        with self.project.module_read_connection(MODULE_ID) as connection:
            rows = connection.execute(
                """
                SELECT pairs.*,
                       reference.id AS reference_id,
                       reference.module_id AS reference_module_id,
                       reference.shot_id AS reference_shot_id,
                       reference.image_role AS reference_image_role,
                       reference.version_id AS reference_version_id,
                       reference.name AS reference_name,
                       reference.semantic_type AS reference_semantic_type,
                       reference.rect_x AS reference_rect_x,
                       reference.rect_y AS reference_rect_y,
                       reference.rect_width AS reference_rect_width,
                       reference.rect_height AS reference_rect_height,
                       reference.created_at AS reference_created_at,
                       reference.updated_at AS reference_updated_at,
                       current.id AS current_id,
                       current.module_id AS current_module_id,
                       current.shot_id AS current_shot_id,
                       current.image_role AS current_image_role,
                       current.version_id AS current_version_id,
                       current.name AS current_name,
                       current.semantic_type AS current_semantic_type,
                       current.rect_x AS current_rect_x,
                       current.rect_y AS current_rect_y,
                       current.rect_width AS current_rect_width,
                       current.rect_height AS current_rect_height,
                       current.created_at AS current_created_at,
                       current.updated_at AS current_updated_at,
                       COALESCE((
                           SELECT status
                           FROM visual_review_region_analyses AS analyses
                           WHERE analyses.pair_id = pairs.id
                           ORDER BY
                               CASE analyses.status
                                   WHEN 'complete' THEN 0
                                   WHEN 'stale' THEN 1
                                   ELSE 2
                               END,
                               analyses.created_at DESC
                           LIMIT 1
                       ), 'pending') AS analysis_status
                FROM visual_review_region_pairs AS pairs
                JOIN visual_review_regions AS reference
                  ON reference.id = pairs.reference_region_id
                JOIN visual_review_regions AS current
                  ON current.id = pairs.current_region_id
                WHERE pairs.shot_id = ? AND current.version_id = ?
                ORDER BY pairs.created_at, pairs.id
                """,
                (shot_id, version_id),
            ).fetchall()
        return tuple(self._pair_view_from_row(row) for row in rows)

    def update_pair(
        self,
        pair_id: str,
        *,
        name: str | None = None,
        semantic_type: str | None = None,
        notes: str | None = None,
    ) -> RegionPairRecord:
        pair = self.get_pair(pair_id)
        updated = replace(
            pair,
            name=pair.name if name is None else name.strip(),
            semantic_type=(
                pair.semantic_type
                if semantic_type is None
                else semantic_type.strip()
            ),
            notes=pair.notes if notes is None else notes.strip(),
            updated_at=utc_now(),
        )
        if not updated.name or not updated.semantic_type:
            raise ProjectSaveError("区域对名称和语义不能为空。")
        with self.project.module_write_connection(MODULE_ID) as connection:
            connection.execute(
                """
                UPDATE visual_review_region_pairs
                SET name = ?, semantic_type = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.name,
                    updated.semantic_type,
                    updated.notes,
                    updated.updated_at,
                    pair_id,
                ),
            )
            connection.execute(
                """
                UPDATE visual_review_region_analyses
                SET status = 'stale'
                WHERE pair_id = ? AND status = 'complete'
                """,
                (pair_id,),
            )
        return updated

    def get_pair(self, pair_id: str) -> RegionPairRecord:
        with self.project.module_read_connection(MODULE_ID) as connection:
            row = connection.execute(
                "SELECT * FROM visual_review_region_pairs WHERE id = ?",
                (pair_id,),
            ).fetchone()
        if row is None:
            raise ProjectSaveError("找不到指定区域对。")
        return self._pair_from_row(row)

    def delete_pair(self, pair_id: str, *, delete_regions: bool = False) -> None:
        pair = self.get_pair(pair_id)
        with self.project.module_write_connection(MODULE_ID) as connection:
            connection.execute(
                "DELETE FROM visual_review_region_pairs WHERE id = ?",
                (pair_id,),
            )
            if delete_regions:
                connection.execute(
                    "DELETE FROM visual_review_regions WHERE id IN (?, ?)",
                    (pair.reference_region_id, pair.current_region_id),
                )

    def copy_previous_version_regions(
        self,
        shot_id: str,
        source_version_id: str,
        target_version_id: str,
    ) -> tuple[RegionPairRecord, ...]:
        source_version = self.project.get_version(source_version_id)
        target_version = self.project.get_version(target_version_id)
        if (
            source_version.shot_id != shot_id
            or target_version.shot_id != shot_id
        ):
            raise ProjectSaveError("复制区域的两个版本必须属于当前 Shot。")
        if self.list_pair_views(shot_id, target_version_id):
            raise ProjectSaveError("目标版本已经存在区域对，未执行复制。")
        source_pairs = self.list_pair_views(shot_id, source_version_id)
        now = utc_now()
        copied: list[RegionPairRecord] = []
        with self.project.module_write_connection(MODULE_ID) as connection:
            for view in source_pairs:
                current = replace(
                    view.current_region,
                    id=str(uuid.uuid4()),
                    version_id=target_version_id,
                    created_at=now,
                    updated_at=now,
                )
                self._insert_region(connection, current)
                pair = replace(
                    view.pair,
                    id=str(uuid.uuid4()),
                    current_region_id=current.id,
                    created_at=now,
                    updated_at=now,
                )
                connection.execute(
                    """
                    INSERT INTO visual_review_region_pairs(
                        id, shot_id, reference_region_id, current_region_id,
                        name, semantic_type, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pair.id,
                        pair.shot_id,
                        pair.reference_region_id,
                        pair.current_region_id,
                        pair.name,
                        pair.semantic_type,
                        pair.notes,
                        pair.created_at,
                        pair.updated_at,
                    ),
                )
                copied.append(pair)
        return tuple(copied)

    def unpaired_regions(
        self,
        shot_id: str,
        version_id: str | None,
    ) -> tuple[RegionRecord, ...]:
        regions = self.list_regions(shot_id, version_id=version_id)
        with self.project.module_read_connection(MODULE_ID) as connection:
            paired_ids = {
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT reference_region_id FROM visual_review_region_pairs
                    WHERE shot_id = ?
                    UNION
                    SELECT current_region_id FROM visual_review_region_pairs
                    WHERE shot_id = ?
                    """,
                    (shot_id, shot_id),
                ).fetchall()
            }
        return tuple(region for region in regions if region.id not in paired_ids)

    def load_analysis(self, cache_key: str) -> RegionAnalysisRecord | None:
        with self.project.module_read_connection(MODULE_ID) as connection:
            row = connection.execute(
                """
                SELECT * FROM visual_review_region_analyses
                WHERE cache_key = ? AND status = 'complete'
                """,
                (cache_key,),
            ).fetchone()
        return None if row is None else self._analysis_from_row(row)

    def latest_analysis(
        self,
        pair_id: str,
    ) -> RegionAnalysisRecord | None:
        with self.project.module_read_connection(MODULE_ID) as connection:
            row = connection.execute(
                """
                SELECT * FROM visual_review_region_analyses
                WHERE pair_id = ?
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (pair_id,),
            ).fetchone()
        return None if row is None else self._analysis_from_row(row)

    def mark_pair_analyses_stale(self, pair_id: str) -> None:
        with self.project.module_write_connection(MODULE_ID) as connection:
            connection.execute(
                """
                UPDATE visual_review_region_analyses
                SET status = 'stale'
                WHERE pair_id = ? AND status = 'complete'
                """,
                (pair_id,),
            )

    def update_analysis_freshness(
        self,
        expected_cache_keys: dict[str, str],
    ) -> None:
        if not expected_cache_keys:
            return
        with self.project.module_write_connection(MODULE_ID) as connection:
            for pair_id, expected_key in expected_cache_keys.items():
                connection.execute(
                    """
                    UPDATE visual_review_region_analyses
                    SET status = CASE
                        WHEN cache_key = ? THEN 'complete'
                        ELSE 'stale'
                    END
                    WHERE pair_id = ? AND status <> 'failed'
                    """,
                    (expected_key, pair_id),
                )

    def mark_version_analyses_stale(
        self,
        shot_id: str,
        version_id: str,
    ) -> None:
        with self.project.module_write_connection(MODULE_ID) as connection:
            connection.execute(
                """
                UPDATE visual_review_region_analyses
                SET status = 'stale'
                WHERE status = 'complete' AND pair_id IN (
                    SELECT pairs.id
                    FROM visual_review_region_pairs AS pairs
                    JOIN visual_review_regions AS current
                      ON current.id = pairs.current_region_id
                    WHERE pairs.shot_id = ? AND current.version_id = ?
                )
                """,
                (shot_id, version_id),
            )

    def save_analysis(
        self,
        pair_id: str,
        *,
        analyzer_id: str,
        analyzer_version: str,
        reference_image_hash: str,
        current_image_hash: str,
        reference_region_geometry: dict[str, float],
        current_region_geometry: dict[str, float],
        shared_palette_cache_key: str,
        parameters: dict[str, Any],
        cache_key: str,
        result: dict[str, Any],
    ) -> RegionAnalysisRecord:
        self.get_pair(pair_id)
        existing = self.load_analysis(cache_key)
        if existing is not None:
            return existing
        record = RegionAnalysisRecord(
            id=str(uuid.uuid4()),
            pair_id=pair_id,
            module_id=MODULE_ID,
            analyzer_id=analyzer_id,
            analyzer_version=analyzer_version,
            reference_image_hash=reference_image_hash,
            current_image_hash=current_image_hash,
            reference_region_geometry=dict(reference_region_geometry),
            current_region_geometry=dict(current_region_geometry),
            shared_palette_cache_key=shared_palette_cache_key,
            parameters=dict(parameters),
            cache_key=cache_key,
            result=dict(result),
            status="complete",
            created_at=utc_now(),
        )
        with self.project.module_write_connection(MODULE_ID) as connection:
            connection.execute(
                """
                UPDATE visual_review_region_analyses
                SET status = 'stale'
                WHERE pair_id = ? AND status = 'complete'
                """,
                (pair_id,),
            )
            connection.execute(
                """
                INSERT INTO visual_review_region_analyses(
                    id, pair_id, module_id, analyzer_id, analyzer_version,
                    reference_image_hash, current_image_hash,
                    reference_region_geometry_json,
                    current_region_geometry_json,
                    shared_palette_cache_key, parameters_json, cache_key,
                    result_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'complete', ?)
                """,
                (
                    record.id,
                    record.pair_id,
                    record.module_id,
                    record.analyzer_id,
                    record.analyzer_version,
                    record.reference_image_hash,
                    record.current_image_hash,
                    canonical_json(record.reference_region_geometry),
                    canonical_json(record.current_region_geometry),
                    record.shared_palette_cache_key,
                    canonical_json(record.parameters),
                    record.cache_key,
                    canonical_json(record.result),
                    record.created_at,
                ),
            )
        return record

    def _validate_role_selection(
        self,
        shot_id: str,
        image_role: str,
        version_id: str | None,
    ) -> None:
        self.project.get_shot(shot_id)
        if image_role == "reference":
            if version_id is not None:
                raise ProjectSaveError("参考区域不能绑定 Version。")
            return
        if image_role != "current" or version_id is None:
            raise ProjectSaveError("当前区域必须绑定具体 Version。")
        version = self.project.get_version(version_id)
        if version.shot_id != shot_id:
            raise ProjectSaveError("当前区域 Version 不属于所选 Shot。")

    @staticmethod
    def _insert_region(
        connection: sqlite3.Connection,
        region: RegionRecord,
    ) -> None:
        rect = region.normalized_rect
        connection.execute(
            """
            INSERT INTO visual_review_regions(
                id, module_id, shot_id, image_role, version_id, name,
                semantic_type, rect_x, rect_y, rect_width, rect_height,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                region.id,
                region.module_id,
                region.shot_id,
                region.image_role,
                region.version_id,
                region.name,
                region.semantic_type,
                rect.x,
                rect.y,
                rect.width,
                rect.height,
                region.created_at,
                region.updated_at,
            ),
        )

    @staticmethod
    def _mark_region_analyses_stale(
        connection: sqlite3.Connection,
        region_id: str,
    ) -> None:
        connection.execute(
            """
            UPDATE visual_review_region_analyses
            SET status = 'stale'
            WHERE status = 'complete' AND pair_id IN (
                SELECT id FROM visual_review_region_pairs
                WHERE reference_region_id = ? OR current_region_id = ?
            )
            """,
            (region_id, region_id),
        )

    @staticmethod
    def _region_from_row(row: sqlite3.Row) -> RegionRecord:
        return RegionRecord(
            id=str(row["id"]),
            module_id=str(row["module_id"]),
            shot_id=str(row["shot_id"]),
            image_role=str(row["image_role"]),
            version_id=row["version_id"],
            name=str(row["name"]),
            semantic_type=str(row["semantic_type"]),
            normalized_rect=NormalizedRect(
                float(row["rect_x"]),
                float(row["rect_y"]),
                float(row["rect_width"]),
                float(row["rect_height"]),
            ),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _pair_from_row(row: sqlite3.Row) -> RegionPairRecord:
        return RegionPairRecord(
            id=str(row["id"]),
            shot_id=str(row["shot_id"]),
            reference_region_id=str(row["reference_region_id"]),
            current_region_id=str(row["current_region_id"]),
            name=str(row["name"]),
            semantic_type=str(row["semantic_type"]),
            notes=str(row["notes"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _analysis_from_row(row: sqlite3.Row) -> RegionAnalysisRecord:
        return RegionAnalysisRecord(
            id=str(row["id"]),
            pair_id=str(row["pair_id"]),
            module_id=str(row["module_id"]),
            analyzer_id=str(row["analyzer_id"]),
            analyzer_version=str(row["analyzer_version"]),
            reference_image_hash=str(row["reference_image_hash"]),
            current_image_hash=str(row["current_image_hash"]),
            reference_region_geometry=json.loads(
                row["reference_region_geometry_json"]
            ),
            current_region_geometry=json.loads(
                row["current_region_geometry_json"]
            ),
            shared_palette_cache_key=str(row["shared_palette_cache_key"]),
            parameters=json.loads(row["parameters_json"]),
            cache_key=str(row["cache_key"]),
            result=json.loads(row["result_json"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
        )

    @classmethod
    def _pair_view_from_row(cls, row: sqlite3.Row) -> RegionPairView:
        pair = cls._pair_from_row(row)

        def region(prefix: str) -> RegionRecord:
            return RegionRecord(
                id=str(row[f"{prefix}_id"]),
                module_id=str(row[f"{prefix}_module_id"]),
                shot_id=str(row[f"{prefix}_shot_id"]),
                image_role=str(row[f"{prefix}_image_role"]),
                version_id=row[f"{prefix}_version_id"],
                name=str(row[f"{prefix}_name"]),
                semantic_type=str(row[f"{prefix}_semantic_type"]),
                normalized_rect=NormalizedRect(
                    float(row[f"{prefix}_rect_x"]),
                    float(row[f"{prefix}_rect_y"]),
                    float(row[f"{prefix}_rect_width"]),
                    float(row[f"{prefix}_rect_height"]),
                ),
                created_at=str(row[f"{prefix}_created_at"]),
                updated_at=str(row[f"{prefix}_updated_at"]),
            )

        return RegionPairView(
            pair=pair,
            reference_region=region("reference"),
            current_region=region("current"),
            analysis_status=str(row["analysis_status"]),
        )
