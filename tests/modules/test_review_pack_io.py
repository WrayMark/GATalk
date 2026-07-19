import json
import zipfile
from pathlib import Path

from scenelens.modules.visual_review.review_pack_io import (
    write_offline_review_pack,
)
from scenelens.providers.contracts import ProviderImage


def test_offline_review_pack_contains_schema_and_sanitized_images(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "中世纪 村庄-review.zip"
    write_offline_review_pack(
        destination,
        {
            "format": "scenelens.offline_review_pack",
            "output_schema": {"type": "object"},
        },
        (
            ProviderImage("reference", "image/png", b"ref"),
            ProviderImage("current", "image/png", b"cur"),
        ),
    )
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert "review_request.json" in names
        assert "images/01-reference.png" in names
        assert json.loads(archive.read("review_request.json"))["format"] == (
            "scenelens.offline_review_pack"
        )
