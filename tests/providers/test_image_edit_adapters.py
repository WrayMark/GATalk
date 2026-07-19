import base64

import pytest

from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditRequest,
)
from scenelens.providers.factory import create_default_provider_registry
from scenelens.providers.image_adapters import (
    DashScopeImageEditProvider,
    GeminiImageEditProvider,
    MultipartImageEditProvider,
)
from scenelens.providers.manifests import load_provider_manifests
from scenelens.providers.transport import (
    RecordingBinaryTransport,
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
                                        "b64_json": base64.b64encode(
                                            PNG
                                        ).decode()
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


@pytest.mark.parametrize("provider_id", ["openai_image", "xai_imagine"])
def test_multipart_image_adapters_keep_structured_prompt(provider_id) -> None:
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
        _manifest(provider_id),
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
