"""User-facing storage exceptions."""


class StorageError(RuntimeError):
    """Base class for project storage failures."""


class ProjectFormatError(StorageError):
    """The selected directory is not a valid SceneLens project."""


class ProjectVersionError(StorageError):
    """The project is newer than this application can safely write."""


class ProjectSaveError(StorageError):
    """A requested change could not be saved safely."""
