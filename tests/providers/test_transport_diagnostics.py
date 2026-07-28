from __future__ import annotations

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
    JsonTransportRequest,
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
