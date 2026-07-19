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


def configure_connection(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    connection.row_factory = sqlite3.Row


def connect_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path), timeout=10.0)
    configure_connection(connection)
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


MIGRATIONS: dict[int, tuple[str, Migration]] = {
    1: ("initial_m1a_schema", _migration_1),
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
                "该项目由更高版本的 SceneLens 创建，当前版本不会写入它。"
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
