from __future__ import annotations

import json
from typing import Any, Mapping

from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditRequest,
    ImageEditResponse,
    ProviderCapability,
    ProviderManifest,
    ProviderResponse,
    StructuredOutputRequest,
    VisionReviewRequest,
    require_user_approval,
)


class MockProvider:
    def __init__(
        self,
        output: Mapping[str, Any] | None = None,
        image_bytes: bytes = b"mock-image",
    ) -> None:
        self.manifest = ProviderManifest(
            provider_id="mock",
            display_name="离线 Mock",
            api_style="mock",
            base_url="",
            capabilities=(
                ProviderCapability.VISION_REVIEW,
                ProviderCapability.STRUCTURED_OUTPUT,
                ProviderCapability.IMAGE_EDIT,
            ),
            default_models={
                ProviderCapability.VISION_REVIEW.value: "mock-vision-v1",
                ProviderCapability.STRUCTURED_OUTPUT.value: "mock-json-v1",
                ProviderCapability.IMAGE_EDIT.value: "mock-image-v1",
            },
            credential_target="SceneLens/provider/mock",
            optional=False,
            mainland_priority=0,
        )
        self.output = dict(output or {"findings": []})
        self.image_bytes = bytes(image_bytes)

    def review(
        self,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        del credential
        require_user_approval(request)
        cancellation.raise_if_cancelled()
        return ProviderResponse(
            provider_id=self.manifest.provider_id,
            model_id=self.manifest.model_for(
                ProviderCapability.VISION_REVIEW,
                request.model_id,
            ),
            output=json.loads(json.dumps(self.output)),
        )

    def generate_structured(
        self,
        request: StructuredOutputRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        del credential
        require_user_approval(request)
        cancellation.raise_if_cancelled()
        return ProviderResponse(
            provider_id=self.manifest.provider_id,
            model_id=self.manifest.model_for(
                ProviderCapability.STRUCTURED_OUTPUT,
                request.model_id,
            ),
            output=json.loads(json.dumps(self.output)),
        )

    def edit_image(
        self,
        request: ImageEditRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ImageEditResponse:
        del credential
        require_user_approval(request)
        cancellation.raise_if_cancelled()
        return ImageEditResponse(
            provider_id=self.manifest.provider_id,
            model_id=self.manifest.model_for(
                ProviderCapability.IMAGE_EDIT,
                request.model_id,
            ),
            media_type="image/png",
            image_bytes=self.image_bytes,
            metadata={"change_budget": request.change_budget},
        )

