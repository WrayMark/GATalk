from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scenelens.storage.errors import (
    ProjectLockedError,
    ProjectReadOnlyError,
)
from scenelens.storage.project_lock import LOCK_FILENAME
from scenelens.storage.project_store import ProjectStore


def test_second_process_is_read_only_until_writer_exits(tmp_path: Path):
    root = tmp_path / "多进程 中文项目.scenelens"
    initial = ProjectStore.create(root, "多进程测试")
    initial.create_shot("镜头")
    initial.close()

    script = """
import sys
from pathlib import Path
from scenelens.storage.project_store import ProjectStore
store = ProjectStore.open(Path(sys.argv[1]))
print("LOCKED", flush=True)
sys.stdin.readline()
store.close()
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path.cwd() / "src")
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(root)],
        cwd=Path.cwd(),
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "LOCKED"

        with pytest.raises(ProjectLockedError):
            ProjectStore.open(root)

        read_only = ProjectStore.open(root, read_only=True)
        assert read_only.read_only
        assert len(read_only.list_shots()) == 1
        with pytest.raises(ProjectReadOnlyError):
            read_only.create_shot("不能写入")
        read_only.close()
    finally:
        if process.stdin is not None:
            process.stdin.write("\n")
            process.stdin.flush()
        process.wait(timeout=10)
        if process.poll() is None:
            process.kill()
    assert process.returncode == 0, (
        process.stderr.read() if process.stderr is not None else ""
    )

    writable = ProjectStore.open(root)
    assert not writable.read_only
    writable.close()


def test_active_metadata_without_os_lock_is_recovered_as_stale(tmp_path: Path):
    root = tmp_path / "陈旧锁.scenelens"
    store = ProjectStore.create(root, "陈旧锁")
    store.close()
    lock_path = root / LOCK_FILENAME
    lock_path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "lock_id": "old-lock",
                "project_id": "old-project",
                "pid": 999999,
                "hostname": "old-host",
                "app_version": "0.0.0",
                "acquired_at": "2000-01-01T00:00:00.000Z",
                "state": "active",
            }
        ),
        encoding="utf-8",
    )

    reopened = ProjectStore.open(root)

    assert reopened.recovered_stale_lock
    reopened.close()
