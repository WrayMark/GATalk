import pytest

from scenelens.core.schema_validation import (
    SchemaValidationError,
    require_valid_json_schema,
    validate_json_schema,
)


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings", "status"],
    "properties": {
        "status": {"type": "string", "enum": ["pass", "review"]},
        "findings": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["observation", "confidence"],
                "properties": {
                    "observation": {"type": "string", "minLength": 1},
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
            },
        },
    },
}


def test_strict_schema_accepts_valid_value() -> None:
    assert (
        validate_json_schema(
            {
                "status": "review",
                "findings": [
                    {"observation": "焦点区偏暗", "confidence": 0.7}
                ],
            },
            SCHEMA,
        )
        == ()
    )


def test_strict_schema_reports_exact_paths() -> None:
    issues = validate_json_schema(
        {
            "status": "unknown",
            "findings": [
                {
                    "observation": "",
                    "confidence": 1.2,
                    "score": 9,
                }
            ],
            "total_score": 8,
        },
        SCHEMA,
    )
    paths = {issue.path for issue in issues}
    assert "$.status" in paths
    assert "$.findings[0].observation" in paths
    assert "$.findings[0].confidence" in paths
    assert "$.findings[0].score" in paths
    assert "$.total_score" in paths


def test_schema_limits_review_to_five_findings() -> None:
    value = {
        "status": "review",
        "findings": [
            {"observation": str(index), "confidence": 0.5}
            for index in range(6)
        ],
    }
    with pytest.raises(SchemaValidationError, match="项目数不能超过 5"):
        require_valid_json_schema(value, SCHEMA)
