from __future__ import annotations

import copy
import json

import pytest

from scenelens.modules.visual_review.reviews.base import load_review_schema
from scenelens.providers.adapters import (
    GeminiVisionProvider,
    OpenAICompatibleChatProvider,
    ResponsesVisionProvider,
)
from scenelens.providers.contracts import (
    CancellationToken,
    ProviderCapability,
    ProviderError,
    ProviderImage,
    VisionReviewRequest,
    disclosure_preview,
)
from scenelens.providers.factory import create_default_provider_registry
from scenelens.providers.manifests import load_provider_manifests
from scenelens.providers.mock import _default_mock_output
from scenelens.providers.schema_adapters import schema_output_template
from scenelens.providers.transport import RecordingJsonTransport


SCHEMA = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": {}}},
    "required": ["findings"],
    "additionalProperties": False,
}


def _request(
    confirmed: bool = True,
    max_output_tokens: int | None = None,
    output_schema=None,
) -> VisionReviewRequest:
    return VisionReviewRequest(
        system_instruction="Return evidence-grounded JSON.",
        payload={"creative_intent": {"stage": "灯光初版"}},
        images=(
            ProviderImage(
                role="current",
                media_type="image/png",
                data=b"fake-png",
            ),
        ),
        output_schema=output_schema or SCHEMA,
        user_initiated=True,
        disclosure_confirmed=confirmed,
        max_output_tokens=max_output_tokens,
    )


def _manifest(provider_id: str):
    return next(
        item
        for item in load_provider_manifests()
        if item.provider_id == provider_id
    )


@pytest.mark.parametrize("provider_id", ["aliyun_bailian", "siliconflow"])
def test_openai_chat_provider_contract_is_offline_and_configurable(provider_id):
    transport = RecordingJsonTransport(
        [
            {
                "id": "chat-request",
                "model": "returned-model",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"findings": []})
                        }
                    }
                ],
                "usage": {"total_tokens": 10},
            }
        ]
    )
    provider = OpenAICompatibleChatProvider(
        _manifest(provider_id),
        transport,
    )

    response = provider.review(
        _request(),
        "test-secret",
        CancellationToken(),
    )

    assert response.output == {"findings": []}
    assert len(transport.requests) == 1
    wire = transport.requests[0]
    assert wire.url.endswith("/chat/completions")
    assert wire.headers["Authorization"] == "Bearer test-secret"
    assert wire.body["model"] == provider.manifest.default_models[
        "vision_review"
    ]
    assert wire.body["messages"][1]["content"][0]["text"] == (
        "IMAGE_ROLE=current"
    )
    assert wire.body["messages"][1]["content"][1]["image_url"][
        "url"
    ].startswith("data:image/png;base64,")
    assert wire.body["response_format"] == {"type": "json_object"}
    assert "JSON" in wire.body["messages"][0]["content"]
    assert "SCENELENS_OUTPUT_JSON_SCHEMA=" in wire.body["messages"][1][
        "content"
    ][-1]["text"]


@pytest.mark.parametrize("provider_id", ["openai", "xai_grok"])
def test_responses_provider_contract_uses_strict_schema(provider_id):
    transport = RecordingJsonTransport(
        [
            {
                "id": "response-request",
                "model": "returned-model",
                "output_text": json.dumps({"findings": []}),
                "usage": {"total_tokens": 12},
            }
        ]
    )
    provider = ResponsesVisionProvider(_manifest(provider_id), transport)

    response = provider.review(
        _request(),
        "test-secret",
        CancellationToken(),
    )

    assert response.output == {"findings": []}
    wire = transport.requests[0]
    assert wire.url.endswith("/responses")
    assert wire.body["store"] is False
    assert wire.body["text"]["format"]["schema"] == SCHEMA
    assert wire.body["text"]["format"]["strict"] is True


def test_gemini_provider_contract_uses_inline_image_and_json_schema():
    transport = RecordingJsonTransport(
        [
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps({"findings": []})}
                            ]
                        }
                    }
                ],
                "usageMetadata": {"totalTokenCount": 8},
            }
        ]
    )
    provider = GeminiVisionProvider(_manifest("google_gemini"), transport)

    response = provider.review(
        _request(),
        "test-secret",
        CancellationToken(),
    )

    assert response.output == {"findings": []}
    wire = transport.requests[0]
    assert ":generateContent" in wire.url
    assert wire.headers["x-goog-api-key"] == "test-secret"
    assert wire.body["contents"][0]["parts"][0]["text"] == (
        "IMAGE_ROLE=current"
    )
    assert wire.body["contents"][0]["parts"][1]["inlineData"][
        "mimeType"
    ] == "image/png"
    assert wire.body["generationConfig"]["responseFormat"]["text"][
        "schema"
    ] == SCHEMA
    assert wire.body["generationConfig"]["responseFormat"]["text"][
        "mimeType"
    ] == "APPLICATION_JSON"
    assert "temperature" not in wire.body["generationConfig"]


def test_rich_review_output_budget_maps_to_each_provider_wire_format():
    chat = OpenAICompatibleChatProvider(_manifest("aliyun_bailian"))
    responses = ResponsesVisionProvider(_manifest("openai"))
    gemini = GeminiVisionProvider(_manifest("google_gemini"))
    request = _request(max_output_tokens=12000)

    assert chat.build_request(request, "secret").body["max_tokens"] == 12000
    assert (
        responses.build_request(request, "secret").body["max_output_tokens"]
        == 12000
    )
    assert (
        gemini.build_request(request, "secret")
        .body["generationConfig"]["maxOutputTokens"]
        == 12000
    )


def test_gemini_deep_review_uses_structural_wire_schema_and_prompt_contract():
    schema = load_review_schema("deep_art_director_review.schema.json")
    provider = GeminiVisionProvider(_manifest("google_gemini"))

    wire = provider.build_request(
        _request(output_schema=schema),
        "secret",
    )
    text_format = wire.body["generationConfig"]["responseFormat"]["text"]
    prompt_parts = wire.body["contents"][0]["parts"]

    assert text_format["schema"]["required"] == schema["required"]
    claims = text_format["schema"]["properties"]["findings"]["items"][
        "properties"
    ]["evidence_claims"]
    assert claims["items"]["type"] == "object"
    target = text_format["schema"]["properties"]["target_readback"]
    assert "production_stage" in target["required"]
    assert any(
        "SCENELENS_OUTPUT_JSON_SCHEMA=" in part.get("text", "")
        for part in prompt_parts
    )
    assert any(
        "SCENELENS_OUTPUT_JSON_TEMPLATE=" in part.get("text", "")
        for part in prompt_parts
    )


def test_gemini_repairs_missing_fields_and_string_evidence_claims_once():
    schema = load_review_schema("deep_art_director_review.schema.json")
    valid = _default_mock_output(schema)
    finding = schema_output_template(
        schema["properties"]["findings"]["items"]
    )
    finding["finding_id"] = "finding-1"
    finding["dimension_ids"] = ["composition"]
    valid["findings"] = [finding]
    invalid = copy.deepcopy(valid)
    for field in (
        "production_stage",
        "target_style",
        "target_mood",
        "primary_focus",
        "protected_content",
        "review_exclusions",
    ):
        invalid["target_readback"].pop(field)
    invalid["findings"][0]["evidence_claims"] = [
        f"第 {index + 1} 条证据只有文字，没有完整矩形、指标和阈值。"
        for index in range(8)
    ]
    transport = RecordingJsonTransport(
        [
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(invalid)}]
                        }
                    }
                ],
                "usageMetadata": {"totalTokenCount": 100},
            },
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(valid)}]
                        }
                    }
                ],
                "usageMetadata": {"totalTokenCount": 30},
            },
        ]
    )
    provider = GeminiVisionProvider(
        _manifest("google_gemini"),
        transport,
    )

    response = provider.review(
        _request(output_schema=schema),
        "test-secret",
        CancellationToken(),
    )

    assert response.output == valid
    assert response.usage["schemaRepairAttempted"] is True
    assert response.usage["schemaRepairReason"] == "schema_validation"
    assert len(transport.requests) == 2
    repair_parts = transport.requests[1].body["contents"][0]["parts"]
    assert any(
        '"schema_issues"' in part.get("text", "")
        and "evidence_claims" in part.get("text", "")
        for part in repair_parts
    )


def test_gemini_repairs_invalid_json_from_exact_report_location_once():
    invalid_json = "\n".join(
        [
            "{",
            '  "findings": [',
            *([""] * 458),
            "                invalid",
            "  ]",
            "}",
        ]
    )
    transport = RecordingJsonTransport(
        [
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": invalid_json}]},
                        "finishReason": "MAX_TOKENS",
                    }
                ],
                "usageMetadata": {"totalTokenCount": 12000},
            },
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {"findings": []}
                                    )
                                }
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"totalTokenCount": 100},
            },
        ]
    )
    provider = GeminiVisionProvider(
        _manifest("google_gemini"),
        transport,
    )

    response = provider.review(
        _request(),
        "test-secret",
        CancellationToken(),
    )

    assert response.output == {"findings": []}
    assert response.usage["schemaRepairAttempted"] is True
    assert response.usage["schemaRepairReason"] == "json_syntax"
    assert len(transport.requests) == 2
    repair_payload = next(
        part["text"]
        for part in transport.requests[1].body["contents"][0]["parts"]
        if "invalid_output" in part.get("text", "")
    )
    assert "line=461,column=17" in repair_payload
    assert "MAX_TOKENS" in repair_payload
    assert "invalid_output" in repair_payload


def test_gemini_joins_multiple_text_parts_before_parsing():
    transport = RecordingJsonTransport(
        [
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": '{"findings":'},
                                {"text": "[]}"},
                            ]
                        }
                    }
                ]
            }
        ]
    )
    provider = GeminiVisionProvider(
        _manifest("google_gemini"),
        transport,
    )

    response = provider.review(
        _request(),
        "test-secret",
        CancellationToken(),
    )

    assert response.output == {"findings": []}
    assert len(transport.requests) == 1


def test_gemini_stops_after_one_failed_json_syntax_repair():
    invalid_body = {
        "candidates": [
            {
                "content": {"parts": [{"text": '{"findings": ['}]},
                "finishReason": "MAX_TOKENS",
            }
        ]
    }
    transport = RecordingJsonTransport([invalid_body, invalid_body])
    provider = GeminiVisionProvider(
        _manifest("google_gemini"),
        transport,
    )

    with pytest.raises(ProviderError) as exc_info:
        provider.review(
            _request(),
            "test-secret",
            CancellationToken(),
        )

    assert exc_info.value.code == "invalid_structured_output_after_repair"
    assert "line=1" in exc_info.value.technical_detail
    assert "finish_reason=MAX_TOKENS" in exc_info.value.technical_detail
    assert len(transport.requests) == 2


def test_gemini_stops_after_one_failed_structure_repair():
    schema = load_review_schema("deep_art_director_review.schema.json")
    invalid = {"schema_version": "2.0"}
    response_body = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(invalid)}]
                }
            }
        ]
    }
    transport = RecordingJsonTransport([response_body, response_body])
    provider = GeminiVisionProvider(
        _manifest("google_gemini"),
        transport,
    )

    with pytest.raises(ProviderError) as exc_info:
        provider.review(
            _request(output_schema=schema),
            "test-secret",
            CancellationToken(),
        )

    assert exc_info.value.code == "invalid_structured_output_after_repair"
    assert len(transport.requests) == 2


def test_gemini_retries_schema_rejection_once_in_prompt_only_mode():
    class RejectSchemaOnceTransport:
        def __init__(self):
            self.requests = []

        def send(self, request, cancellation):
            cancellation.raise_if_cancelled()
            self.requests.append(request)
            if len(self.requests) == 1:
                raise ProviderError(
                    "AI 服务拒绝了请求参数。",
                    code="http_400",
                    technical_detail=(
                        "HTTP 400 | status=INVALID_ARGUMENT | "
                        "message=GenerateContent contains an invalid argument."
                    ),
                )
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps({"findings": []})}
                            ]
                        }
                    }
                ]
            }

    transport = RejectSchemaOnceTransport()
    provider = GeminiVisionProvider(
        _manifest("google_gemini"),
        transport,
    )

    response = provider.review(
        _request(),
        "test-secret",
        CancellationToken(),
    )

    assert response.output == {"findings": []}
    assert len(transport.requests) == 2
    fallback_format = transport.requests[1].body["generationConfig"][
        "responseFormat"
    ]["text"]
    assert fallback_format == {"mimeType": "APPLICATION_JSON"}
    assert any(
        "SCENELENS_OUTPUT_JSON_SCHEMA=" in part.get("text", "")
        for part in transport.requests[1].body["contents"][0]["parts"]
    )


def test_provider_request_requires_user_disclosure_confirmation():
    provider = OpenAICompatibleChatProvider(
        _manifest("aliyun_bailian"),
        RecordingJsonTransport([]),
    )

    with pytest.raises(ProviderError) as exc_info:
        provider.build_request(_request(confirmed=False), "secret")

    assert exc_info.value.code == "disclosure_not_confirmed"


def test_disclosure_preview_has_hash_and_size_but_no_image_bytes():
    request = _request()
    preview = disclosure_preview(_manifest("openai"), request)

    assert preview.payload_fields == ("creative_intent",)
    assert preview.images[0].byte_size == len(b"fake-png")
    assert len(preview.images[0].sha256) == 64
    assert not hasattr(preview.images[0], "data")


def test_default_registry_creation_is_offline_and_lists_image_edit_slots():
    registry = create_default_provider_registry()

    vision_ids = [
        item.manifest.provider_id
        for item in registry.for_capability(
            ProviderCapability.VISION_REVIEW
        )
    ]
    edit_ids = {
        item.manifest.provider_id
        for item in registry.for_capability(ProviderCapability.IMAGE_EDIT)
    }

    assert vision_ids[:3] == ["mock", "aliyun_bailian", "siliconflow"]
    assert {
        "mock",
        "aliyun_wanxiang",
        "google_gemini_image",
        "openai_image",
        "xai_imagine",
    } <= edit_ids
