from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


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
        else:
            self.signals.result.emit(
                self.role,
                self.kind,
                self.generation,
                result,
            )
        finally:
            self.signals.finished.emit(self.role, self.kind, self.generation)
