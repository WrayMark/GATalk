from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from scenelens.providers.contracts import (
    CancellationToken,
    ProviderCapability,
    ProviderError,
    ProviderManifest,
    ProviderResponse,
    VisionReviewRequest,
)
from scenelens.providers.credentials import (
    MemoryCredentialStore,
    WindowsCredentialStore,
)
from scenelens.providers.execution import (
    ProviderExecutionService,
    RetryPolicy,
    redact_sensitive_text,
)


def _request() -> VisionReviewRequest:
    return VisionReviewRequest(
        system_instruction="test",
        payload={},
        images=(),
        output_schema={"type": "object"},
        user_initiated=True,
        disclosure_confirmed=True,
    )


@dataclass
class FlakyProvider:
    failures: int

    def __post_init__(self):
        self.calls = 0
        self.manifest = ProviderManifest(
            provider_id="flaky",
            display_name="Flaky",
            api_style="test",
            base_url="",
            capabilities=(ProviderCapability.VISION_REVIEW,),
            default_models={"vision_review": "test"},
            credential_target="SceneLens/provider/flaky",
        )

    def review(self, request, credential, cancellation):
        del request
        self.calls += 1
        cancellation.raise_if_cancelled()
        if self.calls <= self.failures:
            raise ProviderError(
                "temporary",
                code="temporary",
                retryable=True,
                technical_detail=f"Authorization: Bearer {credential}",
            )
        return ProviderResponse("flaky", "test", {"ok": True})


def test_memory_credential_store_never_exposes_values_by_listing():
    store = MemoryCredentialStore()
    store.set("SceneLens/provider/test", "secret-value")

    assert store.get("SceneLens/provider/test") == "secret-value"
    assert not hasattr(store, "list")
    store.delete("SceneLens/provider/test")
    assert store.get("SceneLens/provider/test") is None


def test_windows_credential_target_is_namespaced():
    store = WindowsCredentialStore(prefix="SceneLens-Test")

    assert store.target_name("provider/openai") == (
        "SceneLens-Test/provider/openai"
    )


def test_execution_retries_retryable_errors_without_real_sleep():
    delays = []
    service = ProviderExecutionService(sleep=delays.append)
    provider = FlakyProvider(failures=2)

    response = service.run_review(
        provider,
        _request(),
        "sk-never-log-this",
        CancellationToken(),
        RetryPolicy(max_attempts=3, initial_backoff_seconds=0.1),
    )

    assert response.output == {"ok": True}
    assert provider.calls == 3
    assert delays == [0.1, 0.2]
    service.close()


def test_retry_exhaustion_reports_attempt_count():
    service = ProviderExecutionService(sleep=lambda _delay: None)
    provider = FlakyProvider(failures=3)

    try:
        with pytest.raises(ProviderError) as exc_info:
            service.run_review(
                provider,
                _request(),
                "secret",
                CancellationToken(),
                RetryPolicy(max_attempts=3, initial_backoff_seconds=0),
            )
    finally:
        service.close()

    assert provider.calls == 3
    assert "retry_attempts=3" in exc_info.value.technical_detail


def test_review_falls_back_once_after_primary_http_503():
    service = ProviderExecutionService(sleep=lambda _delay: None)

    @dataclass
    class CapacityProvider:
        manifest: ProviderManifest

        def __post_init__(self):
            self.models = []

        def review(self, request, _credential, _cancellation):
            self.models.append(request.model_id)
            if request.model_id == "primary-model":
                raise ProviderError(
                    "temporarily unavailable",
                    code="http_503",
                    retryable=True,
                )
            return ProviderResponse(
                "capacity",
                request.model_id,
                {"ok": True},
            )

    provider = CapacityProvider(
        replace(
            FlakyProvider(0).manifest,
            provider_id="capacity",
            default_models={"vision_review": "primary-model"},
        )
    )
    try:
        result = service.run_review_with_model_fallback(
            provider,
            _request(),
            "secret",
            CancellationToken(),
            ("fallback-model",),
            RetryPolicy(max_attempts=3, initial_backoff_seconds=0),
        )
    finally:
        service.close()

    assert provider.models == [
        "primary-model",
        "primary-model",
        "primary-model",
        "fallback-model",
    ]
    assert result.response.model_id == "fallback-model"
    assert result.requested_model_id == "primary-model"
    assert result.attempted_model_ids == (
        "primary-model",
        "fallback-model",
    )
    assert result.fallback_used is True
    assert result.fallback_reason == "http_503"


def test_review_does_not_fall_back_for_non_capacity_error():
    service = ProviderExecutionService(sleep=lambda _delay: None)

    @dataclass
    class InvalidRequestProvider:
        manifest: ProviderManifest

        def review(self, _request, _credential, _cancellation):
            raise ProviderError(
                "invalid request",
                code="http_400",
                retryable=False,
            )

    provider = InvalidRequestProvider(
        replace(
            FlakyProvider(0).manifest,
            provider_id="invalid",
            default_models={"vision_review": "primary-model"},
        )
    )
    try:
        with pytest.raises(ProviderError) as exc_info:
            service.run_review_with_model_fallback(
                provider,
                _request(),
                "secret",
                CancellationToken(),
                ("fallback-model",),
            )
    finally:
        service.close()

    assert exc_info.value.code == "http_400"


@pytest.mark.parametrize("primary_error_code", ["http_404", "http_503"])
def test_review_skips_unavailable_models_in_fallback_chain(
    primary_error_code,
):
    service = ProviderExecutionService(sleep=lambda _delay: None)

    @dataclass
    class RoutedProvider:
        manifest: ProviderManifest

        def __post_init__(self):
            self.models = []

        def review(self, request, _credential, _cancellation):
            self.models.append(request.model_id)
            if request.model_id == "primary-model":
                raise ProviderError(
                    "primary unavailable",
                    code=primary_error_code,
                    retryable=primary_error_code == "http_503",
                )
            if request.model_id == "retired-fallback":
                raise ProviderError(
                    "model retired",
                    code="http_404",
                    retryable=False,
                )
            return ProviderResponse(
                "routed",
                request.model_id,
                {"ok": True},
            )

    provider = RoutedProvider(
        replace(
            FlakyProvider(0).manifest,
            provider_id="routed",
            default_models={"vision_review": "primary-model"},
        )
    )
    try:
        result = service.run_review_with_model_fallback(
            provider,
            _request(),
            "secret",
            CancellationToken(),
            ("retired-fallback", "working-fallback"),
            RetryPolicy(max_attempts=1, initial_backoff_seconds=0),
        )
    finally:
        service.close()

    assert provider.models == [
        "primary-model",
        "retired-fallback",
        "working-fallback",
    ]
    assert result.response.model_id == "working-fallback"
    assert result.attempted_model_ids == (
        "primary-model",
        "retired-fallback",
        "working-fallback",
    )
    assert result.fallback_reason == primary_error_code


def test_review_reports_complete_route_when_all_models_are_unavailable():
    service = ProviderExecutionService(sleep=lambda _delay: None)

    @dataclass
    class UnavailableProvider:
        manifest: ProviderManifest

        def review(self, request, _credential, _cancellation):
            raise ProviderError(
                "model unavailable",
                code="http_404",
                retryable=False,
                technical_detail=f"model={request.model_id}",
            )

    provider = UnavailableProvider(
        replace(
            FlakyProvider(0).manifest,
            provider_id="unavailable",
            default_models={"vision_review": "primary-model"},
        )
    )
    try:
        with pytest.raises(ProviderError) as exc_info:
            service.run_review_with_model_fallback(
                provider,
                _request(),
                "secret",
                CancellationToken(),
                ("fallback-a", "fallback-b"),
                RetryPolicy(max_attempts=1),
            )
    finally:
        service.close()

    assert exc_info.value.code == "http_404"
    assert "已配置的备用模型均不可用" in exc_info.value.public_message
    assert (
        "model_attempts=primary-model->fallback-a->fallback-b"
        in exc_info.value.technical_detail
    )
    assert "fallback-a:http_404" in exc_info.value.technical_detail
    assert "fallback-b:http_404" in exc_info.value.technical_detail


def test_manifest_fallback_models_are_configured_and_deduplicated():
    manifest = ProviderManifest(
        provider_id="test",
        display_name="Test",
        api_style="test",
        base_url="",
        capabilities=(ProviderCapability.VISION_REVIEW,),
        default_models={"vision_review": "primary"},
        credential_target="SceneLens/provider/test",
        options={
            "fallback_models": {
                "vision_review": [
                    "primary",
                    "fallback",
                    "fallback",
                ]
            }
        },
    )

    assert manifest.fallback_models_for(
        ProviderCapability.VISION_REVIEW
    ) == ("fallback",)


def test_execution_cancellation_stops_before_provider_call():
    service = ProviderExecutionService(sleep=lambda _delay: None)
    provider = FlakyProvider(failures=0)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(ProviderError) as exc_info:
        service.run_review(provider, _request(), "secret", token)

    assert exc_info.value.code == "cancelled"
    assert provider.calls == 0
    service.close()


def test_error_redaction_removes_common_secret_shapes():
    redacted = redact_sensitive_text(
        "Authorization: Bearer abc.def api_key=hello sk-abcdefghijk",
        "abc.def",
    )

    assert "abc.def" not in redacted
    assert "hello" not in redacted
    assert "sk-abcdefghijk" not in redacted
    assert "[REDACTED]" in redacted
