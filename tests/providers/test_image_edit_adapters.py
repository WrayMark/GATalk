import base64

import pytest

from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditRequest,
    ProviderError,
)
from scenelens.providers.factory import create_default_provider_registry
from scenelens.providers.image_adapters import (
    DashScopeImageEditProvider,
    GeminiImageEditProvider,
    MultipartImageEditProvider,
    XAIImageEditProvider,
)
from scenelens.providers.manifests import load_provider_manifests
from scenelens.providers.transport import (
    DownloadedBinary,
    RecordingBinaryTransport,
    RecordingBinaryDownloadTransport,
    RecordingJsonTransport,
)
from scenelens.providers.contracts import ProviderImage


PNG = b"\x89PNG\r\n\x1a\nmock"


def _manifest(provider_id: str):
    return next(
        item
        for item in load_provider_manifests()
        if item.provider_id == provider_id
    )


def _request() -> ImageEditRequest:
    return ImageEditRequest(
        instruction={
            "output_type": "AIConceptPreview",
            "edit_mode": "lighting_only",
        },
        images=(
            ProviderImage("current", "image/png", PNG),
            ProviderImage("reference", "image/png", PNG),
        ),
        change_budget=25,
        user_initiated=True,
        disclosure_confirmed=True,
    )


def test_gemini_image_adapter_is_offline_contract_test() -> None:
    transport = RecordingJsonTransport(
        [
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(PNG).decode(),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    )
    provider = GeminiImageEditProvider(
        _manifest("google_gemini_image"),
        transport,
    )
    result = provider.edit_image(
        _request(),
        "secret",
        CancellationToken(),
    )
    assert result.image_bytes == PNG
    assert ":generateContent" in transport.requests[0].url
    assert transport.requests[0].headers["x-goog-api-key"] == "secret"
    parts = transport.requests[0].body["contents"][0]["parts"]
    assert parts[0] == {"text": "IMAGE_ROLE=current"}
    assert parts[2] == {"text": "IMAGE_ROLE=reference"}


def test_gemini_current_nano_banana_models_and_resolution_contract() -> None:
    provider = GeminiImageEditProvider(
        _manifest("google_gemini_image"),
        RecordingJsonTransport([]),
    )
    request = ImageEditRequest(
        instruction={
            "output_type": "AssetConceptArtifact",
            "output_resolution": "2K",
        },
        images=(ProviderImage("current", "image/png", PNG),),
        model_id="gemini-3-pro-image",
        user_initiated=True,
        disclosure_confirmed=True,
    )
    wire = provider.build_request(request, "secret")
    assert "/models/gemini-3-pro-image:generateContent" in wire.url
    assert wire.body["generationConfig"]["responseFormat"] == {
        "image": {"imageSize": "2K"}
    }

    lite = ImageEditRequest(
        instruction={"output_resolution": "2K"},
        images=request.images,
        model_id="gemini-3.1-flash-lite-image",
        user_initiated=True,
        disclosure_confirmed=True,
    )
    with pytest.raises(ProviderError) as error:
        provider.build_request(lite, "secret")
    assert error.value.code == "unsupported_image_resolution"


def test_gemini_missing_image_reports_finish_reason() -> None:
    provider = GeminiImageEditProvider(
        _manifest("google_gemini_image"),
        RecordingJsonTransport(
            [
                {
                    "candidates": [
                        {
                            "finishReason": "SAFETY",
                            "finishMessage": "blocked",
                        }
                    ]
                }
            ]
        ),
    )
    with pytest.raises(ProviderError) as error:
        provider.edit_image(_request(), "secret", CancellationToken())
    assert error.value.code == "missing_image_output"
    assert "finish_reason=SAFETY" in error.value.technical_detail


def test_dashscope_image_adapter_builds_structured_request() -> None:
    transport = RecordingJsonTransport(
        [
            {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {
                                        "image": (
                                            "https://example.invalid/"
                                            "wan-output.png"
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        ]
    )
    provider = DashScopeImageEditProvider(
        _manifest("aliyun_wanxiang"),
        transport,
        RecordingBinaryDownloadTransport(
            [DownloadedBinary(PNG, "image/png")]
        ),
    )
    result = provider.edit_image(
        _request(),
        "secret",
        CancellationToken(),
    )
    assert result.image_bytes == PNG
    wire = transport.requests[0]
    assert wire.body["input"]["messages"][0]["content"][-1]["text"].startswith(
        "{"
    )


def test_openai_multipart_image_adapter_keeps_structured_prompt() -> None:
    transport = RecordingBinaryTransport(
        [
            {
                "data": [
                    {"b64_json": base64.b64encode(PNG).decode()}
                ]
            }
        ]
    )
    provider = MultipartImageEditProvider(
        _manifest("openai_image"),
        transport,
    )
    result = provider.edit_image(
        _request(),
        "secret",
        CancellationToken(),
    )
    assert result.image_bytes == PNG
    wire = transport.requests[0]
    assert wire.url.endswith("/images/edits")
    assert b"AIConceptPreview" in wire.body
    assert b"secret" not in wire.body


def test_xai_image_adapter_uses_json_and_downloads_output() -> None:
    transport = RecordingJsonTransport(
        [
            {
                "data": [
                    {
                        "url": "https://example.invalid/grok-output.jpeg",
                        "mime_type": "image/jpeg",
                    }
                ],
                "usage": {"cost_in_usd_ticks": 10},
            }
        ]
    )
    downloads = RecordingBinaryDownloadTransport(
        [DownloadedBinary(PNG, "image/jpeg")]
    )
    provider = XAIImageEditProvider(
        _manifest("xai_imagine"),
        transport,
        downloads,
    )

    result = provider.edit_image(
        _request(),
        "secret",
        CancellationToken(),
    )

    assert result.image_bytes == PNG
    wire = transport.requests[0]
    assert wire.url.endswith("/images/edits")
    assert wire.headers["Content-Type"] == "application/json"
    assert len(wire.body["images"]) == 2
    assert wire.body["images"][0]["url"].startswith(
        "data:image/png;base64,"
    )
    assert downloads.urls == [
        "https://example.invalid/grok-output.jpeg"
    ]


def test_default_registry_uses_real_m3_adapter_classes() -> None:
    registry = create_default_provider_registry()
    assert isinstance(
        registry.get("aliyun_wanxiang"),
        DashScopeImageEditProvider,
    )
    assert isinstance(
        registry.get("google_gemini_image"),
        GeminiImageEditProvider,
    )
    assert isinstance(
        registry.get("openai_image"),
        MultipartImageEditProvider,
    )
    assert isinstance(
        registry.get("xai_imagine"),
        XAIImageEditProvider,
    )
