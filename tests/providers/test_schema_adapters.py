import json
from copy import deepcopy

from scenelens.modules.visual_review.reviews import DeepArtDirectorReview
from scenelens.modules.visual_review.reviews.base import load_review_schema
from scenelens.providers.schema_adapters import (
    gemini_compatible_schema,
    gemini_schema_profile,
    gemini_structural_schema,
    schema_output_template,
)


def test_gemini_schema_adapter_removes_unsupported_keywords() -> None:
    source = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "schema_version": {"const": "1.0"},
            "summary": {
                "type": "string",
                "minLength": 1,
                "pattern": ".+",
            },
        },
        "required": ["schema_version", "summary"],
        "additionalProperties": False,
    }
    original = deepcopy(source)

    adapted = gemini_compatible_schema(source)

    assert adapted["properties"]["schema_version"] == {
        "type": "string",
        "enum": ["1.0"],
    }
    assert adapted["properties"]["summary"] == {"type": "string"}
    assert "$schema" not in adapted
    assert source == original


def test_gemini_schema_adapter_preserves_measurement_constraints() -> None:
    adapted = gemini_compatible_schema(
        {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
        }
    )

    assert adapted == {
        "type": "array",
        "minItems": 1,
        "maxItems": 5,
        "items": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
    }


def test_deep_review_schema_uses_structural_gemini_wire_contract() -> None:
    schema = load_review_schema("deep_art_director_review.schema.json")

    profile = gemini_schema_profile(schema)
    structural = gemini_structural_schema(schema)

    assert profile.requires_structural_mode is True
    assert profile.byte_size > 4_096
    assert structural["required"] == schema["required"]
    assert set(structural["properties"]) == set(schema["properties"])
    target = structural["properties"]["target_readback"]
    assert target["required"] == schema["properties"]["target_readback"][
        "required"
    ]
    claims = structural["properties"]["findings"]["items"]["properties"][
        "evidence_claims"
    ]
    assert claims["items"]["type"] == "object"
    assert "enum" not in structural["properties"]["dimension_reviews"][
        "items"
    ]["properties"]["dimension_id"]
    assert len(
        json.dumps(
            structural,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    ) < profile.byte_size
    assert structural["properties"]["schema_version"] == {
        "type": "string",
        "enum": ["2.0"],
    }


def test_deep_review_prompt_template_is_locally_valid() -> None:
    reviewer = DeepArtDirectorReview()

    template = schema_output_template(reviewer.output_schema)
    validated = reviewer.validate_output(template)

    assert len(validated.output["dimension_reviews"]) == 8
    assert validated.output["findings"] == []
    assert set(validated.output["target_readback"]) == {
        "production_stage",
        "target_style",
        "target_mood",
        "primary_focus",
        "protected_content",
        "review_exclusions",
    }


def test_small_schema_keeps_full_gemini_wire_contract() -> None:
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    assert gemini_schema_profile(schema).requires_structural_mode is False
