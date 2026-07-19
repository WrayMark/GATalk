from __future__ import annotations

import json
import os
import uuid
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from scenelens.providers.contracts import ProviderImage


def write_offline_review_pack(
    destination: Path,
    manifest: Mapping[str, Any],
    images: Sequence[ProviderImage],
) -> Path:
    """Write a self-contained ZIP atomically after explicit user action."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            archive.writestr(
                "review_request.json",
                json.dumps(
                    dict(manifest),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            for index, image in enumerate(images, start=1):
                extension = {
                    "image/png": ".png",
                    "image/jpeg": ".jpg",
                    "image/webp": ".webp",
                }.get(image.media_type, ".bin")
                archive.writestr(
                    f"images/{index:02d}-{image.role}{extension}",
                    image.data,
                )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination
