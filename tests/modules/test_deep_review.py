from __future__ import annotations

import copy

import numpy as np

from scenelens.modules.visual_review.review_coordinator import (
    ReviewCoordinator,
    ReviewRunOptions,
)
from scenelens.modules.visual_review.review_evidence import (
    build_review_evidence_digest,
)
from scenelens.modules.visual_review.reviews import (
    DeepArtDirectorReview,
    ReviewContext,
)
from scenelens.providers.contracts import (
    CancellationToken,
    ProviderImage,
)
from scenelens.providers.mock import MockProvider, _default_mock_output
from scenelens.providers.registry import ProviderRegistry
from scenelens.providers.schema_adapters import schema_output_template


def _context() -> ReviewContext:
    return ReviewContext(
        project_id="project",
        shot_id="shot",
        version_id="version",
        creative_intent={"production_stage": {"value": "灯光初版"}},
        reference_visual_brief={},
        global_measurements={},
        local_evidence_digest={"digest_version": "1.0.0"},
    )


def _images() -> tuple[ProviderImage, ...]:
    return (
        ProviderImage("reference", "image/png", b"reference"),
        ProviderImage("current", "image/png", b"current"),
    )


def test_review_evidence_digest_is_bounded_reproducible_and_directional() -> None:
    reference = np.full((600, 1200, 3), 32, dtype=np.uint8)
    current = np.full((600, 1200, 3), 192, dtype=np.uint8)

    first = build_review_evidence_digest(
        reference,
        current,
        low_threshold=0.3,
        high_threshold=0.7,
        maximum_side=128,
    )
    second = build_review_evidence_digest(
        reference,
        current,
        low_threshold=0.3,
        high_threshold=0.7,
        maximum_side=128,
    )

    assert first == second
    assert max(first["current"]["sample_dimensions"]) <= 128
    assert first["current_minus_reference"]["mean_luminance"] > 0.0
    assert len(first["current"]["spatial_grid"]) == 9


def test_deep_review_default_mock_is_strict_and_requests_room_for_detail() -> None:
    registry = ProviderRegistry()
    registry.register(MockProvider())
    reviewer = DeepArtDirectorReview()
    coordinator = ReviewCoordinator(
        registry,
        {"deep_art_director_review": reviewer},
    )
    image = np.full((16, 16, 3), 100, dtype=np.uint8)

    request = reviewer.create_request(_context(), _images())
    assert request.max_output_tokens == 12000
    assert request.payload["local_evidence_digest"]["digest_version"] == "1.0.0"

    outcome = coordinator.run(
        options=ReviewRunOptions("deep_art_director_review", "mock"),
        context=_context(),
        images=_images(),
        current_rgb=image,
        reference_rgb=image,
        credentials={},
        cancellation=CancellationToken(),
    )
    assert len(outcome.output["dimension_reviews"]) == 8
    assert outcome.output["findings"] == []
    coordinator.close()


def test_deep_review_claim_conflict_is_retained_and_confidence_downgraded() -> None:
    reviewer = DeepArtDirectorReview()
    output = copy.deepcopy(_default_mock_output(reviewer.output_schema))
    output["dimension_reviews"][4]["linked_finding_ids"] = ["value-1"]
    output["findings"] = [
        {
            "finding_id": "value-1",
            "dimension_ids": ["value_structure"],
            "observation": "当前画面整体偏暗。",
            "image_evidence": "画面大面积处于暗部。",
            "measurement_evidence": [],
            "linked_image_role": "current",
            "linked_region_ids": [],
            "evidence_claims": [
                {
                    "claim_id": "dark-all",
                    "description": "全图平均明度不高于 0.2。",
                    "current_rect": {
                        "x": 0.0,
                        "y": 0.0,
                        "width": 1.0,
                        "height": 1.0,
                    },
                    "reference_rect": None,
                    "metric": "mean_luminance",
                    "operator": "<=",
                    "threshold": 0.2,
                    "tolerance": 0.05,
                    "confidence": 0.9,
                }
            ],
            "impact": "可读性风险。",
            "recommended_action": "先核对曝光。",
            "priority": "high",
            "confidence": 0.9,
            "counterevidence_or_uncertainty": "需要测量复核。",
            "next_version_validation": "复测平均明度。",
        }
    ]
    registry = ProviderRegistry()
    registry.register(MockProvider(output=output))
    coordinator = ReviewCoordinator(
        registry,
        {"deep_art_director_review": reviewer},
    )
    bright = np.full((32, 32, 3), 240, dtype=np.uint8)

    outcome = coordinator.run(
        options=ReviewRunOptions("deep_art_director_review", "mock"),
        context=_context(),
        images=_images(),
        current_rgb=bright,
        reference_rgb=bright,
        credentials={},
        cancellation=CancellationToken(),
    )

    validation = outcome.component_validations[0]
    assert validation.status.value == "conflict"
    assert validation.adjusted_confidence < 0.9
    assert outcome.output["findings"][0]["observation"] == "当前画面整体偏暗。"
    coordinator.close()


def test_deep_review_drops_only_dangling_finding_links() -> None:
    reviewer = DeepArtDirectorReview()
    output = copy.deepcopy(_default_mock_output(reviewer.output_schema))
    finding = schema_output_template(
        reviewer.output_schema["properties"]["findings"]["items"]
    )
    finding["finding_id"] = "find-real"
    finding["dimension_ids"] = ["composition"]
    finding["evidence_claims"] = []
    output["findings"] = [finding]
    output["dimension_reviews"][0]["linked_finding_ids"] = [
        "find-real",
        "find_smoke_particle",
    ]
    output["dimension_reviews"][3]["linked_finding_ids"] = [
        "find_skybox_color"
    ]
    action = schema_output_template(
        reviewer.output_schema["properties"]["action_plan"]["items"]
    )
    action["order"] = 1
    action["finding_ids"] = ["find-real", "find_action_missing"]
    output["action_plan"] = [action]
    registry = ProviderRegistry()
    registry.register(MockProvider(output=output))
    coordinator = ReviewCoordinator(
        registry,
        {"deep_art_director_review": reviewer},
    )
    image = np.full((16, 16, 3), 100, dtype=np.uint8)

    outcome = coordinator.run(
        options=ReviewRunOptions("deep_art_director_review", "mock"),
        context=_context(),
        images=_images(),
        current_rgb=image,
        reference_rgb=image,
        credentials={},
        cancellation=CancellationToken(),
    )

    assert output["dimension_reviews"][0]["linked_finding_ids"] == [
        "find-real",
        "find_smoke_particle",
    ]
    assert outcome.output["dimension_reviews"][0]["linked_finding_ids"] == [
        "find-real"
    ]
    assert outcome.output["dimension_reviews"][3]["linked_finding_ids"] == []
    assert outcome.output["action_plan"][0]["finding_ids"] == ["find-real"]
    assert len(outcome.normalization_warnings) == 3
    assert "find_smoke_particle" in outcome.normalization_warnings[0]
    assert "find_skybox_color" in outcome.normalization_warnings[1]
    assert "find_action_missing" in outcome.normalization_warnings[2]
    coordinator.close()
