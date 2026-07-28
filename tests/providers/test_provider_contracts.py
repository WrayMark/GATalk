from __future__ import annotations

import json
from dataclasses import dataclass

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


def test_gemini_deep_review_uses_compact_wire_schema_and_prompt_contract():
    schema = load_review_schema("deep_art_director_review.schema.json")
    provider = GeminiVisionProvider(_manifest("google_gemini"))

    wire = provider.build_request(
        _request(output_schema=schema),
        "secret",
    )
    text_format = wire.body["generationConfig"]["responseFormat"]["text"]
    prompt_parts = wire.body["contents"][0]["parts"]

    assert text_format["schema"]["required"] == schema["required"]
    assert text_format["schema"]["properties"]["dimension_reviews"] == {
        "type": "array"
    }
    assert any(
        "SCENELENS_OUTPUT_JSON_SCHEMA=" in part.get("text", "")
        for part in prompt_parts
    )


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
