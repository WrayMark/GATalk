from __future__ import annotations

from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditRequest,
    ImageEditResponse,
    ProviderError,
    ProviderManifest,
    require_user_approval,
)


class ImageEditSlotProvider:
    """Registered M2 capability slot; real execution is enabled in M3."""

    def __init__(self, manifest: ProviderManifest) -> None:
        self.manifest = manifest

    def edit_image(
        self,
        request: ImageEditRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ImageEditResponse:
        del credential
        require_user_approval(request)
        cancellation.raise_if_cancelled()
        raise ProviderError(
            "该图像编辑供应商已完成接口注册，将在 M3 启用真实编辑。",
            code="image_edit_not_enabled",
            retryable=False,
        )

