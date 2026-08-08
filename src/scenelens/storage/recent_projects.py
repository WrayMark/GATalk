from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from scenelens.storage.atomic import atomic_write_json, load_json


@dataclass(frozen=True)
class RecentProject:
    project_id: str
    name: str
    manifest_path: Path
    last_opened_at: str

    @property
    def is_available(self) -> bool:
        return self.manifest_path.is_file()


class RecentProjects:
    def __init__(self, path: Path | None = None, limit: int = 12) -> None:
        legacy_path: Path | None = None
        if path is None:
            local_app_data = os.environ.get("LOCALAPPDATA")
            base = (
                Path(local_app_data)
                if local_app_data
                else Path.home() / "AppData" / "Local"
            )
            path = base / "GATalk" / "recent-projects.json"
            legacy_path = base / "SceneLens" / "recent-projects.json"
        self.path = Path(path)
        self.legacy_path = legacy_path
        self.limit = max(1, int(limit))

    def load(self) -> tuple[RecentProject, ...]:
        source = self.path
        if (
            not source.is_file()
            and self.legacy_path is not None
            and self.legacy_path.is_file()
        ):
            source = self.legacy_path
        if not source.is_file():
            return ()
        try:
            raw_items = load_json(source).get("projects", [])
            if not isinstance(raw_items, list):
                return ()
            projects: list[RecentProject] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                try:
                    projects.append(
                        RecentProject(
                            project_id=str(item["project_id"]),
                            name=str(item["name"]),
                            manifest_path=Path(str(item["manifest_path"])),
                            last_opened_at=str(item["last_opened_at"]),
                        )
                    )
                except KeyError:
                    continue
            return tuple(projects[: self.limit])
        except (OSError, ValueError):
            return ()

    def add(
        self,
        project_id: str,
        name: str,
        manifest_path: Path,
        opened_at: str,
    ) -> None:
        normalized = Path(manifest_path).resolve()
        remaining = [
            item
            for item in self.load()
            if item.project_id != project_id
            and item.manifest_path.resolve() != normalized
        ]
        projects = [
            RecentProject(
                project_id=project_id,
                name=name,
                manifest_path=normalized,
                last_opened_at=opened_at,
            ),
            *remaining,
        ][: self.limit]
        atomic_write_json(
            self.path,
            {
                "format_version": 1,
                "projects": [
                    {
                        "project_id": item.project_id,
                        "name": item.name,
                        "manifest_path": str(item.manifest_path),
                        "last_opened_at": item.last_opened_at,
                    }
                    for item in projects
                ],
            },
        )

    def relink(self, project_id: str, manifest_path: Path) -> bool:
        """Update one moved recent-project entry without changing its identity."""

        projects = list(self.load())
        normalized = Path(manifest_path).resolve()
        changed = False
        updated: list[RecentProject] = []
        for item in projects:
            if item.project_id == project_id:
                updated.append(
                    RecentProject(
                        project_id=item.project_id,
                        name=item.name,
                        manifest_path=normalized,
                        last_opened_at=item.last_opened_at,
                    )
                )
                changed = True
            else:
                updated.append(item)
        if not changed:
            return False
        atomic_write_json(
            self.path,
            {
                "format_version": 1,
                "projects": [
                    {
                        "project_id": item.project_id,
                        "name": item.name,
                        "manifest_path": str(item.manifest_path),
                        "last_opened_at": item.last_opened_at,
                    }
                    for item in updated[: self.limit]
                ],
            },
        )
        return True
