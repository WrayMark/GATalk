from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditProvider,
    ImageEditRequest,
    ImageEditResponse,
    ProviderCancelledError,
    ProviderError,
    ProviderResponse,
    VisionReviewProvider,
    VisionReviewRequest,
)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 0.25


@dataclass
class ProviderJob:
    future: Future
    cancellation: CancellationToken

    def cancel(self) -> bool:
        self.cancellation.cancel()
        return self.future.cancel()


class ProviderExecutionService:
    def __init__(
        self,
        max_workers: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="scenelens-ai",
        )
        self._sleep = sleep

    def submit_review(
        self,
        provider: VisionReviewProvider,
        request: VisionReviewRequest,
        credential: str,
        retry_policy: RetryPolicy | None = None,
    ) -> ProviderJob:
        cancellation = CancellationToken()
        policy = retry_policy or RetryPolicy()
        future = self._executor.submit(
            self.run_review,
            provider,
            request,
            credential,
            cancellation,
            policy,
        )
        return ProviderJob(future=future, cancellation=cancellation)

    def run_review(
        self,
        provider: VisionReviewProvider,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
        retry_policy: RetryPolicy | None = None,
    ) -> ProviderResponse:
        policy = retry_policy or RetryPolicy()
        if policy.max_attempts < 1:
            raise ValueError("max_attempts must be at least one.")
        for attempt in range(1, policy.max_attempts + 1):
            cancellation.raise_if_cancelled()
            try:
                return provider.review(request, credential, cancellation)
            except ProviderCancelledError:
                raise
            except ProviderError as exc:
                exc.technical_detail = redact_sensitive_text(
                    exc.technical_detail,
                    credential,
                )
                if not exc.retryable or attempt >= policy.max_attempts:
                    raise
                delay = policy.initial_backoff_seconds * (2 ** (attempt - 1))
                cancellation.raise_if_cancelled()
                self._sleep(delay)
        raise AssertionError("retry loop ended unexpectedly")

    def submit_image_edit(
        self,
        provider: ImageEditProvider,
        request: ImageEditRequest,
        credential: str,
        retry_policy: RetryPolicy | None = None,
    ) -> ProviderJob:
        cancellation = CancellationToken()
        policy = retry_policy or RetryPolicy()
        future = self._executor.submit(
            self.run_image_edit,
            provider,
            request,
            credential,
            cancellation,
            policy,
        )
        return ProviderJob(future=future, cancellation=cancellation)

    def run_image_edit(
        self,
        provider: ImageEditProvider,
        request: ImageEditRequest,
        credential: str,
        cancellation: CancellationToken,
        retry_policy: RetryPolicy | None = None,
    ) -> ImageEditResponse:
        policy = retry_policy or RetryPolicy()
        if policy.max_attempts < 1:
            raise ValueError("max_attempts must be at least one.")
        for attempt in range(1, policy.max_attempts + 1):
            cancellation.raise_if_cancelled()
            try:
                return provider.edit_image(
                    request,
                    credential,
                    cancellation,
                )
            except ProviderCancelledError:
                raise
            except ProviderError as exc:
                exc.technical_detail = redact_sensitive_text(
                    exc.technical_detail,
                    credential,
                )
                if not exc.retryable or attempt >= policy.max_attempts:
                    raise
                delay = policy.initial_backoff_seconds * (2 ** (attempt - 1))
                cancellation.raise_if_cancelled()
                self._sleep(delay)
        raise AssertionError("retry loop ended unexpectedly")

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def redact_sensitive_text(value: str, credential: str = "") -> str:
    result = str(value)
    if credential:
        result = result.replace(credential, "[REDACTED]")
    patterns = (
        (
            r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+",
            "Bearer [REDACTED]",
        ),
        (r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]"),
        (
            r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+",
            r"\1[REDACTED]",
        ),
    )
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result
