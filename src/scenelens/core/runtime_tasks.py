from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import StrEnum
import os
from pathlib import Path
import threading
from typing import Any, Callable, Mapping
import uuid

from scenelens.storage.atomic import atomic_write_json, load_json
from scenelens.storage.project_store import utc_now


class RuntimeTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class RuntimeTask:
    task_id: str
    title: str
    task_type: str
    module_id: str
    provider_id: str
    model_id: str
    status: RuntimeTaskStatus
    created_at: str
    updated_at: str
    progress_current: int = 0
    progress_total: int = 0
    attempt: int = 0
    max_attempts: int = 0
    input_summary: Mapping[str, Any] | None = None
    public_error: str = ""
    technical_error: str = ""
    output_location: str = ""
    can_cancel: bool = False
    can_retry: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["input_summary"] = dict(self.input_summary or {})
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RuntimeTask:
        status = RuntimeTaskStatus(str(value.get("status", "failed")))
        if status in {RuntimeTaskStatus.QUEUED, RuntimeTaskStatus.RUNNING}:
            status = RuntimeTaskStatus.INTERRUPTED
        return cls(
            task_id=str(value["task_id"]),
            title=str(value.get("title", "后台任务")),
            task_type=str(value.get("task_type", "unknown")),
            module_id=str(value.get("module_id", "gatalk.core")),
            provider_id=str(value.get("provider_id", "")),
            model_id=str(value.get("model_id", "")),
            status=status,
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
            progress_current=int(value.get("progress_current", 0)),
            progress_total=int(value.get("progress_total", 0)),
            attempt=int(value.get("attempt", 0)),
            max_attempts=int(value.get("max_attempts", 0)),
            input_summary=dict(value.get("input_summary", {})),
            public_error=str(value.get("public_error", "")),
            technical_error=str(value.get("technical_error", "")),
            output_location=str(value.get("output_location", "")),
            can_cancel=False,
            can_retry=False,
        )


def default_runtime_tasks_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) if local else Path.home() / "AppData" / "Local"
    return root / "GATalk" / "runtime-tasks.json"


class RuntimeTaskCenter:
    """Process-wide task ledger. It never stores credentials or payload text."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_runtime_tasks_path()
        self._lock = threading.RLock()
        self._tasks: dict[str, RuntimeTask] = {}
        self._cancellers: dict[str, Callable[[], None]] = {}
        self._retry_callbacks: dict[str, Callable[[], None]] = {}
        self.persistence_error = ""
        self._load()

    def begin(
        self,
        *,
        title: str,
        task_type: str,
        module_id: str,
        provider_id: str = "",
        model_id: str = "",
        input_summary: Mapping[str, Any] | None = None,
        progress_total: int = 0,
        max_attempts: int = 0,
        cancel: Callable[[], None] | None = None,
        retry: Callable[[], None] | None = None,
    ) -> str:
        now = utc_now()
        task_id = str(uuid.uuid4())
        task = RuntimeTask(
            task_id=task_id,
            title=title.strip() or "后台任务",
            task_type=task_type,
            module_id=module_id,
            provider_id=provider_id,
            model_id=model_id,
            status=RuntimeTaskStatus.RUNNING,
            created_at=now,
            updated_at=now,
            progress_total=max(0, int(progress_total)),
            max_attempts=max(0, int(max_attempts)),
            input_summary=dict(input_summary or {}),
            can_cancel=cancel is not None,
            can_retry=retry is not None,
        )
        with self._lock:
            self._tasks[task_id] = task
            if cancel is not None:
                self._cancellers[task_id] = cancel
            if retry is not None:
                self._retry_callbacks[task_id] = retry
            self._save()
        return task_id

    def update(self, task_id: str, **changes: Any) -> RuntimeTask:
        with self._lock:
            current = self._tasks[task_id]
            allowed = {
                "title",
                "provider_id",
                "model_id",
                "status",
                "progress_current",
                "progress_total",
                "attempt",
                "max_attempts",
                "public_error",
                "technical_error",
                "output_location",
                "can_cancel",
                "can_retry",
            }
            normalized = {key: value for key, value in changes.items() if key in allowed}
            if "status" in normalized:
                normalized["status"] = RuntimeTaskStatus(normalized["status"])
            updated = replace(current, updated_at=utc_now(), **normalized)
            self._tasks[task_id] = updated
            self._save()
            return updated

    def finish(
        self,
        task_id: str,
        *,
        status: RuntimeTaskStatus = RuntimeTaskStatus.COMPLETED,
        output_location: str = "",
    ) -> RuntimeTask:
        with self._lock:
            self._cancellers.pop(task_id, None)
            return self.update(
                task_id,
                status=status,
                output_location=output_location,
                can_cancel=False,
            )

    def fail(self, task_id: str, public_error: str, technical_error: str = "") -> RuntimeTask:
        with self._lock:
            self._cancellers.pop(task_id, None)
            return self.update(
                task_id,
                status=RuntimeTaskStatus.FAILED,
                public_error=public_error,
                technical_error=technical_error,
                can_cancel=False,
            )

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            callback = self._cancellers.get(task_id)
        if callback is None:
            return False
        callback()
        self.finish(task_id, status=RuntimeTaskStatus.CANCELLED)
        return True

    def retry(self, task_id: str) -> bool:
        with self._lock:
            callback = self._retry_callbacks.get(task_id)
        if callback is None:
            return False
        callback()
        return True

    def tasks(self) -> tuple[RuntimeTask, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._tasks.values(),
                    key=lambda item: item.updated_at,
                    reverse=True,
                )
            )

    def clear_finished(self) -> None:
        active = {RuntimeTaskStatus.QUEUED, RuntimeTaskStatus.RUNNING}
        with self._lock:
            self._tasks = {
                key: value for key, value in self._tasks.items() if value.status in active
            }
            self._cancellers = {
                key: value for key, value in self._cancellers.items() if key in self._tasks
            }
            self._retry_callbacks = {
                key: value for key, value in self._retry_callbacks.items() if key in self._tasks
            }
            self._save()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            value = load_json(self.path)
            for raw in value.get("tasks", []):
                task = RuntimeTask.from_dict(raw)
                self._tasks[task.task_id] = task
            self._save()
        except (OSError, TypeError, ValueError, KeyError):
            self._tasks = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                self.path,
                {
                    "format": "gatalk.runtime_tasks",
                    "format_version": 1,
                    "tasks": [item.to_dict() for item in self.tasks()[:200]],
                },
            )
            self.persistence_error = ""
        except OSError as exc:
            # Task visibility must remain available in memory even when a
            # locked-down Windows profile does not allow AppData writes.
            self.persistence_error = str(exc)


_DEFAULT_CENTER: RuntimeTaskCenter | None = None
_DEFAULT_LOCK = threading.Lock()


def runtime_task_center() -> RuntimeTaskCenter:
    global _DEFAULT_CENTER
    with _DEFAULT_LOCK:
        if _DEFAULT_CENTER is None:
            _DEFAULT_CENTER = RuntimeTaskCenter()
        return _DEFAULT_CENTER
