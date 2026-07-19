from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

from scenelens.imaging.loader import LoadedImage
from scenelens.providers.contracts import ProviderImage


@dataclass(frozen=True)
class ProviderImageExportOptions:
    remove_metadata: bool = True
    maximum_side: int | None = 2048


def prepare_provider_image(
    loaded: LoadedImage,
    role: str,
    options: ProviderImageExportOptions,
) -> ProviderImage:
    """Create an in-memory send copy without modifying the source asset."""

    if options.maximum_side is not None and options.maximum_side < 64:
        raise ValueError("maximum_side must be at least 64 or None")
    if not options.remove_metadata and options.maximum_side is None:
        suffix = loaded.source_path.suffix.lower()
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".png": "image/png",
        }.get(suffix, "application/octet-stream")
        if not media_type.startswith("image/"):
            raise ValueError("源文件不是支持的图片格式。")
        return ProviderImage(
            role=role,
            media_type=media_type,
            data=loaded.source_path.read_bytes(),
        )

    image = Image.fromarray(np.ascontiguousarray(loaded.rgb), mode="RGB")
    if options.maximum_side is not None:
        maximum = int(options.maximum_side)
        if max(image.size) > maximum:
            image.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    # Creating a new PNG from the normalized working pixels intentionally
    # leaves EXIF, ICC and local paths behind.
    image.save(buffer, format="PNG", optimize=False)
    return ProviderImage(
        role=role,
        media_type="image/png",
        data=buffer.getvalue(),
    )
