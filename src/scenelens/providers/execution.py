from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Callable

from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditProvider,
    ImageEditRequest,
    ImageEditResponse,
    ProviderCancelledError,
    ProviderCapability,
    ProviderError,
    ProviderResponse,
    VisionReviewProvider,
    VisionReviewRequest,
)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0


@dataclass
class ProviderJob:
    future: Future
    cancellation: CancellationToken

    def cancel(self) -> bool:
        self.cancellation.cancel()
        return self.future.cancel()


@dataclass(frozen=True)
class ReviewExecutionResult:
    response: ProviderResponse
    requested_model_id: str
    attempted_model_ids: tuple[str, ...]
    fallback_used: bool = False
    fallback_reason: str = ""


def _fallback_error_with_route(
    error: ProviderError,
    attempted_model_ids: list[str],
    failed_models: list[str],
    *,
    all_models_unavailable: bool = False,
) -> ProviderError:
    detail = error.technical_detail.strip()
    route = "model_attempts=" + "->".join(attempted_model_ids)
    failures = "model_errors=" + ",".join(failed_models)
    technical_detail = " | ".join(
        item for item in (detail, route, failures) if item
    )
    public_message = error.public_message
    if all_models_unavailable:
        public_message = (
            "当前模型及已配置的备用模型均不可用，"
            "请稍后重试或在模型 ID 中选择其他可用模型。"
        )
    return ProviderError(
        public_message,
        code=error.code,
        retryable=error.retryable,
        technical_detail=technical_detail,
    )


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
                if exc.retryable and attempt >= policy.max_attempts:
                    detail = exc.technical_detail.strip()
                    suffix = f"retry_attempts={attempt}"
                    exc.technical_detail = (
                        f"{detail} | {suffix}" if detail else suffix
                    )
                if not exc.retryable or attempt >= policy.max_attempts:
                    raise
                delay = policy.initial_backoff_seconds * (2 ** (attempt - 1))
                cancellation.raise_if_cancelled()
                self._sleep(delay)
        raise AssertionError("retry loop ended unexpectedly")

    def run_review_with_model_fallback(
        self,
        provider: VisionReviewProvider,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
        fallback_model_ids: tuple[str, ...] = (),
        retry_policy: RetryPolicy | None = None,
    ) -> ReviewExecutionResult:
        requested_model_id = provider.manifest.model_for(
            ProviderCapability.VISION_REVIEW,
            request.model_id,
        )
        primary_request = replace(request, model_id=requested_model_id)
        attempted_model_ids = [requested_model_id]
        try:
            response = self.run_review(
                provider,
                primary_request,
                credential,
                cancellation,
                retry_policy,
            )
        except ProviderError as primary_error:
            candidates = tuple(
                dict.fromkeys(
                    model_id.strip()
                    for model_id in fallback_model_ids
                    if model_id.strip()
                    and model_id.strip() != requested_model_id
                )
            )
            recoverable_codes = {"http_404", "http_503"}
            if primary_error.code not in recoverable_codes or not candidates:
                raise
            failed_models = [f"{requested_model_id}:{primary_error.code}"]
            last_error = primary_error
            for fallback_model_id in candidates:
                attempted_model_ids.append(fallback_model_id)
                fallback_request = replace(
                    primary_request,
                    model_id=fallback_model_id,
                )
                cancellation.raise_if_cancelled()
                try:
                    response = self.run_review(
                        provider,
                        fallback_request,
                        credential,
                        cancellation,
                        RetryPolicy(max_attempts=1),
                    )
                except ProviderError as fallback_error:
                    last_error = fallback_error
                    failed_models.append(
                        f"{fallback_model_id}:{fallback_error.code}"
                    )
                    if fallback_error.code in recoverable_codes:
                        continue
                    raise _fallback_error_with_route(
                        fallback_error,
                        attempted_model_ids,
                        failed_models,
                    ) from fallback_error
                return ReviewExecutionResult(
                    response=response,
                    requested_model_id=requested_model_id,
                    attempted_model_ids=tuple(attempted_model_ids),
                    fallback_used=True,
                    fallback_reason=primary_error.code,
                )
            raise _fallback_error_with_route(
                last_error,
                attempted_model_ids,
                failed_models,
                all_models_unavailable=True,
            ) from last_error
        return ReviewExecutionResult(
            response=response,
            requested_model_id=requested_model_id,
            attempted_model_ids=(requested_model_id,),
        )

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
                if exc.retryable and attempt >= policy.max_attempts:
                    detail = exc.technical_detail.strip()
                    suffix = f"retry_attempts={attempt}"
                    exc.technical_detail = (
                        f"{detail} | {suffix}" if detail else suffix
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
