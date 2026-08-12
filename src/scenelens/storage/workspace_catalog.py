from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from scenelens.storage.atomic import atomic_write_json, load_json
from scenelens.storage.project_store import utc_now
from scenelens.storage.recent_projects import RecentProjects


CATALOG_FORMAT_VERSION = 1


ENTRY_WORKSPACES = {
    "project.json": ("scenelens.visual_review", "scene_art_control"),
    "study.json": ("scenelens.artwork_study", "artwork_study"),
    "asset_project.json": ("scenelens.asset_breakdown", "asset_breakdown"),
    "library.json": ("gatalk.knowledge_base", "reference_knowledge"),
    "comparison.json": ("gatalk.comparative_study", "comparative_study"),
}


@dataclass(frozen=True)
class WorkspaceLocation:
    root: str
    entry_filename: str
    module_id: str
    workspace_id: str
    project_id: str
    title: str
    last_opened_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> WorkspaceLocation:
        return cls(
            root=str(value["root"]),
            entry_filename=str(value["entry_filename"]),
            module_id=str(value.get("module_id", "")),
            workspace_id=str(value.get("workspace_id", "")),
            project_id=str(value.get("project_id", "")),
            title=str(value.get("title", "未命名项目")),
            last_opened_at=str(value.get("last_opened_at", "")),
        )


@dataclass(frozen=True)
class WorkspaceSearchRecord:
    record_id: str
    module_id: str
    workspace_id: str
    project_id: str
    project_title: str
    project_root: str
    entity_type: str
    entity_id: str
    title: str
    summary: str = ""
    labels: tuple[str, ...] = ()
    source_version_id: str = ""
    updated_at: str = ""

    @property
    def search_text(self) -> str:
        return " ".join(
            (
                self.title,
                self.summary,
                self.project_title,
                self.entity_type,
                *self.labels,
            )
        ).casefold()


def default_catalog_path() -> Path:
    local = os.getenv("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "GATalk" / "workspace-catalog.json"


class WorkspaceCatalogStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_catalog_path()

    def load(self) -> tuple[WorkspaceLocation, ...]:
        if not self.path.is_file():
            return ()
        try:
            data = load_json(self.path)
            if int(data.get("format_version", 0)) > CATALOG_FORMAT_VERSION:
                return ()
            return tuple(
                WorkspaceLocation.from_dict(item)
                for item in data.get("locations", ())
                if isinstance(item, Mapping)
            )
        except (OSError, TypeError, ValueError):
            return ()

    def remember(self, root: str | Path) -> WorkspaceLocation:
        folder = Path(root).resolve()
        entry = next(
            (name for name in ENTRY_WORKSPACES if (folder / name).is_file()),
            "",
        )
        if not entry:
            raise ValueError("所选目录不是可索引的 GATalk 工作项目。")
        data = load_json(folder / entry)
        state = data.get("state", {})
        if not isinstance(state, Mapping):
            state = {}
        project_id = str(
            data.get("project_id")
            or state.get("project_id")
            or state.get("study_id")
            or state.get("library_id")
            or ""
        )
        title = str(
            data.get("name")
            or state.get("title")
            or folder.stem
        )
        module_id, workspace_id = ENTRY_WORKSPACES[entry]
        location = WorkspaceLocation(
            root=str(folder),
            entry_filename=entry,
            module_id=module_id,
            workspace_id=workspace_id,
            project_id=project_id,
            title=title,
            last_opened_at=utc_now(),
        )
        retained = [
            item
            for item in self.load()
            if Path(item.root) != folder
            and not (project_id and item.project_id == project_id)
        ]
        self._save((location, *retained)[:80])
        return location

    def forget(self, root: str | Path) -> None:
        folder = Path(root).resolve()
        self._save(
            tuple(item for item in self.load() if Path(item.root) != folder)
        )

    def relink(self, old_root: str | Path, new_root: str | Path) -> WorkspaceLocation:
        old = Path(old_root).resolve()
        replacement = self.remember(new_root)
        self._save(
            (
                replacement,
                *(
                    item
                    for item in self.load()
                    if Path(item.root) not in {old, Path(replacement.root)}
                ),
            )
        )
        return replacement

    def _save(self, values: Iterable[WorkspaceLocation]) -> None:
        atomic_write_json(
            self.path,
            {
                "format": "gatalk.workspace_catalog",
                "format_version": CATALOG_FORMAT_VERSION,
                "locations": [item.to_dict() for item in values],
            },
        )


class GlobalWorkspaceSearch:
    def __init__(
        self,
        catalog: WorkspaceCatalogStore | None = None,
        recent_projects: RecentProjects | None = None,
        review_center_root: str | Path | None = None,
    ) -> None:
        self.catalog = catalog or WorkspaceCatalogStore()
        self.recent_projects = recent_projects or RecentProjects()
        self.review_center_root = (
            Path(review_center_root)
            if review_center_root is not None
            else _default_review_center_root()
        )

    def locations(self) -> tuple[WorkspaceLocation, ...]:
        values = list(self.catalog.load())
        known = {Path(item.root).resolve() for item in values if Path(item.root).exists()}
        for item in self.recent_projects.load():
            root = item.manifest_path.parent.resolve()
            if root in known or not item.manifest_path.is_file():
                continue
            values.append(
                WorkspaceLocation(
                    root=str(root),
                    entry_filename=item.manifest_path.name,
                    module_id="scenelens.visual_review",
                    workspace_id="scene_art_control",
                    project_id=item.project_id,
                    title=item.name,
                    last_opened_at=item.last_opened_at,
                )
            )
            known.add(root)
        return tuple(values)

    def records(self) -> tuple[WorkspaceSearchRecord, ...]:
        records: list[WorkspaceSearchRecord] = []
        for location in self.locations():
            root = Path(location.root)
            entry = root / location.entry_filename
            if not entry.is_file():
                continue
            try:
                data = load_json(entry)
                records.extend(_records_for_location(location, data))
            except (OSError, TypeError, ValueError):
                continue
        records.extend(_review_center_records(self.review_center_root))
        unique: dict[str, WorkspaceSearchRecord] = {}
        for record in records:
            unique[record.record_id] = record
        return tuple(unique.values())

    def search(self, query: str, limit: int = 80) -> tuple[WorkspaceSearchRecord, ...]:
        terms = tuple(
            part.casefold()
            for part in query.replace("，", " ").split()
            if part.strip()
        )
        if not terms:
            return tuple(
                sorted(
                    self.records(),
                    key=lambda item: item.updated_at,
                    reverse=True,
                )[:limit]
            )
        ranked: list[tuple[int, WorkspaceSearchRecord]] = []
        for record in self.records():
            haystack = record.search_text
            if not all(term in haystack for term in terms):
                continue
            title = record.title.casefold()
            score = sum(6 if term in title else 2 for term in terms)
            if all(title.startswith(term) for term in terms):
                score += 4
            ranked.append((score, record))
        ranked.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return tuple(record for _score, record in ranked[:limit])


def _records_for_location(
    location: WorkspaceLocation,
    data: Mapping[str, Any],
) -> list[WorkspaceSearchRecord]:
    state = data.get("state", {})
    if not isinstance(state, Mapping):
        state = {}
    title = location.title or str(state.get("title", "未命名项目"))
    updated = str(data.get("updated_at") or state.get("updated_at") or location.last_opened_at)
    records = [
        _record(
            location,
            "project",
            location.project_id or location.root,
            title,
            _project_summary(state),
            updated_at=updated,
        )
    ]
    entry = location.entry_filename
    if entry == "library.json":
        for item in state.get("items", ()):
            if not isinstance(item, Mapping):
                continue
            records.append(
                _record(
                    location,
                    "knowledge_item",
                    str(item.get("item_id", "")),
                    str(item.get("title", "未命名资料")),
                    " ".join(
                        str(item.get(key, ""))
                        for key in ("creator", "project_name", "description", "notes")
                    ),
                    labels=tuple(str(value) for value in item.get("tags", ())),
                    updated_at=str(item.get("updated_at", updated)),
                )
            )
        for board in state.get("visual_boards", ()):
            if not isinstance(board, Mapping):
                continue
            records.append(
                _record(
                    location,
                    "visual_board",
                    str(board.get("board_id", "")),
                    str(board.get("title", "未命名视觉资料板")),
                    " ".join(
                        (
                            str(board.get("purpose", "")),
                            " ".join(
                                str(card.get("title", ""))
                                for card in board.get("cards", ())
                                if isinstance(card, Mapping)
                            ),
                        )
                    ),
                    updated_at=str(board.get("updated_at", updated)),
                )
            )
    elif entry == "asset_project.json":
        production_specs = {
            str(item.get("asset_id", "")): item
            for item in state.get("production_specs", ())
            if isinstance(item, Mapping)
        }
        for item in state.get("assets", ()):
            if not isinstance(item, Mapping):
                continue
            specification = production_specs.get(
                str(item.get("asset_id", "")),
                {},
            )
            records.append(
                _record(
                    location,
                    "asset",
                    str(item.get("asset_id", "")),
                    str(item.get("name", "未命名资产")),
                    " ".join(
                        str(item.get(key, ""))
                        for key in (
                            "semantic_type",
                            "visible_evidence",
                            "production_strategy",
                            "material_notes",
                        )
                    )
                    + " "
                    + " ".join(
                        str(specification.get(key, ""))
                        for key in (
                            "asset_code",
                            "target_dimensions_cm",
                            "geometry_strategy",
                            "ue_destination",
                            "notes",
                        )
                    ),
                    labels=(
                        str(item.get("category", "")),
                        str(item.get("production_priority", "")),
                        str(item.get("reuse_group", "")),
                        str(specification.get("status", "")),
                    ),
                    updated_at=str(item.get("updated_at", updated)),
                )
            )
    elif entry == "study.json":
        review = state.get("ai_review", {})
        if isinstance(review, Mapping):
            for item in review.get("dimension_studies", ()):
                if not isinstance(item, Mapping):
                    continue
                records.append(
                    _record(
                        location,
                        "dimension_study",
                        str(item.get("dimension_id", item.get("dimension", ""))),
                        str(item.get("dimension", "研究维度")),
                        " ".join(
                            str(item.get(key, ""))
                            for key in ("observation", "visual_evidence", "learning_note")
                        ),
                        updated_at=updated,
                    )
                )
    elif entry == "comparison.json":
        for item in state.get("items", state.get("works", ())):
            if isinstance(item, Mapping):
                records.append(
                    _record(
                        location,
                        "comparison_work",
                        str(item.get("item_id", item.get("work_id", ""))),
                        str(item.get("title", "对照作品")),
                        str(item.get("source_reference", "")),
                        updated_at=updated,
                    )
                )
    elif entry == "project.json":
        records.extend(_scene_database_records(location, title, updated))
    return records


def _scene_database_records(
    location: WorkspaceLocation,
    project_title: str,
    updated: str,
) -> list[WorkspaceSearchRecord]:
    path = Path(location.root) / "project.db"
    if not path.is_file():
        return []
    records: list[WorkspaceSearchRecord] = []
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        for row in connection.execute("SELECT id, name, updated_at FROM shots"):
            records.append(
                _record(
                    location,
                    "shot",
                    str(row["id"]),
                    str(row["name"]),
                    project_title,
                    updated_at=str(row["updated_at"] or updated),
                )
            )
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "workbench_tasks" in tables:
            for row in connection.execute(
                "SELECT id, title, description, status, version_id, updated_at "
                "FROM workbench_tasks"
            ):
                records.append(
                    _record(
                        location,
                        "workbench_task",
                        str(row["id"]),
                        str(row["title"]),
                        str(row["description"] or ""),
                        labels=(str(row["status"] or ""),),
                        source_version_id=str(row["version_id"] or ""),
                        updated_at=str(row["updated_at"] or updated),
                    )
                )
    except sqlite3.Error:
        return records
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass
    return records


def _review_center_records(root: Path) -> list[WorkspaceSearchRecord]:
    entry = root / "review_center.json"
    if not entry.is_file():
        return []
    try:
        state = load_json(entry).get("state", {})
    except (OSError, ValueError):
        return []
    if not isinstance(state, Mapping):
        return []
    values: list[WorkspaceSearchRecord] = []
    for entity_type, key in (("review_task", "tasks"), ("quality_gate", "gates")):
        for item in state.get(key, ()):
            if not isinstance(item, Mapping):
                continue
            entity_id = str(item.get("task_id") or item.get("gate_id") or "")
            project_id = str(item.get("source_project_id", ""))
            values.append(
                WorkspaceSearchRecord(
                    record_id=f"review_control:{entity_type}:{entity_id}",
                    module_id="gatalk.review_control",
                    workspace_id="review_control",
                    project_id=project_id,
                    project_title=str(item.get("source_project_title", "制作任务中心")),
                    project_root=str(item.get("source_project_path", root)),
                    entity_type=entity_type,
                    entity_id=entity_id,
                    title=str(item.get("title") or item.get("name") or "未命名"),
                    summary=str(
                        item.get("description")
                        or item.get("acceptance_criteria")
                        or ""
                    ),
                    labels=tuple(str(value) for value in item.get("labels", ())),
                    source_version_id=str(item.get("source_version_id", "")),
                    updated_at=str(item.get("updated_at", "")),
                )
            )
    return values


def _record(
    location: WorkspaceLocation,
    entity_type: str,
    entity_id: str,
    title: str,
    summary: str,
    *,
    labels: tuple[str, ...] = (),
    source_version_id: str = "",
    updated_at: str = "",
) -> WorkspaceSearchRecord:
    return WorkspaceSearchRecord(
        record_id=f"{location.module_id}:{location.project_id}:{entity_type}:{entity_id}",
        module_id=location.module_id,
        workspace_id=location.workspace_id,
        project_id=location.project_id,
        project_title=location.title,
        project_root=location.root,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        summary=summary,
        labels=tuple(label for label in labels if label),
        source_version_id=source_version_id,
        updated_at=updated_at,
    )


def _project_summary(state: Mapping[str, Any]) -> str:
    return " ".join(
        str(state.get(key, ""))
        for key in (
            "production_goal",
            "study_goal",
            "research_question",
            "known_context",
            "notes",
            "synthesis_notes",
        )
    )


def _default_review_center_root() -> Path:
    local = os.getenv("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "GATalk" / "review-control"
