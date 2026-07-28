from copy import deepcopy

from scenelens.providers.schema_adapters import gemini_compatible_schema


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
