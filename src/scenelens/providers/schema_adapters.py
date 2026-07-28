from __future__ import annotations

import json
from dataclasses import dataclass
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

_GEMINI_SAFE_SCHEMA_BYTES = 4_096
_GEMINI_SAFE_SCHEMA_DEPTH = 5
_GEMINI_SAFE_PROPERTY_COUNT = 48


@dataclass(frozen=True)
class GeminiSchemaProfile:
    byte_size: int
    max_depth: int
    property_count: int

    @property
    def requires_compact_mode(self) -> bool:
        return (
            self.byte_size > _GEMINI_SAFE_SCHEMA_BYTES
            or self.max_depth > _GEMINI_SAFE_SCHEMA_DEPTH
            or self.property_count > _GEMINI_SAFE_PROPERTY_COUNT
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


def gemini_schema_profile(
    schema: Mapping[str, Any],
) -> GeminiSchemaProfile:
    """Measure the Gemini wire copy of a JSON Schema.

    Gemini supports only a JSON Schema subset and may reject large or deeply
    nested schemas with a generic ``INVALID_ARGUMENT`` response.  The limits
    here are deliberately conservative compatibility thresholds, not claims
    about undocumented service hard limits.
    """

    adapted = gemini_compatible_schema(schema)
    encoded = json.dumps(
        adapted,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    max_depth, property_count = _schema_shape(adapted)
    return GeminiSchemaProfile(
        byte_size=len(encoded),
        max_depth=max_depth,
        property_count=property_count,
    )


def gemini_compact_schema(
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep the top-level contract for Gemini's server-side constraint.

    The complete schema is still sent as prompt text and validated locally.
    This compact copy prevents complex SceneLens review schemas from being
    rejected before inference starts.
    """

    adapted = gemini_compatible_schema(schema)
    result: dict[str, Any] = {"type": adapted.get("type", "object")}
    properties = adapted.get("properties")
    if isinstance(properties, Mapping):
        result["properties"] = {
            str(name): _compact_property(child)
            for name, child in properties.items()
        }
    required = adapted.get("required")
    if isinstance(required, list):
        result["required"] = list(required)
    if adapted.get("additionalProperties") is False:
        result["additionalProperties"] = False
    return result


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


def _compact_property(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    if "type" in value:
        result["type"] = value["type"]
    if "enum" in value:
        result["enum"] = list(value["enum"])
    if not result and "anyOf" in value:
        result["anyOf"] = [
            _compact_property(item) for item in value["anyOf"]
        ]
    return result


def _schema_shape(value: Any, depth: int = 1) -> tuple[int, int]:
    if not isinstance(value, Mapping):
        return depth, 0
    max_depth = depth
    property_count = 0
    properties = value.get("properties")
    if isinstance(properties, Mapping):
        property_count += len(properties)
        for child in properties.values():
            child_depth, child_count = _schema_shape(child, depth + 1)
            max_depth = max(max_depth, child_depth)
            property_count += child_count
    defs = value.get("$defs")
    if isinstance(defs, Mapping):
        for child in defs.values():
            child_depth, child_count = _schema_shape(child, depth + 1)
            max_depth = max(max_depth, child_depth)
            property_count += child_count
    for key in ("items", "additionalProperties"):
        child = value.get(key)
        if isinstance(child, Mapping):
            child_depth, child_count = _schema_shape(child, depth + 1)
            max_depth = max(max_depth, child_depth)
            property_count += child_count
    for key in ("anyOf", "prefixItems"):
        children = value.get(key)
        if not isinstance(children, list):
            continue
        for child in children:
            child_depth, child_count = _schema_shape(child, depth + 1)
            max_depth = max(max_depth, child_depth)
            property_count += child_count
    return max_depth, property_count


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
