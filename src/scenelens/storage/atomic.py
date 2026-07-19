from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                data,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_json(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层必须是对象。")
    return data


def canonical_json(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class StagedAsset:
    temporary_path: Path
    sha256: str
    byte_size: int
    normalized_extension: str


def stage_asset_copy(source: Path, staging_directory: Path) -> StagedAsset:
    source = Path(source)
    extension = source.suffix.lower()
    normalized = ".jpg" if extension == ".jpeg" else extension
    staging_directory.mkdir(parents=True, exist_ok=True)
    temporary = staging_directory / f".import-{uuid.uuid4().hex}{normalized}"
    digest = hashlib.sha256()
    byte_size = 0
    try:
        with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
            while True:
                chunk = input_handle.read(1024 * 1024)
                if not chunk:
                    break
                output_handle.write(chunk)
                digest.update(chunk)
                byte_size += len(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        return StagedAsset(
            temporary_path=temporary,
            sha256=digest.hexdigest(),
            byte_size=byte_size,
            normalized_extension=normalized,
        )
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def cache_key_for(parts: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(parts).encode("utf-8")).hexdigest()
