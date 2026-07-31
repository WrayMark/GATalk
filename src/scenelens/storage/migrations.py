from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path

from scenelens.storage.atomic import atomic_write_json
from scenelens.storage.errors import ProjectVersionError
from scenelens.storage.models import DATABASE_SCHEMA_VERSION


Migration = Callable[[sqlite3.Connection, str, str], None]


def configure_connection(
    connection: sqlite3.Connection,
    read_only: bool = False,
) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    if read_only:
        connection.execute("PRAGMA query_only = ON")
    else:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
    connection.row_factory = sqlite3.Row


def connect_database(
    path: Path,
    read_only: bool = False,
) -> sqlite3.Connection:
    database_path = Path(path)
    if read_only:
        connection = sqlite3.connect(
            f"{database_path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=10.0,
        )
    else:
        connection = sqlite3.connect(database_path, timeout=10.0)
    configure_connection(connection, read_only=read_only)
    return connection


def _migration_1(connection: sqlite3.Connection, project_id: str, now: str) -> None:
    statements = (
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            app_version TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE project_identity (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            id TEXT NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE image_assets (
            id TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL UNIQUE,
            original_filename TEXT NOT NULL,
            stored_relpath TEXT NOT NULL UNIQUE,
            byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
            media_type TEXT NOT NULL,
            source_format TEXT NOT NULL,
            width INTEGER NOT NULL CHECK (width > 0),
            height INTEGER NOT NULL CHECK (height > 0),
            exif_orientation INTEGER,
            icc_status TEXT NOT NULL CHECK (
                icc_status IN ('converted_to_srgb', 'assumed_srgb')
            ),
            imported_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE shots (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES project_identity(id),
            name TEXT NOT NULL,
            reference_asset_id TEXT REFERENCES image_assets(id),
            sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX shots_project_sort_order
        ON shots(project_id, sort_order)
        """,
        """
        CREATE TABLE versions (
            id TEXT PRIMARY KEY,
            shot_id TEXT NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
            asset_id TEXT NOT NULL REFERENCES image_assets(id),
            ordinal INTEGER NOT NULL CHECK (ordinal > 0),
            name TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE (shot_id, ordinal)
        )
        """,
        """
        CREATE TABLE art_briefs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES project_identity(id),
            shot_id TEXT REFERENCES shots(id) ON DELETE CASCADE,
            scene_type TEXT NOT NULL DEFAULT '',
            production_stage TEXT NOT NULL DEFAULT '',
            target_style TEXT NOT NULL DEFAULT '',
            time_weather TEXT NOT NULL DEFAULT '',
            target_mood TEXT NOT NULL DEFAULT '',
            primary_focus TEXT NOT NULL DEFAULT '',
            secondary_focus TEXT NOT NULL DEFAULT '',
            preserve_content TEXT NOT NULL DEFAULT '',
            main_issues TEXT NOT NULL DEFAULT '',
            excluded_review TEXT NOT NULL DEFAULT '',
            constraints TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX art_briefs_project_level
        ON art_briefs(project_id) WHERE shot_id IS NULL
        """,
        """
        CREATE UNIQUE INDEX art_briefs_shot_level
        ON art_briefs(shot_id) WHERE shot_id IS NOT NULL
        """,
        """
        CREATE TABLE workspace_state (
            project_id TEXT PRIMARY KEY REFERENCES project_identity(id),
            current_shot_id TEXT REFERENCES shots(id) ON DELETE SET NULL,
            current_version_id TEXT REFERENCES versions(id) ON DELETE SET NULL,
            display_mode TEXT NOT NULL DEFAULT 'original',
            comparison_mode TEXT NOT NULL DEFAULT 'split',
            ab_role TEXT NOT NULL DEFAULT 'reference',
            sync_views INTEGER NOT NULL DEFAULT 1 CHECK (sync_views IN (0, 1)),
            blur_sigma REAL NOT NULL DEFAULT 0.0,
            three_threshold_low REAL NOT NULL DEFAULT 0.3333333333333333,
            three_threshold_high REAL NOT NULL DEFAULT 0.6666666666666666,
            five_thresholds_json TEXT NOT NULL DEFAULT '[0.2,0.4,0.6,0.8]',
            palette_colours INTEGER NOT NULL DEFAULT 8,
            palette_seed INTEGER NOT NULL DEFAULT 13579,
            palette_max_samples INTEGER NOT NULL DEFAULT 60000,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE canvas_states (
            id TEXT PRIMARY KEY,
            shot_id TEXT NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
            version_id TEXT REFERENCES versions(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('reference', 'current')),
            zoom_factor REAL NOT NULL DEFAULT 1.0,
            center_x REAL NOT NULL DEFAULT 0.5,
            center_y REAL NOT NULL DEFAULT 0.5,
            updated_at TEXT NOT NULL,
            CHECK (
                (role = 'reference' AND version_id IS NULL)
                OR
                (role = 'current' AND version_id IS NOT NULL)
            )
        )
        """,
        """
        CREATE UNIQUE INDEX canvas_states_reference
        ON canvas_states(shot_id) WHERE role = 'reference'
        """,
        """
        CREATE UNIQUE INDEX canvas_states_current
        ON canvas_states(version_id) WHERE role = 'current'
        """,
        """
        CREATE TABLE analysis_runs (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL REFERENCES image_assets(id),
            algorithm_id TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            input_sha256 TEXT NOT NULL,
            cache_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (
                status IN ('complete', 'failed', 'stale')
            ),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE analysis_results (
            id TEXT PRIMARY KEY,
            analysis_run_id TEXT NOT NULL
                REFERENCES analysis_runs(id) ON DELETE CASCADE,
            result_key TEXT NOT NULL,
            evidence_type TEXT NOT NULL CHECK (
                evidence_type IN (
                    'measurement',
                    'algorithm_inference',
                    'art_judgment'
                )
            ),
            payload_json TEXT NOT NULL,
            artifact_relpath TEXT,
            UNIQUE (analysis_run_id, result_key)
        )
        """,
    )
    for statement in statements:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO project_identity(singleton, id) VALUES (1, ?)",
        (project_id,),
    )
    connection.execute(
        """
        INSERT INTO art_briefs(
            id, project_id, shot_id, created_at, updated_at
        ) VALUES (?, ?, NULL, ?, ?)
        """,
        (str(uuid.uuid4()), project_id, now, now),
    )
    connection.execute(
        """
        INSERT INTO workspace_state(project_id, updated_at)
        VALUES (?, ?)
        """,
        (project_id, now),
    )


def _migration_2(connection: sqlite3.Connection, project_id: str, now: str) -> None:
    statements = (
        """
        CREATE TABLE module_schema_versions (
            module_id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
            updated_at TEXT NOT NULL
        )
        """,
        """
        ALTER TABLE analysis_runs
        ADD COLUMN module_id TEXT NOT NULL DEFAULT 'scenelens.visual_review'
        """,
        """
        ALTER TABLE analysis_runs
        ADD COLUMN analyzer_id TEXT NOT NULL DEFAULT 'basic_image_measurements'
        """,
        """
        ALTER TABLE analysis_runs
        ADD COLUMN analyzer_version TEXT NOT NULL DEFAULT '1'
        """,
        """
        ALTER TABLE workspace_state
        ADD COLUMN active_analysis_tab TEXT NOT NULL DEFAULT 'reference'
        """,
        """
        CREATE TABLE visual_review_brief_documents (
            id TEXT PRIMARY KEY,
            document_type TEXT NOT NULL CHECK (
                document_type IN ('creative_intent', 'reference_visual')
            ),
            project_id TEXT NOT NULL REFERENCES project_identity(id),
            shot_id TEXT REFERENCES shots(id) ON DELETE CASCADE,
            asset_id TEXT REFERENCES image_assets(id),
            asset_sha256 TEXT,
            analyzer_id TEXT,
            analyzer_version TEXT,
            analyzed_at TEXT,
            status TEXT NOT NULL DEFAULT 'current' CHECK (
                status IN ('current', 'stale')
            ),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (
                (document_type = 'creative_intent' AND asset_id IS NULL)
                OR
                (
                    document_type = 'reference_visual'
                    AND shot_id IS NOT NULL
                    AND asset_id IS NOT NULL
                    AND asset_sha256 IS NOT NULL
                )
            )
        )
        """,
        """
        CREATE UNIQUE INDEX visual_review_project_intent
        ON visual_review_brief_documents(project_id)
        WHERE document_type = 'creative_intent' AND shot_id IS NULL
        """,
        """
        CREATE UNIQUE INDEX visual_review_shot_intent
        ON visual_review_brief_documents(shot_id)
        WHERE document_type = 'creative_intent' AND shot_id IS NOT NULL
        """,
        """
        CREATE UNIQUE INDEX visual_review_reference_brief
        ON visual_review_brief_documents(shot_id, asset_id)
        WHERE document_type = 'reference_visual'
        """,
        """
        CREATE TABLE visual_review_brief_fields (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL
                REFERENCES visual_review_brief_documents(id) ON DELETE CASCADE,
            field_key TEXT NOT NULL,
            value_json TEXT NOT NULL,
            source TEXT NOT NULL CHECK (
                source IN (
                    'automatic_measurement',
                    'algorithm_inference',
                    'ai_analysis',
                    'user_input',
                    'user_revision'
                )
            ),
            confidence REAL CHECK (
                confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)
            ),
            evidence_json TEXT,
            user_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (
                user_confirmed IN (0, 1)
            ),
            updated_at TEXT NOT NULL,
            UNIQUE (document_id, field_key)
        )
        """,
    )
    for statement in statements:
        connection.execute(statement)

    connection.execute(
        """
        INSERT INTO module_schema_versions(module_id, schema_version, updated_at)
        VALUES ('scenelens.visual_review', 1, ?)
        """,
        (now,),
    )
    connection.execute(
        """
        UPDATE analysis_runs
        SET module_id = 'scenelens.visual_review',
            analyzer_id = CASE
                WHEN algorithm_id = 'scenelens.basic_measurements'
                THEN 'basic_image_measurements'
                ELSE algorithm_id
            END,
            analyzer_version = algorithm_version
        """
    )

    creative_document_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO visual_review_brief_documents(
            id, document_type, project_id, shot_id, asset_id, asset_sha256,
            analyzer_id, analyzer_version, analyzed_at, status,
            created_at, updated_at
        ) VALUES (?, 'creative_intent', ?, NULL, NULL, NULL,
                  NULL, NULL, NULL, 'current', ?, ?)
        """,
        (creative_document_id, project_id, now, now),
    )
    legacy = connection.execute(
        """
        SELECT scene_type, production_stage, target_style, time_weather,
               target_mood, primary_focus, secondary_focus,
               preserve_content, main_issues, excluded_review, constraints
        FROM art_briefs
        WHERE project_id = ? AND shot_id IS NULL
        """,
        (project_id,),
    ).fetchone()
    if legacy is not None:
        field_mapping = {
            "scene_type": "scene_type",
            "production_stage": "production_stage",
            "target_style": "target_style",
            "target_mood": "target_moods",
            "primary_focus": "primary_focus",
            "secondary_focus": "secondary_focus",
            "preserve_content": "preserve_content",
            "main_issues": "main_issues",
            "excluded_review": "excluded_review",
            "constraints": "constraints",
        }
        for legacy_key, field_key in field_mapping.items():
            value = legacy[legacy_key]
            if value:
                _insert_brief_field(
                    connection,
                    creative_document_id,
                    field_key,
                    value,
                    now,
                    {"migrated_from": f"art_briefs.{legacy_key}"},
                )
        if legacy["time_weather"]:
            _insert_brief_field(
                connection,
                creative_document_id,
                "additional_notes",
                f"M1A 时间与天气（未拆分）：{legacy['time_weather']}",
                now,
                {
                    "migrated_from": "art_briefs.time_weather",
                    "original_value": legacy["time_weather"],
                    "migration_note": "未猜测拆分为时间、季节或天气。",
                },
            )

    reference_rows = connection.execute(
        """
        SELECT shots.id AS shot_id, image_assets.id AS asset_id,
               image_assets.sha256 AS asset_sha256
        FROM shots
        JOIN image_assets ON image_assets.id = shots.reference_asset_id
        """
    ).fetchall()
    for reference in reference_rows:
        connection.execute(
            """
            INSERT INTO visual_review_brief_documents(
                id, document_type, project_id, shot_id, asset_id, asset_sha256,
                analyzer_id, analyzer_version, analyzed_at, status,
                created_at, updated_at
            ) VALUES (?, 'reference_visual', ?, ?, ?, ?, NULL, NULL, NULL,
                      'current', ?, ?)
            """,
            (
                str(uuid.uuid4()),
                project_id,
                reference["shot_id"],
                reference["asset_id"],
                reference["asset_sha256"],
                now,
                now,
            ),
        )


def _insert_brief_field(
    connection: sqlite3.Connection,
    document_id: str,
    field_key: str,
    value: object,
    now: str,
    evidence: object | None,
) -> None:
    connection.execute(
        """
        INSERT INTO visual_review_brief_fields(
            id, document_id, field_key, value_json, source, confidence,
            evidence_json, user_confirmed, updated_at
        ) VALUES (?, ?, ?, ?, 'user_input', NULL, ?, 1, ?)
        """,
        (
            str(uuid.uuid4()),
            document_id,
            field_key,
            json.dumps(value, ensure_ascii=False, sort_keys=True),
            (
                None
                if evidence is None
                else json.dumps(evidence, ensure_ascii=False, sort_keys=True)
            ),
            now,
        ),
    )


def _migration_3(connection: sqlite3.Connection, project_id: str, now: str) -> None:
    del project_id
    connection.execute(
        """
        CREATE TABLE visual_review_comparison_analyses (
            id TEXT PRIMARY KEY,
            shot_id TEXT NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
            version_id TEXT NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
            module_id TEXT NOT NULL,
            analyzer_id TEXT NOT NULL,
            analyzer_version TEXT NOT NULL,
            reference_asset_id TEXT NOT NULL REFERENCES image_assets(id),
            current_asset_id TEXT NOT NULL REFERENCES image_assets(id),
            reference_sha256 TEXT NOT NULL,
            current_sha256 TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            input_hashes_json TEXT NOT NULL,
            cache_key TEXT NOT NULL UNIQUE,
            result_json TEXT NOT NULL,
            evidence_type TEXT NOT NULL CHECK (
                evidence_type IN ('measurement', 'algorithm_inference')
            ),
            status TEXT NOT NULL DEFAULT 'complete' CHECK (
                status IN ('complete', 'stale')
            ),
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX visual_review_comparison_selection
        ON visual_review_comparison_analyses(
            shot_id, version_id, analyzer_id, status
        )
        """
    )
    connection.execute(
        """
        UPDATE module_schema_versions
        SET schema_version = 2, updated_at = ?
        WHERE module_id = 'scenelens.visual_review'
        """,
        (now,),
    )


def _migration_4(connection: sqlite3.Connection, project_id: str, now: str) -> None:
    del project_id
    statements = (
        """
        CREATE TABLE visual_review_regions (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL DEFAULT 'scenelens.visual_review',
            shot_id TEXT NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
            image_role TEXT NOT NULL CHECK (
                image_role IN ('reference', 'current')
            ),
            version_id TEXT REFERENCES versions(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            semantic_type TEXT NOT NULL,
            rect_x REAL NOT NULL CHECK (rect_x >= 0.0 AND rect_x <= 1.0),
            rect_y REAL NOT NULL CHECK (rect_y >= 0.0 AND rect_y <= 1.0),
            rect_width REAL NOT NULL CHECK (
                rect_width > 0.0 AND rect_width <= 1.0
            ),
            rect_height REAL NOT NULL CHECK (
                rect_height > 0.0 AND rect_height <= 1.0
            ),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (rect_x + rect_width <= 1.000000001),
            CHECK (rect_y + rect_height <= 1.000000001),
            CHECK (
                (image_role = 'reference' AND version_id IS NULL)
                OR
                (image_role = 'current' AND version_id IS NOT NULL)
            )
        )
        """,
        """
        CREATE INDEX visual_review_regions_selection
        ON visual_review_regions(shot_id, image_role, version_id, created_at)
        """,
        """
        CREATE TABLE visual_review_region_pairs (
            id TEXT PRIMARY KEY,
            shot_id TEXT NOT NULL REFERENCES shots(id) ON DELETE CASCADE,
            reference_region_id TEXT NOT NULL
                REFERENCES visual_review_regions(id) ON DELETE CASCADE,
            current_region_id TEXT NOT NULL UNIQUE
                REFERENCES visual_review_regions(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            semantic_type TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX visual_review_region_pairs_shot
        ON visual_review_region_pairs(shot_id, created_at)
        """,
        """
        CREATE TABLE visual_review_region_analyses (
            id TEXT PRIMARY KEY,
            pair_id TEXT NOT NULL
                REFERENCES visual_review_region_pairs(id) ON DELETE CASCADE,
            module_id TEXT NOT NULL,
            analyzer_id TEXT NOT NULL,
            analyzer_version TEXT NOT NULL,
            reference_image_hash TEXT NOT NULL,
            current_image_hash TEXT NOT NULL,
            reference_region_geometry_json TEXT NOT NULL,
            current_region_geometry_json TEXT NOT NULL,
            shared_palette_cache_key TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            cache_key TEXT NOT NULL UNIQUE,
            result_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('complete', 'stale', 'failed')
            ),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX visual_review_region_analysis_pair
        ON visual_review_region_analyses(pair_id, status, created_at)
        """,
    )
    for statement in statements:
        connection.execute(statement)
    connection.execute(
        """
        UPDATE module_schema_versions
        SET schema_version = 3, updated_at = ?
        WHERE module_id = 'scenelens.visual_review'
        """,
        (now,),
    )


def _migration_5(connection: sqlite3.Connection, project_id: str, now: str) -> None:
    del project_id, now
    statements = (
        """
        CREATE TABLE workbench_evidence (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            shot_id TEXT REFERENCES shots(id) ON DELETE CASCADE,
            version_id TEXT REFERENCES versions(id) ON DELETE CASCADE,
            evidence_type TEXT NOT NULL CHECK (
                evidence_type IN (
                    'measurement',
                    'algorithm_inference',
                    'art_judgment'
                )
            ),
            source TEXT NOT NULL CHECK (
                source IN (
                    'local_analyzer',
                    'ai_provider',
                    'user',
                    'import'
                )
            ),
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('current', 'stale', 'deleted')
            ),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX workbench_evidence_subject
        ON workbench_evidence(
            module_id, subject_type, subject_id, status, created_at
        )
        """,
        """
        CREATE TABLE workbench_annotations (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            shot_id TEXT REFERENCES shots(id) ON DELETE CASCADE,
            version_id TEXT REFERENCES versions(id) ON DELETE CASCADE,
            evidence_id TEXT REFERENCES workbench_evidence(id)
                ON DELETE SET NULL,
            annotation_type TEXT NOT NULL,
            geometry_json TEXT NOT NULL,
            label TEXT NOT NULL,
            style_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX workbench_annotations_selection
        ON workbench_annotations(module_id, shot_id, version_id, created_at)
        """,
        """
        CREATE TABLE workbench_tasks (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            shot_id TEXT REFERENCES shots(id) ON DELETE CASCADE,
            version_id TEXT REFERENCES versions(id) ON DELETE SET NULL,
            source_evidence_id TEXT REFERENCES workbench_evidence(id)
                ON DELETE SET NULL,
            source_annotation_id TEXT REFERENCES workbench_annotations(id)
                ON DELETE SET NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL CHECK (
                priority IN ('critical', 'high', 'medium', 'low')
            ),
            status TEXT NOT NULL CHECK (
                status IN ('open', 'in_progress', 'done', 'dismissed')
            ),
            verification_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX workbench_tasks_selection
        ON workbench_tasks(module_id, shot_id, version_id, status, priority)
        """,
        """
        CREATE TABLE workbench_derived_artifacts (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            shot_id TEXT REFERENCES shots(id) ON DELETE CASCADE,
            version_id TEXT REFERENCES versions(id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            input_hashes_json TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('current', 'stale', 'deleted')
            ),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX workbench_artifacts_selection
        ON workbench_derived_artifacts(
            module_id, shot_id, version_id, artifact_type, status
        )
        """,
        """
        CREATE TABLE workbench_ai_runs (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            reviewer_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            input_manifest_json TEXT NOT NULL,
            output_json TEXT,
            status TEXT NOT NULL CHECK (
                status IN (
                    'pending', 'running', 'complete', 'failed', 'cancelled'
                )
            ),
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
        """,
        """
        CREATE INDEX workbench_ai_runs_selection
        ON workbench_ai_runs(
            module_id, reviewer_id, provider_id, status, created_at
        )
        """,
        """
        CREATE TABLE workbench_source_documents (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            document_type TEXT NOT NULL,
            title TEXT NOT NULL,
            source_uri TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE workbench_review_profiles (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            name TEXT NOT NULL,
            reviewer_ids_json TEXT NOT NULL,
            settings_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE workbench_quality_gates (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL
                REFERENCES workbench_review_profiles(id) ON DELETE CASCADE,
            dimension_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            operator TEXT NOT NULL,
            threshold_json TEXT NOT NULL,
            weight REAL NOT NULL CHECK (weight >= 0.0),
            state TEXT NOT NULL CHECK (
                state IN (
                    'not_evaluated',
                    'pass',
                    'warning',
                    'fail',
                    'insufficient_evidence'
                )
            ),
            updated_at TEXT NOT NULL,
            UNIQUE (profile_id, dimension_id)
        )
        """,
    )
    for statement in statements:
        connection.execute(statement)


def _migration_6(connection: sqlite3.Connection, project_id: str, now: str) -> None:
    del project_id, now
    columns = {
        str(row["name"])
        for row in connection.execute(
            "PRAGMA table_info(workspace_state)"
        ).fetchall()
    }
    if "silhouette_threshold" in columns:
        return
    connection.execute(
        """
        ALTER TABLE workspace_state
        ADD COLUMN silhouette_threshold REAL NOT NULL DEFAULT 0.45
        """
    )


def _migration_7(
    connection: sqlite3.Connection,
    project_id: str,
    now: str,
) -> None:
    del project_id, now
    columns = {
        str(row["name"])
        for row in connection.execute(
            "PRAGMA table_info(workspace_state)"
        ).fetchall()
    }
    if "composition_guide" in columns:
        return
    connection.execute(
        """
        ALTER TABLE workspace_state
        ADD COLUMN composition_guide TEXT NOT NULL DEFAULT 'none'
        """
    )


MIGRATIONS: dict[int, tuple[str, Migration]] = {
    1: ("initial_m1a_schema", _migration_1),
    2: ("m1b_visual_review_module_schema", _migration_2),
    3: ("m1b_comparison_analysis_cache", _migration_3),
    4: ("m1b_paired_regions", _migration_4),
    5: ("m2_workbench_core_entities", _migration_5),
    6: ("m2_lighting_observation_state", _migration_6),
    7: ("m4_composition_guide_state", _migration_7),
}


def database_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def create_database(
    path: Path,
    project_id: str,
    now: str,
    app_version: str,
) -> None:
    connection = connect_database(path)
    try:
        _apply_migrations(connection, 0, project_id, now, app_version)
    finally:
        connection.close()


def migrate_database(
    path: Path,
    project_id: str,
    project_root: Path,
    backups_relpath: str,
    now: str,
    app_version: str,
) -> int:
    connection = connect_database(path)
    try:
        current = database_version(connection)
        if current > DATABASE_SCHEMA_VERSION:
            raise ProjectVersionError(
                "该项目由更高版本的 GATalk 创建，当前版本不会写入它。"
            )
        if current == DATABASE_SCHEMA_VERSION:
            return current

        _create_migration_backup(
            connection,
            project_root,
            backups_relpath,
            current,
            DATABASE_SCHEMA_VERSION,
            now,
        )
        _apply_migrations(
            connection,
            current,
            project_id,
            now,
            app_version,
        )
        return DATABASE_SCHEMA_VERSION
    finally:
        connection.close()


def _apply_migrations(
    connection: sqlite3.Connection,
    current: int,
    project_id: str,
    now: str,
    app_version: str,
) -> None:
    for target in range(current + 1, DATABASE_SCHEMA_VERSION + 1):
        name, migration = MIGRATIONS[target]
        try:
            connection.execute("BEGIN IMMEDIATE")
            migration(connection, project_id, now)
            connection.execute(
                """
                INSERT INTO schema_migrations(version, name, applied_at, app_version)
                VALUES (?, ?, ?, ?)
                """,
                (target, name, now, app_version),
            )
            connection.execute(f"PRAGMA user_version = {target}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _create_migration_backup(
    source: sqlite3.Connection,
    project_root: Path,
    backups_relpath: str,
    source_version: int,
    target_version: int,
    now: str,
) -> Path:
    safe_time = (
        now.replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace("+00:00", "Z")
    )
    backup_root = (
        project_root
        / Path(backups_relpath)
        / f"pre-migration_{source_version:04d}_to_{target_version:04d}_{safe_time}"
    )
    backup_root.mkdir(parents=True, exist_ok=False)
    destination_path = backup_root / "project.db"
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()

    manifest_source = project_root / "project.json"
    if manifest_source.is_file():
        (backup_root / "project.json").write_bytes(manifest_source.read_bytes())

    atomic_write_json(
        backup_root / "backup.json",
        {
            "backup_id": str(uuid.uuid4()),
            "complete": True,
            "created_at": now,
            "source_schema_version": source_version,
            "target_schema_version": target_version,
            "database": "project.db",
            "manifest": "project.json" if manifest_source.is_file() else None,
        },
    )
    return backup_root
