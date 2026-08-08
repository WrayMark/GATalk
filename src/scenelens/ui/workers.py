from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from scenelens.core.runtime_tasks import runtime_task_center


class WorkerSignals(QObject):
    result = Signal(str, str, int, object)
    error = Signal(str, str, int, str, str)
    finished = Signal(str, str, int)


class FunctionWorker(QRunnable):
    def __init__(
        self,
        role: str,
        kind: str,
        generation: int,
        function: Callable[[], Any],
    ) -> None:
        super().__init__()
        self.role = role
        self.kind = kind
        self.generation = generation
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        tracked_kinds = {
            "analysis",
            "local",
            "load",
            "export",
            "preview",
            "mask",
        }
        task_id = None
        if self.kind in tracked_kinds:
            task_id = runtime_task_center().begin(
                title={
                    "analysis": "本地图像分析",
                    "local": "本地对照分析",
                    "load": "读取图片",
                    "export": "导出结果",
                    "preview": "生成预览",
                    "mask": "生成证据遮罩",
                }.get(self.kind, "后台任务"),
                task_type=self.kind,
                module_id=f"scenelens.{self.role}",
            )
        try:
            result = self.function()
        except Exception as exc:  # UI boundary: convert to a user-facing event.
            message_factory = getattr(exc, "to_user_message", None)
            message = (
                str(message_factory())
                if callable(message_factory)
                else str(exc)
            )
            self.signals.error.emit(
                self.role,
                self.kind,
                self.generation,
                message,
                traceback.format_exc(),
            )
            if task_id:
                runtime_task_center().fail(task_id, message)
        else:
            self.signals.result.emit(
                self.role,
                self.kind,
                self.generation,
                result,
            )
            if task_id:
                runtime_task_center().finish(task_id)
        finally:
            self.signals.finished.emit(self.role, self.kind, self.generation)
