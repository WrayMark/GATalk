from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol, runtime_checkable


class ProviderCapability(StrEnum):
    VISION_REVIEW = "vision_review"
    STRUCTURED_OUTPUT = "structured_output"
    IMAGE_EDIT = "image_edit"


@dataclass(frozen=True)
class ProviderManifest:
    provider_id: str
    display_name: str
    api_style: str
    base_url: str
    capabilities: tuple[ProviderCapability, ...]
    default_models: Mapping[str, str]
    credential_target: str
    optional: bool = True
    mainland_priority: int = 100
    options: Mapping[str, Any] = field(default_factory=dict)

    def model_for(
        self,
        capability: ProviderCapability,
        override: str | None = None,
    ) -> str:
        if override:
            return override
        try:
            return str(self.default_models[capability.value])
        except KeyError as exc:
            raise ValueError(
                f"{self.provider_id} 未配置 {capability.value} 默认模型。"
            ) from exc

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ProviderManifest:
        return cls(
            provider_id=str(value["provider_id"]),
            display_name=str(value["display_name"]),
            api_style=str(value["api_style"]),
            base_url=str(value["base_url"]).rstrip("/"),
            capabilities=tuple(
                ProviderCapability(str(item))
                for item in value["capabilities"]
            ),
            default_models={
                str(key): str(model)
                for key, model in dict(value["default_models"]).items()
            },
            credential_target=str(value["credential_target"]),
            optional=bool(value.get("optional", True)),
            mainland_priority=int(value.get("mainland_priority", 100)),
            options=dict(value.get("options", {})),
        )


@dataclass(frozen=True)
class ProviderImage:
    role: str
    media_type: str
    data: bytes
    sha256: str = ""

    def __post_init__(self) -> None:
        if not self.media_type.startswith("image/"):
            raise ValueError("ProviderImage media_type must be an image type.")
        if not self.data:
            raise ValueError("ProviderImage data must not be empty.")
        if not self.sha256:
            object.__setattr__(
                self,
                "sha256",
                hashlib.sha256(self.data).hexdigest(),
            )


@dataclass(frozen=True)
class VisionReviewRequest:
    system_instruction: str
    payload: Mapping[str, Any]
    images: tuple[ProviderImage, ...]
    output_schema: Mapping[str, Any]
    model_id: str | None = None
    user_initiated: bool = False
    disclosure_confirmed: bool = False
    timeout_seconds: float = 120.0
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if (
            self.max_output_tokens is not None
            and self.max_output_tokens <= 0
        ):
            raise ValueError("max_output_tokens must be positive.")

    def canonical_payload(self) -> str:
        return json.dumps(
            dict(self.payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class StructuredOutputRequest:
    system_instruction: str
    payload: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    model_id: str | None = None
    user_initiated: bool = False
    disclosure_confirmed: bool = False
    timeout_seconds: float = 120.0


@dataclass(frozen=True)
class ImageEditRequest:
    instruction: Mapping[str, Any]
    images: tuple[ProviderImage, ...]
    model_id: str | None = None
    change_budget: int = 25
    user_initiated: bool = False
    disclosure_confirmed: bool = False
    timeout_seconds: float = 180.0


@dataclass(frozen=True)
class ProviderResponse:
    provider_id: str
    model_id: str
    output: Mapping[str, Any]
    request_id: str | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImageEditResponse:
    provider_id: str
    model_id: str
    media_type: str
    image_bytes: bytes
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DisclosureImage:
    role: str
    media_type: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class DataDisclosurePreview:
    provider_id: str
    model_id: str
    payload_fields: tuple[str, ...]
    images: tuple[DisclosureImage, ...]


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise ProviderCancelledError()


class ProviderError(RuntimeError):
    def __init__(
        self,
        public_message: str,
        *,
        code: str,
        retryable: bool = False,
        technical_detail: str = "",
    ) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.code = code
        self.retryable = retryable
        self.technical_detail = technical_detail

    def to_user_message(self) -> str:
        lines = [self.public_message, f"错误代码：{self.code}"]
        detail = self.technical_detail.strip()
        if detail:
            lines.append(f"服务返回：{detail}")
        return "\n".join(lines)


class ProviderCancelledError(ProviderError):
    def __init__(self) -> None:
        super().__init__(
            "AI 任务已取消。",
            code="cancelled",
            retryable=False,
        )


@runtime_checkable
class VisionReviewProvider(Protocol):
    manifest: ProviderManifest

    def review(
        self,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        """Run a user-approved multimodal review request."""


@runtime_checkable
class StructuredOutputProvider(Protocol):
    manifest: ProviderManifest

    def generate_structured(
        self,
        request: StructuredOutputRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        """Run a user-approved structured text request."""


@runtime_checkable
class ImageEditProvider(Protocol):
    manifest: ProviderManifest

    def edit_image(
        self,
        request: ImageEditRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ImageEditResponse:
        """Run a user-approved image edit request."""


def disclosure_preview(
    manifest: ProviderManifest,
    request: VisionReviewRequest | ImageEditRequest,
) -> DataDisclosurePreview:
    capability = (
        ProviderCapability.VISION_REVIEW
        if isinstance(request, VisionReviewRequest)
        else ProviderCapability.IMAGE_EDIT
    )
    payload = (
        request.payload
        if isinstance(request, VisionReviewRequest)
        else request.instruction
    )
    return DataDisclosurePreview(
        provider_id=manifest.provider_id,
        model_id=manifest.model_for(capability, request.model_id),
        payload_fields=tuple(sorted(str(key) for key in payload)),
        images=tuple(
            DisclosureImage(
                role=image.role,
                media_type=image.media_type,
                byte_size=len(image.data),
                sha256=image.sha256,
            )
            for image in request.images
        ),
    )


def require_user_approval(
    request: VisionReviewRequest | StructuredOutputRequest | ImageEditRequest,
) -> None:
    if not request.user_initiated or not request.disclosure_confirmed:
        raise ProviderError(
            "发送已取消：请先查看并确认将发送的数据。",
            code="disclosure_not_confirmed",
            retryable=False,
        )
