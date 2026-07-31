from pathlib import Path

from scenelens.storage.atomic import atomic_write_json
from scenelens.storage.recent_projects import RecentProjects


def test_recent_projects_are_ordered_deduplicated_and_keep_missing_paths(
    tmp_path: Path,
):
    recent = RecentProjects(tmp_path / "local" / "recent-projects.json", limit=2)
    first = tmp_path / "项目一" / "project.json"
    second = tmp_path / "项目二" / "project.json"
    first.parent.mkdir()
    first.write_text("{}", encoding="utf-8")

    recent.add("one", "项目一", first, "2026-07-19T01:00:00.000Z")
    recent.add("two", "项目二", second, "2026-07-19T02:00:00.000Z")
    recent.add("one", "项目一（重命名）", first, "2026-07-19T03:00:00.000Z")

    loaded = recent.load()
    assert [item.project_id for item in loaded] == ["one", "two"]
    assert loaded[0].name == "项目一（重命名）"
    assert loaded[0].is_available
    assert not loaded[1].is_available


def test_default_store_reads_legacy_scenelens_list(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    manifest = tmp_path / "旧项目" / "project.json"
    manifest.parent.mkdir()
    manifest.write_text("{}", encoding="utf-8")
    atomic_write_json(
        tmp_path / "SceneLens" / "recent-projects.json",
        {
            "format_version": 1,
            "projects": [
                {
                    "project_id": "legacy",
                    "name": "旧 SceneLens 项目",
                    "manifest_path": str(manifest),
                    "last_opened_at": "2026-07-31T00:00:00.000Z",
                }
            ],
        },
    )

    recent = RecentProjects()
    loaded = recent.load()

    assert recent.path == tmp_path / "GATalk" / "recent-projects.json"
    assert loaded[0].project_id == "legacy"
    recent.add(
        "new",
        "GATalk 项目",
        manifest,
        "2026-07-31T01:00:00.000Z",
    )
    assert recent.path.is_file()
