from __future__ import annotations

import http.client
import io
import json
import urllib.error

import pytest

from scenelens.providers.contracts import CancellationToken, ProviderError
from scenelens.providers.execution import (
    ProviderExecutionService,
    RetryPolicy,
)
from scenelens.providers.transport import (
    BinaryTransportRequest,
    JsonTransportRequest,
    UrllibBinaryDownloadTransport,
    UrllibBinaryTransport,
    UrllibJsonTransport,
)


def test_http_error_keeps_provider_reason_without_request_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": "Unsupported schema keyword: minLength",
            }
        }
    ).encode()

    def fail(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://example.invalid",
            400,
            "Bad Request",
            {},
            io.BytesIO(body),
        )

    monkeypatch.setattr("urllib.request.urlopen", fail)
    request = JsonTransportRequest(
        url="https://example.invalid",
        headers={"Authorization": "Bearer secret-token"},
        body={"safe": True},
        timeout_seconds=1,
    )

    with pytest.raises(ProviderError) as exc_info:
        UrllibJsonTransport().send(request, CancellationToken())

    error = exc_info.value
    assert error.code == "http_400"
    assert "请求参数" in error.public_message
    assert "INVALID_ARGUMENT" in error.technical_detail
    assert "minLength" in error.technical_detail
    assert "secret-token" not in error.technical_detail


def test_provider_error_user_message_includes_redacted_diagnostic() -> None:
    error = ProviderError(
        "AI 服务拒绝了请求参数。",
        code="http_400",
        technical_detail="HTTP 400 | api_key=secret-value",
    )

    class FailingProvider:
        def review(self, request, credential, cancellation):
            del request, cancellation
            error.technical_detail += f" | echoed={credential}"
            raise error

    service = ProviderExecutionService(sleep=lambda _delay: None)
    try:
        with pytest.raises(ProviderError) as exc_info:
            service.run_review(
                FailingProvider(),
                object(),
                "secret-value",
                CancellationToken(),
                RetryPolicy(max_attempts=1),
            )
    finally:
        service.close()

    message = exc_info.value.to_user_message()
    assert "错误代码：http_400" in message
    assert "secret-value" not in message
    assert "[REDACTED]" in message


@pytest.mark.parametrize(
    ("transport", "wire_request"),
    [
        (
            UrllibJsonTransport(),
            JsonTransportRequest(
                url="https://example.invalid",
                headers={"Content-Type": "application/json"},
                body={"safe": True},
                timeout_seconds=1,
            ),
        ),
        (
            UrllibBinaryTransport(),
            BinaryTransportRequest(
                url="https://example.invalid",
                headers={"Content-Type": "application/json"},
                body=b'{"safe":true}',
                timeout_seconds=1,
            ),
        ),
    ],
)
def test_remote_disconnect_becomes_retryable_provider_error(
    monkeypatch: pytest.MonkeyPatch,
    transport,
    wire_request,
) -> None:
    def fail(*_args, **_kwargs):
        raise http.client.RemoteDisconnected(
            "Remote end closed connection without response"
        )

    monkeypatch.setattr("urllib.request.urlopen", fail)

    with pytest.raises(ProviderError) as exc_info:
        transport.send(wire_request, CancellationToken())

    error = exc_info.value
    assert error.code == "connection_closed"
    assert error.retryable is True
    assert "自动重试" in error.public_message
    assert "RemoteDisconnected" in error.technical_detail
    assert "Remote end closed" not in error.to_user_message()


def test_remote_disconnect_during_image_download_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args, **_kwargs):
        raise http.client.RemoteDisconnected(
            "Remote end closed connection without response"
        )

    monkeypatch.setattr("urllib.request.urlopen", fail)

    with pytest.raises(ProviderError) as exc_info:
        UrllibBinaryDownloadTransport().download(
            "https://example.invalid/output.png",
            CancellationToken(),
            timeout_seconds=1,
            max_bytes=1024,
        )

    error = exc_info.value
    assert error.code == "output_connection_closed"
    assert error.retryable is True
    assert "自动重试" in error.public_message
