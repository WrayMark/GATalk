import copy

import numpy as np

from scenelens.modules.visual_review.review_coordinator import (
    ReviewCoordinator,
    ReviewRunOptions,
    review_outcome_from_payload,
    review_outcome_to_payload,
)
from scenelens.modules.visual_review.reviews import (
    ArtDirectorReview,
    LightingReview,
    ReviewContext,
)
from scenelens.providers.contracts import (
    CancellationToken,
    ProviderImage,
)
from scenelens.providers.mock import MockProvider
from scenelens.providers.registry import ProviderRegistry


def _context() -> ReviewContext:
    return ReviewContext(
        project_id="p",
        shot_id="s",
        version_id="v",
        creative_intent={},
        reference_visual_brief={},
        global_measurements={},
    )


def _images():
    return (
        ProviderImage("reference", "image/png", b"reference"),
        ProviderImage("current", "image/png", b"current"),
    )


def _lighting_output():
    scheme = {
        "strategy": "faithful_to_reference",
        "key_direction_and_altitude": "mock",
        "key_softness": "mock",
        "key_fill_relationship": "mock",
        "colour_temperature_strategy": "mock",
        "sky_and_indirect_light": "mock",
        "exposure_direction": "mock",
        "fog_and_atmospheric_perspective": "mock",
        "volumetric_light": "mock",
        "focus_emphasis": "mock",
        "depth_separation": "mock",
        "regions_to_darken_or_lift": [],
        "ue53_execution_order": ["mock"],
        "risks": [],
        "validation": ["mock"],
        "annotations": [],
    }
    dramatic = copy.deepcopy(scheme)
    dramatic["strategy"] = "heightened_drama"
    readable = copy.deepcopy(scheme)
    readable["strategy"] = "gameplay_readability"
    dimensions = (
        "exposure_value_range", "key_fill_balance", "focal_hierarchy",
        "depth_separation", "colour_temperature", "shadow_silhouette",
        "atmosphere_volumetrics", "gameplay_readability",
    )
    return {
        "schema_version": "2.0",
        "reviewer_id": "lighting_review",
        "summary": "mock",
        "target_readback": {
            "production_stage": "", "target_mood": "", "primary_focus": "",
            "protected_content": [], "review_exclusions": [],
        },
        "dimension_reviews": [
            {
                "dimension_id": value,
                "status": "insufficient_evidence",
                "intent_target": "",
                "reference_read": "mock",
                "current_read": "mock",
                "evidence_summary": [],
                "strengths": [],
                "risks": [],
                "linked_finding_ids": [],
                "confidence": 0.0,
                "uncertainty": "mock",
            }
            for value in dimensions
        ],
        "lighting_components": [
            {
                "component_id": "shadow",
                "inference_type": "shadow_area",
                "normalized_rect": {
                    "x": 0,
                    "y": 0,
                    "width": 1,
                    "height": 1,
                },
                "image_evidence": "区域较暗",
                "alternative_explanation": "材质可能较暗",
                "confidence": 0.8,
                "narrative_role": "压制信息",
                "ue5_component_candidates": [],
            }
        ],
        "findings": [],
        "preserve_items": [],
        "action_plan": [],
        "target_schemes": [scheme, dramatic, readable],
        "performance_checklist": ["确认 Lumen 配置"],
        "confidence_notes": [],
    }


def test_coordinator_validates_ai_coordinates_with_local_pixels() -> None:
    registry = ProviderRegistry()
    registry.register(MockProvider(output=_lighting_output()))
    coordinator = ReviewCoordinator(
        registry,
        {
            "art_director_review": ArtDirectorReview(),
            "lighting_review": LightingReview(),
        },
    )
    dark = np.full((20, 20, 3), 20, dtype=np.uint8)
    outcome = coordinator.run(
        options=ReviewRunOptions("lighting_review", "mock"),
        context=_context(),
        images=_images(),
        current_rgb=dark,
        reference_rgb=dark,
        credentials={},
        cancellation=CancellationToken(),
    )
    assert outcome.component_validations[0].status.value == "supported"
    restored = review_outcome_from_payload(review_outcome_to_payload(outcome))
    assert restored == outcome
    coordinator.close()


def test_default_mock_generates_schema_valid_art_review_offline() -> None:
    registry = ProviderRegistry()
    registry.register(MockProvider())
    reviewer = ArtDirectorReview()
    coordinator = ReviewCoordinator(
        registry,
        {"art_director_review": reviewer},
    )
    image = np.full((8, 8, 3), 100, dtype=np.uint8)
    outcome = coordinator.run(
        options=ReviewRunOptions("art_director_review", "mock"),
        context=_context(),
        images=_images(),
        current_rgb=image,
        reference_rgb=image,
        credentials={},
        cancellation=CancellationToken(),
    )
    assert outcome.output["reviewer_id"] == "art_director_review"
    assert outcome.output["findings"] == []
    coordinator.close()
