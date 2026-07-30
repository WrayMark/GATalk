from PIL import Image

from scenelens.imaging.loader import load_image
from scenelens.imaging.provider_export import (
    ProviderImageExportOptions,
    prepare_provider_image,
)
from scenelens.modules.asset_breakdown.automatic import (
    run_automatic_pipeline,
)
from scenelens.modules.asset_breakdown.reviews import (
    AssetBreakdownContext,
    AssetBreakdownReview,
)
from scenelens.providers.contracts import CancellationToken
from scenelens.providers.execution import ProviderExecutionService
from scenelens.providers.mock import MockProvider


def test_automatic_pipeline_generates_all_without_mutating_manual_state(
    tmp_path,
) -> None:
    source = tmp_path / "scene.png"
    Image.new("RGB", (320, 180), (50, 90, 70)).save(source)
    loaded = load_image(source)
    main = prepare_provider_image(
        loaded,
        "main_concept",
        ProviderImageExportOptions(maximum_side=2048),
    )
    reviewer = AssetBreakdownReview()
    context = AssetBreakdownContext(
        project_id="project",
        title="scene",
        scene_type="general_environment",
        scene_focus=(),
        production_goal="",
        image_metadata={"width": 320, "height": 180},
        supplemental_references=(),
    )
    request = reviewer.create_request(
        context,
        (main,),
        model_id="mock-vision-v1",
        user_initiated=True,
        disclosure_confirmed=True,
    )
    provider = MockProvider()
    execution = ProviderExecutionService(sleep=lambda _seconds: None)
    try:
        result = run_automatic_pipeline(
            reviewer=reviewer,
            review_provider=provider,
            review_request=request,
            review_credential="",
            image_provider=provider,
            image_credential="",
            image_model_id="mock-image-v1",
            image_resolution="1K",
            full_scene=main,
            rgb=loaded.rgb,
            source_image_id="source",
            scene_type="general_environment",
            output_kind="isolated_concept",
            asset_limit=8,
            execution=execution,
            cancellation=CancellationToken(),
        )
    finally:
        execution.close()
    assert len(result.assets) == 2
    assert len(result.generated) == 2
    assert not result.failures
    assert all(item.image_bytes.startswith(b"\x89PNG") for item in result.generated)
    assert all(
        item.instruction["output_resolution"] == "1K"
        for item in result.generated
    )
