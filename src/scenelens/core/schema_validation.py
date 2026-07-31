from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SchemaIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class SchemaValidationError(ValueError):
    def __init__(self, issues: Sequence[SchemaIssue]) -> None:
        self.issues = tuple(issues)
        detail = "\n".join(str(issue) for issue in self.issues)
        super().__init__(f"结构化结果不符合 Schema：\n{detail}")


def validate_json_schema(
    value: Any,
    schema: Mapping[str, Any],
) -> tuple[SchemaIssue, ...]:
    """Validate the strict JSON Schema subset used by GATalk.

    The supported subset deliberately covers the checked-in review schemas and
    does not pretend to be a general JSON Schema implementation.
    """

    issues: list[SchemaIssue] = []
    _validate(value, schema, "$", issues)
    return tuple(issues)


def require_valid_json_schema(
    value: Any,
    schema: Mapping[str, Any],
) -> None:
    issues = validate_json_schema(value, schema)
    if issues:
        raise SchemaValidationError(issues)


def _validate(
    value: Any,
    schema: Mapping[str, Any],
    path: str,
    issues: list[SchemaIssue],
) -> None:
    if "const" in schema and value != schema["const"]:
        issues.append(
            SchemaIssue(path, f"必须等于 {schema['const']!r}")
        )
        return

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        issues.append(
            SchemaIssue(path, f"必须是以下值之一：{', '.join(map(str, enum))}")
        )
        return

    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        expected_text = (
            "/".join(expected)
            if isinstance(expected, list)
            else str(expected)
        )
        issues.append(
            SchemaIssue(
                path,
                f"类型应为 {expected_text}，实际为 {_json_type(value)}",
            )
        )
        return

    if isinstance(value, Mapping):
        _validate_object(value, schema, path, issues)
    elif isinstance(value, list):
        _validate_array(value, schema, path, issues)
    elif isinstance(value, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if minimum is not None and len(value) < int(minimum):
            issues.append(SchemaIssue(path, f"长度不能少于 {minimum}"))
        if maximum is not None and len(value) > int(maximum):
            issues.append(SchemaIssue(path, f"长度不能超过 {maximum}"))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            issues.append(SchemaIssue(path, f"不能小于 {minimum}"))
        if maximum is not None and value > maximum:
            issues.append(SchemaIssue(path, f"不能大于 {maximum}"))


def _validate_object(
    value: Mapping[str, Any],
    schema: Mapping[str, Any],
    path: str,
    issues: list[SchemaIssue],
) -> None:
    properties = schema.get("properties", {})
    for field in schema.get("required", []):
        if field not in value:
            issues.append(
                SchemaIssue(f"{path}.{field}", "缺少必填字段")
            )
    if schema.get("additionalProperties") is False:
        for field in value:
            if field not in properties:
                issues.append(
                    SchemaIssue(f"{path}.{field}", "不允许未知字段")
                )
    for field, field_value in value.items():
        field_schema = properties.get(field)
        if isinstance(field_schema, Mapping):
            _validate(
                field_value,
                field_schema,
                f"{path}.{field}",
                issues,
            )


def _validate_array(
    value: list[Any],
    schema: Mapping[str, Any],
    path: str,
    issues: list[SchemaIssue],
) -> None:
    minimum = schema.get("minItems")
    maximum = schema.get("maxItems")
    if minimum is not None and len(value) < int(minimum):
        issues.append(SchemaIssue(path, f"项目数不能少于 {minimum}"))
    if maximum is not None and len(value) > int(maximum):
        issues.append(SchemaIssue(path, f"项目数不能超过 {maximum}"))
    item_schema = schema.get("items")
    if isinstance(item_schema, Mapping):
        for index, item in enumerate(value):
            _validate(item, item_schema, f"{path}[{index}]", issues)


def _matches_type(value: Any, expected: str | list[str]) -> bool:
    expected_values = expected if isinstance(expected, list) else [expected]
    return any(_matches_single_type(value, item) for item in expected_values)


def _matches_single_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool)
        )
    return False


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__
