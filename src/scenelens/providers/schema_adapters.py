from __future__ import annotations

from typing import Any, Mapping


_GEMINI_SUPPORTED_KEYS = frozenset(
    {
        "$defs",
        "$ref",
        "additionalProperties",
        "anyOf",
        "description",
        "enum",
        "format",
        "items",
        "maximum",
        "maxItems",
        "minimum",
        "minItems",
        "prefixItems",
        "properties",
        "required",
        "title",
        "type",
    }
)


def gemini_compatible_schema(
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Return Gemini's supported JSON Schema subset.

    The local validator continues to use the complete source schema. This
    adapter only narrows the copy sent to Gemini, and maps ``const`` to a
    single-value ``enum`` so fixed SceneLens identifiers remain constrained.
    """

    return _adapt_mapping(dict(schema))


def _adapt_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    const_value = value.get("const", _MISSING)
    for key, item in value.items():
        if key not in _GEMINI_SUPPORTED_KEYS:
            continue
        if key in {"properties", "$defs"} and isinstance(item, Mapping):
            result[key] = {
                str(name): _adapt_schema(child)
                for name, child in item.items()
            }
        elif key in {"items", "additionalProperties"}:
            result[key] = _adapt_schema(item)
        elif key in {"anyOf", "prefixItems"} and isinstance(item, list):
            result[key] = [_adapt_schema(child) for child in item]
        else:
            result[key] = item
    if const_value is not _MISSING:
        result["enum"] = [const_value]
        result.setdefault("type", _json_type(const_value))
    return result


def _adapt_schema(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _adapt_mapping(value)
    if isinstance(value, list):
        return [_adapt_schema(item) for item in value]
    return value


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    if isinstance(value, list):
        return "array"
    return "object"


_MISSING = object()
