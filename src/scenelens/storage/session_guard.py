from __future__ import annotations

import os
from pathlib import Path
import uuid

from scenelens.storage.atomic import atomic_write_json, load_json
from scenelens.storage.project_store import utc_now


def default_session_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) if local else Path.home() / "AppData" / "Local"
    return root / "GATalk" / "active-session.json"


class ApplicationSessionGuard:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_session_path()
        self.previous_unclean_session: dict[str, object] | None = None
        if self.path.is_file():
            try:
                self.previous_unclean_session = load_json(self.path)
            except (OSError, ValueError):
                self.previous_unclean_session = {"status": "unreadable"}
        self.session_id = str(uuid.uuid4())
        self.persistence_error = ""

    def start(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                self.path,
                {
                    "format": "gatalk.application_session",
                    "format_version": 1,
                    "session_id": self.session_id,
                    "process_id": os.getpid(),
                    "started_at": utc_now(),
                },
            )
            self.persistence_error = ""
        except OSError as exc:
            self.persistence_error = str(exc)

    def close(self) -> None:
        try:
            if self.path.is_file():
                value = load_json(self.path)
                if value.get("session_id") == self.session_id:
                    self.path.unlink()
        except (OSError, ValueError):
            pass
