from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageCms

from scenelens.imaging.loader import load_image


@pytest.mark.parametrize("extension", [".png", ".jpg", ".jpeg", ".webp"])
def test_supported_formats_and_chinese_space_path(tmp_path: Path, extension: str):
    folder = tmp_path / "中文 项目"
    folder.mkdir()
    path = folder / f"测试 图片{extension}"
    Image.new("RGB", (24, 16), (30, 90, 150)).save(path)
    before = path.read_bytes()

    loaded = load_image(path)

    assert loaded.source_path == path
    assert loaded.working_size == (24, 16)
    assert loaded.rgb.shape == (16, 24, 3)
    assert path.read_bytes() == before


def test_exif_orientation_is_applied_without_modifying_source(tmp_path: Path):
    path = tmp_path / "方向 测试.jpg"
    image = Image.new("RGB", (20, 30), (100, 120, 140))
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    before = path.read_bytes()

    loaded = load_image(path)

    assert loaded.original_size == (20, 30)
    assert loaded.working_size == (30, 20)
    assert loaded.exif_orientation == 6
    assert loaded.exif_orientation_applied is True
    assert path.read_bytes() == before


def test_embedded_srgb_profile_is_detected_and_converted(tmp_path: Path):
    path = tmp_path / "带 ICC.png"
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    Image.new("RGB", (16, 12), (40, 80, 120)).save(
        path,
        icc_profile=profile.tobytes(),
    )

    loaded = load_image(path)

    assert loaded.icc_converted_to_srgb is True
    assert loaded.assumed_srgb is False
    assert loaded.warnings == ()
    assert np.mean(loaded.rgb, axis=(0, 1)).tolist() == pytest.approx(
        [40, 80, 120],
        abs=1,
    )
