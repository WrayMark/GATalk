from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import platform
import shutil
from typing import Iterable, Mapping
import uuid

from scenelens.storage.atomic import atomic_write_json, load_json
from scenelens.storage.project_store import utc_now


@dataclass(frozen=True)
class ProjectFormat:
    label: str
    required_directories: tuple[str, ...]
    database_filename: str = ""


ENTRY_FORMATS: Mapping[str, ProjectFormat] = {
    "project.json": ProjectFormat(
        "场景美术控制项目",
        ("assets", "artifacts", "exports", "backups"),
        "project.db",
    ),
    "study.json": ProjectFormat(
        "单件作品研究",
        ("assets", "artifacts", "exports", "backups"),
    ),
    "asset_project.json": ProjectFormat(
        "资产拆分项目",
        ("assets", "artifacts", "exports", "backups"),
    ),
    # 0.7.0 之前的内部候选曾使用此名称，只读诊断继续识别。
    "breakdown.json": ProjectFormat(
        "资产拆分项目（旧入口）",
        ("assets", "artifacts", "exports", "backups"),
    ),
    "library.json": ProjectFormat(
        "参考资料库",
        ("assets", "derived", "documents", "exports", "backups"),
    ),
    "comparison.json": ProjectFormat(
        "作品对照研究",
        ("assets", "artifacts", "exports", "backups"),
    ),
}


@dataclass(frozen=True)
class ProjectDiagnostic:
    root: str
    project_type: str
    status: str
    issues: tuple[str, ...]
    entry_filename: str = ""
    backup_count: int = 0
    missing_source_count: int = 0
    missing_artifact_count: int = 0
    writable: bool = False
    free_bytes: int = 0

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["issues"] = list(self.issues)
        return value


@dataclass(frozen=True)
class RecoveryPoint:
    path: str
    label: str
    kind: str
    created_at: str
    restorable: bool


def inspect_project(root: str | Path) -> ProjectDiagnostic:
    folder = Path(root)
    issues: list[str] = []
    if not folder.is_dir():
        return ProjectDiagnostic(
            str(folder),
            "未知",
            "missing",
            ("目录不存在。",),
        )
    entry = next((name for name in ENTRY_FORMATS if (folder / name).is_file()), "")
    if not entry:
        return ProjectDiagnostic(
            str(folder.resolve()),
            "未知",
            "invalid",
            ("未找到受支持的 GATalk 项目入口文件。",),
            writable=os.access(folder, os.W_OK),
            free_bytes=_free_bytes(folder),
        )
    project_format = ENTRY_FORMATS[entry]
    try:
        data = load_json(folder / entry)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues.append(f"入口文件无法读取：{exc}")
        data = {}
    if not data.get("format"):
        issues.append("入口文件缺少格式标识。")
    for directory in project_format.required_directories:
        if not (folder / directory).is_dir():
            issues.append(f"{directory} 目录缺失。")
    if project_format.database_filename and not (
        folder / project_format.database_filename
    ).is_file():
        issues.append(f"{project_format.database_filename} 缺失。")
    source_paths, artifact_paths = _referenced_paths(data)
    missing_sources, invalid_sources = _missing_path_count(folder, source_paths)
    missing_artifacts, invalid_artifacts = _missing_path_count(folder, artifact_paths)
    if invalid_sources or invalid_artifacts:
        issues.append("项目包含越出项目目录的文件引用，已拒绝访问。")
    if missing_sources:
        issues.append(f"{missing_sources} 个原始资料文件缺失。")
    if missing_artifacts:
        issues.append(f"{missing_artifacts} 个可重建分析产物缺失。")
    backup_count = len(list_recovery_points(folder))
    writable = os.access(folder, os.W_OK)
    if not writable:
        issues.append("项目目录当前不可写，将无法保存修改。")
    return ProjectDiagnostic(
        root=str(folder.resolve()),
        project_type=project_format.label,
        status="ok" if not issues else "warning",
        issues=tuple(issues),
        entry_filename=entry,
        backup_count=backup_count,
        missing_source_count=missing_sources,
        missing_artifact_count=missing_artifacts,
        writable=writable,
        free_bytes=_free_bytes(folder),
    )


def repair_project_directories(root: str | Path) -> tuple[str, ...]:
    """Recreate safe, empty infrastructure directories only.

    Missing databases and source assets are deliberately not synthesized.
    """

    folder = Path(root).resolve()
    diagnostic = inspect_project(folder)
    if not diagnostic.entry_filename:
        raise ValueError("所选目录不是可修复的 GATalk 项目。")
    created: list[str] = []
    for relative in ENTRY_FORMATS[diagnostic.entry_filename].required_directories:
        target = _safe_child(folder, relative)
        if not target.exists():
            target.mkdir(parents=True, exist_ok=False)
            created.append(relative)
    return tuple(created)


def create_recovery_point(
    root: str | Path,
    *,
    label: str = "manual",
) -> RecoveryPoint:
    folder = Path(root).resolve()
    diagnostic = inspect_project(folder)
    if not diagnostic.entry_filename:
        raise ValueError("所选目录不是可备份的 GATalk 项目。")
    stamp = utc_now().replace(":", "-")
    safe_label = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in label.strip()
    ) or "manual"
    destination = folder / "backups" / f"recovery_{stamp}_{safe_label}"
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(folder / diagnostic.entry_filename, destination / diagnostic.entry_filename)
    database = ENTRY_FORMATS[diagnostic.entry_filename].database_filename
    if database and (folder / database).is_file():
        shutil.copy2(folder / database, destination / database)
    atomic_write_json(
        destination / "recovery.json",
        {
            "format": "gatalk.recovery_point",
            "format_version": 1,
            "entry_filename": diagnostic.entry_filename,
            "database_filename": database,
            "created_at": utc_now(),
            "source_root": str(folder),
        },
    )
    return RecoveryPoint(
        path=str(destination),
        label=safe_label,
        kind="snapshot",
        created_at=utc_now(),
        restorable=True,
    )


def list_recovery_points(root: str | Path) -> tuple[RecoveryPoint, ...]:
    folder = Path(root).resolve()
    backups = folder / "backups"
    if not backups.is_dir():
        return ()
    values: list[RecoveryPoint] = []
    for path in backups.iterdir():
        if path.is_dir():
            manifest = path / "recovery.json"
            if manifest.is_file():
                try:
                    data = load_json(manifest)
                except (OSError, ValueError):
                    data = {}
                values.append(
                    RecoveryPoint(
                        path=str(path),
                        label=path.name,
                        kind="snapshot",
                        created_at=str(data.get("created_at", "")),
                        restorable=bool(data.get("entry_filename")),
                    )
                )
            elif (path / "project.json").is_file():
                values.append(
                    RecoveryPoint(
                        path=str(path),
                        label=path.name,
                        kind="migration",
                        created_at="",
                        restorable=True,
                    )
                )
        elif path.is_file() and path.suffix.casefold() == ".json":
            values.append(
                RecoveryPoint(
                    path=str(path),
                    label=path.stem,
                    kind="manifest",
                    created_at="",
                    restorable=True,
                )
            )
    return tuple(sorted(values, key=lambda item: item.path, reverse=True))


def restore_recovery_point(
    root: str | Path,
    recovery_path: str | Path,
) -> RecoveryPoint:
    folder = Path(root).resolve()
    candidate = Path(recovery_path).resolve()
    backups = (folder / "backups").resolve()
    if candidate != backups and backups not in candidate.parents:
        raise ValueError("只能恢复当前项目 backups 目录中的恢复点。")
    current = inspect_project(folder)
    if not current.entry_filename:
        raise ValueError("当前项目入口不可识别，无法确定恢复目标。")
    safety = create_recovery_point(folder, label="pre_restore")
    if candidate.is_dir():
        metadata_path = candidate / "recovery.json"
        metadata = load_json(metadata_path) if metadata_path.is_file() else {}
        source_entry = str(metadata.get("entry_filename", ""))
        if not source_entry:
            source_entry = "project.json" if (candidate / "project.json").is_file() else ""
        if not source_entry or not (candidate / source_entry).is_file():
            raise ValueError("恢复点缺少项目入口文件。")
        _atomic_copy(candidate / source_entry, folder / current.entry_filename)
        source_database = str(metadata.get("database_filename", ""))
        if not source_database and (candidate / "project.db").is_file():
            source_database = "project.db"
        target_database = ENTRY_FORMATS[current.entry_filename].database_filename
        if source_database and target_database and (candidate / source_database).is_file():
            _atomic_copy(candidate / source_database, folder / target_database)
    elif candidate.is_file():
        try:
            backup_data = load_json(candidate)
        except (OSError, ValueError) as exc:
            raise ValueError(f"备份入口无法读取：{exc}") from exc
        if not backup_data.get("format"):
            raise ValueError("备份入口缺少格式标识。")
        _atomic_copy(candidate, folder / current.entry_filename)
    else:
        raise ValueError("恢复点不存在。")
    return safety


def write_diagnostic_report(
    destination: str | Path,
    projects: Iterable[ProjectDiagnostic],
) -> Path:
    path = Path(destination)
    atomic_write_json(
        path,
        {
            "format": "gatalk.diagnostic_report",
            "format_version": 2,
            "created_at": utc_now(),
            "application": {"name": "GATalk", "version": "0.15.0"},
            "environment": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
            "privacy": (
                "报告不包含 API Key、图片字节、AI 提示语或项目正文；"
                "包含用户主动选择的本地路径和结构检查结果。"
            ),
            "projects": [item.to_dict() for item in projects],
        },
    )
    return path


def _referenced_paths(data: Mapping[str, object]) -> tuple[set[str], set[str]]:
    sources: set[str] = set()
    artifacts: set[str] = set()

    def visit(value: object, key: str = "") -> None:
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                visit(child, str(child_key))
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                visit(child, key)
            return
        if not isinstance(value, str) or not value.strip():
            return
        normalized = value.replace("\\", "/").lstrip("./")
        if not normalized or "://" in normalized or normalized.startswith("data:"):
            return
        if key in {
            "relative_path",
            "local_relative_path",
            "stored_relpath",
        }:
            if normalized.startswith(("artifacts/", "derived/", "exports/")):
                artifacts.add(normalized)
            elif normalized.startswith(("assets/", "documents/")):
                sources.add(normalized)
        elif key.endswith("_relative_path"):
            if normalized.startswith(("artifacts/", "derived/", "exports/")):
                artifacts.add(normalized)

    visit(data)
    return sources, artifacts


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("项目内部路径越出项目目录。")
    return candidate


def _missing_path_count(root: Path, values: Iterable[str]) -> tuple[int, int]:
    missing = 0
    invalid = 0
    for relative in values:
        try:
            exists = _safe_child(root, relative).is_file()
        except ValueError:
            invalid += 1
            continue
        if not exists:
            missing += 1
    return missing, invalid


def _atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _free_bytes(path: Path) -> int:
    try:
        return int(shutil.disk_usage(path).free)
    except OSError:
        return 0
