"""User-facing storage exceptions."""


class StorageError(RuntimeError):
    """Base class for project storage failures."""


class ProjectFormatError(StorageError):
    """The selected directory is not a valid SceneLens project."""


class ProjectVersionError(StorageError):
    """The project is newer than this application can safely write."""


class ProjectSaveError(StorageError):
    """A requested change could not be saved safely."""


class ProjectReadOnlyError(ProjectSaveError):
    """The project was opened without write permission."""


class ProjectLockedError(StorageError):
    """Another process currently owns the project write lock."""

    def __init__(self, message: str, owner: dict | None = None) -> None:
        super().__init__(message)
        self.owner = owner or {}
