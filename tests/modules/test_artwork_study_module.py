from dataclasses import replace
from io import BytesIO
import numpy as np
from PIL import Image

from scenelens.core.workspaces import WorkbenchRegistry
from scenelens.modules.artwork_study.reviews import (
    ArtworkMasterStudyReview,
    ArtworkStudyContext,
    STUDY_DIMENSIONS,
)
from scenelens.modules.artwork_study.storage import ArtworkStudyStore
from scenelens.modules.artwork_study.workbench import (
    register_artwork_study_workbench,
)
from scenelens.providers.contracts import CancellationToken, ProviderImage
from scenelens.providers.mock import MockProvider


def _png_bytes() -> bytes:
    rgb = np.zeros((32, 48, 3), dtype=np.uint8)
    rgb[:, :24] = (25, 55, 95)
    rgb[:, 24:] = (210, 145, 70)
    buffer = BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG")
    return buffer.getvalue()


def test_artwork_study_store_preserves_original_bytes_and_restores_state(tmp_path):
    source = tmp_path / "中文 原画.png"
    source.write_bytes(_png_bytes())
    store = ArtworkStudyStore.create(
        tmp_path / "雾中村庄.scenelens-study",
        "雾中村庄研究",
    )

    imported = store.import_image(source)
    asset_path = store.image_path()
    assert asset_path is not None
    assert asset_path.read_bytes() == source.read_bytes()
    assert imported.image_sha256

    store.save(
        replace(
            imported,
            study_goal="研究明度与空间",
            known_context="作者未知，不作归因",
            personal_notes="远景靠低对比退后",
            display_mode="grayscale",
            local_analysis={"analyzer_id": "test"},
        )
    )
    reopened = ArtworkStudyStore.open(store.root)
    assert reopened.state.study_goal == "研究明度与空间"
    assert reopened.state.display_mode == "grayscale"
    assert reopened.state.local_analysis["analyzer_id"] == "test"
    assert reopened.image_path().read_bytes() == source.read_bytes()


def test_artwork_reviewer_mock_covers_twelve_dimensions_and_validates_schema():
    reviewer = ArtworkMasterStudyReview()
    request = reviewer.create_request(
        ArtworkStudyContext(
            study_id="study",
            title="test",
            work_type="environment_concept",
            study_goal="理解构图与气氛",
            known_context="",
            image_metadata={"width": 64, "height": 48},
            local_evidence={"value_structure": {}},
        ),
        (ProviderImage("artwork", "image/png", _png_bytes()),),
        user_initiated=True,
        disclosure_confirmed=True,
    )
    response = MockProvider().review(request, "", CancellationToken())
    output = reviewer.validate_output(response.output)

    dimensions = {
        item["dimension_id"] for item in output["dimension_studies"]
    }
    assert dimensions == set(STUDY_DIMENSIONS)
    assert output["reading_scope"]["visible_content"].startswith("离线 Mock")
    assert "不是实际美术分析" in output["executive_thesis"]


def test_artwork_workbench_registers_as_independent_module():
    registry = WorkbenchRegistry()
    register_artwork_study_workbench(registry)

    workspace = registry.workspaces()[0]
    reviewer = registry.reviewers()[0]
    assert workspace.module_id == "scenelens.artwork_study"
    assert workspace.display_name == "作品研究"
    assert reviewer.reviewer_id == "artwork_master_study"
