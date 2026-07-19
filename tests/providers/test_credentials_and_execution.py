from __future__ import annotations

from dataclasses import dataclass

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

