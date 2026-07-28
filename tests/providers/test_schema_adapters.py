from copy import deepcopy

from scenelens.modules.visual_review.reviews.base import load_review_schema
from scenelens.providers.schema_adapters import (
    gemini_compact_schema,
    gemini_compatible_schema,
    gemini_schema_profile,
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


def test_deep_review_schema_uses_compact_gemini_wire_contract() -> None:
    schema = load_review_schema("deep_art_director_review.schema.json")

    profile = gemini_schema_profile(schema)
    compact = gemini_compact_schema(schema)

    assert profile.requires_compact_mode is True
    assert profile.byte_size > 4_096
    assert compact["required"] == schema["required"]
    assert set(compact["properties"]) == set(schema["properties"])
    assert compact["properties"]["dimension_reviews"] == {
        "type": "array"
    }
    assert compact["properties"]["schema_version"] == {
        "type": "string",
        "enum": ["2.0"],
    }


def test_small_schema_keeps_full_gemini_wire_contract() -> None:
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    assert gemini_schema_profile(schema).requires_compact_mode is False
