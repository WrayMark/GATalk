from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Callable, Mapping

from scenelens.core.runtime_tasks import (
    RuntimeTaskCenter,
    RuntimeTaskStatus,
    runtime_task_center,
)

from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditProvider,
    ImageEditRequest,
    ImageEditResponse,
    ProviderCancelledError,
    ProviderCapability,
    ProviderError,
    ProviderResponse,
    StructuredOutputProvider,
    StructuredOutputRequest,
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
        task_center: RuntimeTaskCenter | None = None,
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="scenelens-ai",
        )
        self._sleep = sleep
        self._task_center = task_center or runtime_task_center()

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
        manifest = getattr(provider, "manifest", None)
        provider_id = str(getattr(manifest, "provider_id", "unknown"))
        requested_model = getattr(request, "model_id", None)
        model_id = (
            manifest.model_for(
                ProviderCapability.VISION_REVIEW,
                requested_model,
            )
            if manifest is not None
            else str(requested_model or "unknown")
        )
        payload = getattr(request, "payload", {})
        images = getattr(request, "images", ())
        task_id = self._task_center.begin(
            title="AI 视觉审阅",
            task_type="vision_review",
            module_id=_request_module_id(payload),
            provider_id=provider_id,
            model_id=model_id,
            progress_total=policy.max_attempts,
            max_attempts=policy.max_attempts,
            input_summary={
                "image_count": len(images),
                "payload_fields": sorted(str(key) for key in payload),
            },
            cancel=cancellation.cancel,
        )
        for attempt in range(1, policy.max_attempts + 1):
            self._task_center.update(
                task_id,
                attempt=attempt,
                progress_current=attempt - 1,
            )
            try:
                cancellation.raise_if_cancelled()
                response = provider.review(request, credential, cancellation)
                self._task_center.update(
                    task_id,
                    progress_current=attempt,
                )
                self._task_center.finish(task_id)
                return response
            except ProviderCancelledError:
                self._task_center.finish(
                    task_id,
                    status=RuntimeTaskStatus.CANCELLED,
                )
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
                    self._task_center.fail(
                        task_id,
                        exc.public_message,
                        exc.technical_detail,
                    )
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

    def submit_structured(
        self,
        provider: StructuredOutputProvider,
        request: StructuredOutputRequest,
        credential: str,
        retry_policy: RetryPolicy | None = None,
    ) -> ProviderJob:
        cancellation = CancellationToken()
        policy = retry_policy or RetryPolicy()
        future = self._executor.submit(
            self.run_structured,
            provider,
            request,
            credential,
            cancellation,
            policy,
        )
        return ProviderJob(future=future, cancellation=cancellation)

    def run_structured(
        self,
        provider: StructuredOutputProvider,
        request: StructuredOutputRequest,
        credential: str,
        cancellation: CancellationToken,
        retry_policy: RetryPolicy | None = None,
    ) -> ProviderResponse:
        policy = retry_policy or RetryPolicy()
        if policy.max_attempts < 1:
            raise ValueError("max_attempts must be at least one.")
        manifest = getattr(provider, "manifest", None)
        provider_id = str(getattr(manifest, "provider_id", "unknown"))
        model_id = (
            manifest.model_for(
                ProviderCapability.STRUCTURED_OUTPUT,
                request.model_id,
            )
            if manifest is not None
            else str(request.model_id or "unknown")
        )
        payload = getattr(request, "payload", {})
        task_id = self._task_center.begin(
            title="AI 结构化文本处理",
            task_type="structured_output",
            module_id=_request_module_id(payload),
            provider_id=provider_id,
            model_id=model_id,
            progress_total=policy.max_attempts,
            max_attempts=policy.max_attempts,
            input_summary={
                "payload_fields": sorted(str(key) for key in payload),
            },
            cancel=cancellation.cancel,
        )
        for attempt in range(1, policy.max_attempts + 1):
            self._task_center.update(
                task_id,
                attempt=attempt,
                progress_current=attempt - 1,
            )
            try:
                cancellation.raise_if_cancelled()
                response = provider.generate_structured(
                    request,
                    credential,
                    cancellation,
                )
                self._task_center.update(task_id, progress_current=attempt)
                self._task_center.finish(task_id)
                return response
            except ProviderCancelledError:
                self._task_center.finish(
                    task_id,
                    status=RuntimeTaskStatus.CANCELLED,
                )
                raise
            except ProviderError as exc:
                exc.technical_detail = redact_sensitive_text(
                    exc.technical_detail,
                    credential,
                )
                if not exc.retryable or attempt >= policy.max_attempts:
                    self._task_center.fail(
                        task_id,
                        exc.public_message,
                        exc.technical_detail,
                    )
                    raise
                delay = policy.initial_backoff_seconds * (2 ** (attempt - 1))
                cancellation.raise_if_cancelled()
                self._sleep(delay)
        raise AssertionError("retry loop ended unexpectedly")

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
        manifest = getattr(provider, "manifest", None)
        provider_id = str(getattr(manifest, "provider_id", "unknown"))
        requested_model = getattr(request, "model_id", None)
        model_id = (
            manifest.model_for(
                ProviderCapability.IMAGE_EDIT,
                requested_model,
            )
            if manifest is not None
            else str(requested_model or "unknown")
        )
        instruction = getattr(request, "instruction", {})
        images = getattr(request, "images", ())
        task_id = self._task_center.begin(
            title="AI 图像生成或编辑",
            task_type="image_edit",
            module_id=_request_module_id(instruction),
            provider_id=provider_id,
            model_id=model_id,
            progress_total=policy.max_attempts,
            max_attempts=policy.max_attempts,
            input_summary={
                "image_count": len(images),
                "instruction_fields": sorted(
                    str(key) for key in instruction
                ),
            },
            cancel=cancellation.cancel,
        )
        for attempt in range(1, policy.max_attempts + 1):
            self._task_center.update(
                task_id,
                attempt=attempt,
                progress_current=attempt - 1,
            )
            try:
                cancellation.raise_if_cancelled()
                response = provider.edit_image(
                    request,
                    credential,
                    cancellation,
                )
                self._task_center.update(
                    task_id,
                    progress_current=attempt,
                )
                self._task_center.finish(task_id)
                return response
            except ProviderCancelledError:
                self._task_center.finish(
                    task_id,
                    status=RuntimeTaskStatus.CANCELLED,
                )
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
                    self._task_center.fail(
                        task_id,
                        exc.public_message,
                        exc.technical_detail,
                    )
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


def _request_module_id(payload: object) -> str:
    if isinstance(payload, Mapping):
        explicit = payload.get("module_id")
        if explicit:
            return str(explicit)
        if "study" in payload:
            return "scenelens.study"
        if "asset_breakdown" in payload or "scene" in payload:
            return "scenelens.asset_breakdown"
        if "project" in payload or "shot" in payload:
            return "scenelens.visual_review"
    return "gatalk.ai"
