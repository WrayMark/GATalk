from pathlib import Path

import numpy as np
from PIL import Image

from scenelens.imaging.loader import LoadedImage
from scenelens.imaging.provider_export import (
    ProviderImageExportOptions,
    prepare_provider_image,
)


def _loaded(path: Path) -> LoadedImage:
    rgb = np.full((100, 200, 3), (80, 120, 160), dtype=np.uint8)
    return LoadedImage(
        source_path=path,
        rgb=rgb,
        alpha=None,
        source_format="JPEG",
        original_size=(200, 100),
        working_size=(200, 100),
        exif_orientation=1,
        exif_orientation_applied=False,
        icc_converted_to_srgb=False,
        assumed_srgb=True,
        warnings=(),
    )


def test_provider_copy_downsizes_and_removes_metadata(tmp_path: Path) -> None:
    source = tmp_path / "原图.jpg"
    image = Image.new("RGB", (200, 100), (80, 120, 160))
    exif = Image.Exif()
    exif[270] = "secret description"
    image.save(source, exif=exif)
    result = prepare_provider_image(
        _loaded(source),
        "current",
        ProviderImageExportOptions(remove_metadata=True, maximum_side=64),
    )
    assert result.media_type == "image/png"
    with Image.open(__import__("io").BytesIO(result.data)) as sent:
        assert sent.size == (64, 32)
        assert not sent.getexif()


def test_raw_source_option_keeps_original_bytes_without_writing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "current.png"
    source.write_bytes(b"original-bytes")
    before = source.read_bytes()
    result = prepare_provider_image(
        _loaded(source),
        "current",
        ProviderImageExportOptions(
            remove_metadata=False,
            maximum_side=None,
        ),
    )
    assert result.data == b"original-bytes"
    assert source.read_bytes() == before
