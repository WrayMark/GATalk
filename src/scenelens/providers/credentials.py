from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Protocol


class CredentialStore(Protocol):
    def set(self, target: str, secret: str) -> None:
        """Store a provider credential outside project data."""

    def get(self, target: str) -> str | None:
        """Read a provider credential."""

    def delete(self, target: str) -> None:
        """Delete a provider credential."""


class MemoryCredentialStore:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set(self, target: str, secret: str) -> None:
        if not target or not secret:
            raise ValueError("Credential target and secret must not be empty.")
        self._values[target] = secret

    def get(self, target: str) -> str | None:
        return self._values.get(target)

    def delete(self, target: str) -> None:
        self._values.pop(target, None)


class WindowsCredentialStore:
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    def __init__(self, prefix: str = "SceneLens") -> None:
        if sys.platform != "win32":
            raise OSError("Windows Credential Manager is only available on Windows.")
        self.prefix = prefix.strip("/")
        self._advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self._advapi.CredWriteW.argtypes = [
            ctypes.POINTER(self.CREDENTIALW),
            wintypes.DWORD,
        ]
        self._advapi.CredWriteW.restype = wintypes.BOOL
        self._advapi.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(self.CREDENTIALW)),
        ]
        self._advapi.CredReadW.restype = wintypes.BOOL
        self._advapi.CredDeleteW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self._advapi.CredDeleteW.restype = wintypes.BOOL
        self._advapi.CredFree.argtypes = [ctypes.c_void_p]
        self._advapi.CredFree.restype = None

    def target_name(self, target: str) -> str:
        value = target.strip("/")
        if not value:
            raise ValueError("Credential target must not be empty.")
        if value.startswith(f"{self.prefix}/"):
            return value
        return f"{self.prefix}/{value}"

    def set(self, target: str, secret: str) -> None:
        if not secret:
            raise ValueError("Credential secret must not be empty.")
        name = self.target_name(target)
        blob = secret.encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = self.CREDENTIALW()
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = name
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(
            buffer,
            ctypes.POINTER(ctypes.c_ubyte),
        )
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "SceneLens"
        if not self._advapi.CredWriteW(ctypes.byref(credential), 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def get(self, target: str) -> str | None:
        name = self.target_name(target)
        pointer = ctypes.POINTER(self.CREDENTIALW)()
        if not self._advapi.CredReadW(
            name,
            self.CRED_TYPE_GENERIC,
            0,
            ctypes.byref(pointer),
        ):
            error = ctypes.get_last_error()
            if error == self.ERROR_NOT_FOUND:
                return None
            raise ctypes.WinError(error)
        try:
            credential = pointer.contents
            if not credential.CredentialBlobSize:
                return ""
            raw = ctypes.string_at(
                credential.CredentialBlob,
                credential.CredentialBlobSize,
            )
            return raw.decode("utf-16-le")
        finally:
            self._advapi.CredFree(pointer)

    def delete(self, target: str) -> None:
        name = self.target_name(target)
        if not self._advapi.CredDeleteW(
            name,
            self.CRED_TYPE_GENERIC,
            0,
        ):
            error = ctypes.get_last_error()
            if error != self.ERROR_NOT_FOUND:
                raise ctypes.WinError(error)

