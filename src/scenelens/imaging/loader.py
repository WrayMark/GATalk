from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageCms, ImageOps

from scenelens.analysis.models import UInt8Image


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
EXIF_ORIENTATION_TAG = 274


@dataclass(frozen=True)
class LoadedImage:
    source_path: Path
    rgb: UInt8Image
    alpha: NDArray[np.uint8] | None
    source_format: str
    original_size: tuple[int, int]
    working_size: tuple[int, int]
    exif_orientation: int | None
    exif_orientation_applied: bool
    icc_converted_to_srgb: bool
    assumed_srgb: bool
    warnings: tuple[str, ...]


def is_supported_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def load_image(path: str | Path) -> LoadedImage:
    """Decode without writing to the source and normalize the working copy."""
    source_path = Path(path)
    if not source_path.is_file():
        raise ValueError(f"找不到图片文件：{source_path}")
    if not is_supported_image(source_path):
        raise ValueError("仅支持 PNG、JPG、JPEG 和 WebP 图片。")

    notices: list[str] = []
    try:
        with Image.open(source_path) as source:
            source.load()
            source_format = source.format or source_path.suffix.lstrip(".").upper()
            original_size = source.size
            orientation = source.getexif().get(EXIF_ORIENTATION_TAG, 1)
            oriented = ImageOps.exif_transpose(source)
            orientation_applied = orientation not in (None, 1)

            alpha = None
            if "A" in oriented.getbands():
                alpha = np.asarray(oriented.getchannel("A"), dtype=np.uint8).copy()

            icc_bytes = source.info.get("icc_profile")
            converted = False
            if icc_bytes:
                try:
                    source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
                    target_profile = ImageCms.createProfile("sRGB")
                    profile_input = oriented
                    if profile_input.mode not in {"RGB", "CMYK", "LAB", "L"}:
                        profile_input = profile_input.convert("RGB")
                    rgb_image = ImageCms.profileToProfile(
                        profile_input,
                        source_profile,
                        target_profile,
                        outputMode="RGB",
                        renderingIntent=ImageCms.Intent.PERCEPTUAL,
                    )
                    converted = True
                except (OSError, ValueError, ImageCms.PyCMSError) as exc:
                    notices.append(f"ICC 配置无法转换，已按 sRGB 读取：{exc}")
                    rgb_image = oriented.convert("RGB")
            else:
                rgb_image = oriented.convert("RGB")

            rgb = np.asarray(rgb_image, dtype=np.uint8).copy()
            return LoadedImage(
                source_path=source_path,
                rgb=np.ascontiguousarray(rgb),
                alpha=None if alpha is None else np.ascontiguousarray(alpha),
                source_format=str(source_format),
                original_size=original_size,
                working_size=rgb_image.size,
                exif_orientation=(
                    int(orientation) if orientation is not None else None
                ),
                exif_orientation_applied=orientation_applied,
                icc_converted_to_srgb=converted,
                assumed_srgb=not converted,
                warnings=tuple(notices),
            )
    except Image.UnidentifiedImageError as exc:
        raise ValueError("无法识别该图片，文件可能已损坏或扩展名不正确。") from exc
    except OSError as exc:
        raise ValueError(f"无法读取图片：{exc}") from exc
