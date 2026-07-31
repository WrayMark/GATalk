from __future__ import annotations

import json
import os
import socket
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from scenelens import __version__
from scenelens.storage.errors import ProjectLockedError


LOCK_FILENAME = ".scenelens.write.lock"
_PROCESS_LOCKS: set[Path] = set()
_PROCESS_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class ProjectLockInfo:
    lock_id: str
    project_id: str
    pid: int
    hostname: str
    app_version: str
    acquired_at: str
    state: str = "active"

    def to_dict(self) -> dict[str, str | int]:
        return {
            "format_version": 1,
            "lock_id": self.lock_id,
            "project_id": self.project_id,
            "pid": self.pid,
            "hostname": self.hostname,
            "app_version": self.app_version,
            "acquired_at": self.acquired_at,
            "state": self.state,
        }


class ProjectWriteLock:
    """One-byte OS lock with diagnostic metadata.

    The operating-system lock is authoritative and is released automatically
    after a crash. The JSON metadata may remain after an abnormal exit; a
    successful OS lock acquisition treats active metadata as stale and
    replaces it.
    """

    def __init__(
        self,
        path: Path,
        handle: BinaryIO,
        info: ProjectLockInfo,
        recovered_stale_lock: bool,
    ) -> None:
        self.path = Path(path)
        self._handle = handle
        self.info = info
        self.recovered_stale_lock = recovered_stale_lock
        self._released = False

    @classmethod
    def acquire(
        cls,
        project_root: Path,
        project_id: str,
        acquired_at: str,
    ) -> ProjectWriteLock:
        path = (Path(project_root).resolve() / LOCK_FILENAME).resolve()
        with _PROCESS_LOCKS_GUARD:
            if path in _PROCESS_LOCKS:
                owner = read_lock_metadata(path)
                raise ProjectLockedError(
                    _locked_message(owner),
                    owner,
                )

        path.parent.mkdir(parents=True, exist_ok=True)
        # msvcrt.locking uses the C file descriptor's position. An unbuffered
        # handle keeps Python's seek position and the descriptor position equal.
        handle = path.open("a+b", buffering=0)
        existing = _read_metadata_from_handle(handle)
        try:
            _lock_file(handle)
        except OSError as exc:
            handle.close()
            owner = read_lock_metadata(path)
            raise ProjectLockedError(_locked_message(owner), owner) from exc

        info = ProjectLockInfo(
            lock_id=str(uuid.uuid4()),
            project_id=project_id,
            pid=os.getpid(),
            hostname=socket.gethostname(),
            app_version=__version__,
            acquired_at=acquired_at,
        )
        recovered = bool(existing and existing.get("state") == "active")
        _write_metadata(handle, info.to_dict())
        with _PROCESS_LOCKS_GUARD:
            _PROCESS_LOCKS.add(path)
        return cls(path, handle, info, recovered)

    def release(self) -> None:
        if self._released:
            return
        try:
            released = {
                **self.info.to_dict(),
                "state": "released",
            }
            _write_metadata(self._handle, released)
            _unlock_file(self._handle)
        finally:
            self._handle.close()
            with _PROCESS_LOCKS_GUARD:
                _PROCESS_LOCKS.discard(self.path)
            self._released = True

    def __enter__(self) -> ProjectWriteLock:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


def read_lock_metadata(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_metadata_from_handle(handle: BinaryIO) -> dict:
    try:
        handle.seek(0)
        raw = handle.read().decode("utf-8")
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, UnicodeDecodeError, ValueError):
        return {}


def _write_metadata(handle: BinaryIO, data: dict) -> None:
    encoded = (
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    handle.seek(0)
    handle.write(encoded)
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def _lock_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        if handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _locked_message(owner: dict) -> str:
    if not owner:
        return "该项目已被另一个 GATalk 进程占用写权限。"
    host = owner.get("hostname", "未知设备")
    pid = owner.get("pid", "未知")
    acquired = owner.get("acquired_at", "未知时间")
    return (
        "该项目已被另一个 GATalk 进程占用写权限。"
        f"\n设备：{host}  进程：{pid}  打开时间：{acquired}"
    )
