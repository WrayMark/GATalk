from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

import numpy as np

from scenelens.analysis.asset_masks import visible_asset_mask
from scenelens.modules.asset_breakdown.artifacts import asset_crop_png
from scenelens.modules.asset_breakdown.models import AssetItem
from scenelens.modules.asset_breakdown.reviews import (
    AssetBreakdownReview,
    asset_generation_instruction,
)
from scenelens.modules.asset_breakdown.service import asset_from_ai
from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditProvider,
    ImageEditRequest,
    ProviderError,
    ProviderCapability,
    ProviderImage,
    VisionReviewProvider,
    VisionReviewRequest,
)
from scenelens.providers.execution import (
    ProviderExecutionService,
    ReviewExecutionResult,
)


@dataclass(frozen=True)
class AutomaticGeneratedAsset:
    asset: AssetItem
    image_bytes: bytes
    provider_id: str
    model_id: str
    instruction: Mapping[str, Any]
    mask: np.ndarray
    mask_method: str


@dataclass(frozen=True)
class AutomaticPipelineResult:
    assets: tuple[AssetItem, ...]
    generated: tuple[AutomaticGeneratedAsset, ...]
    failures: tuple[tuple[str, str], ...]
    repair_notes: tuple[str, ...]
    review_execution: ReviewExecutionResult
    stopped_early: bool = False
    cancelled: bool = False


def provider_error_message(error: BaseException) -> str:
    if isinstance(error, ProviderError):
        return error.to_user_message()
    text = str(error).strip()
    return text or error.__class__.__name__


def is_systemic_provider_error(error: BaseException) -> bool:
    """Return True when repeating the same provider call is not useful."""

    if not isinstance(error, ProviderError):
        return True
    if error.code in {"cancelled", "missing_image_output"}:
        return False
    return (
        error.code.startswith("http_")
        or error.code
        in {
            "network_error",
            "connection_closed",
            "output_connection_closed",
            "invalid_image_resolution",
            "unsupported_image_resolution",
            "invalid_credential",
        }
    )


def run_automatic_pipeline(
    *,
    reviewer: AssetBreakdownReview,
    review_provider: VisionReviewProvider,
    review_request: VisionReviewRequest,
    review_credential: str,
    image_provider: ImageEditProvider,
    image_credential: str,
    image_model_id: str | None,
    image_resolution: str,
    full_scene: ProviderImage,
    rgb: np.ndarray,
    source_image_id: str,
    scene_type: str,
    output_kind: str,
    asset_limit: int,
    execution: ProviderExecutionService,
    cancellation: CancellationToken,
) -> AutomaticPipelineResult:
    review_execution = execution.run_review_with_model_fallback(
        review_provider,
        review_request,
        review_credential,
        cancellation,
        review_provider.manifest.fallback_models_for(
            capability=ProviderCapability.VISION_REVIEW,
            requested_model=review_request.model_id,
        ),
    )
    output, repair_notes = reviewer.normalize_output(
        review_execution.response.output
    )
    assets = tuple(
        asset_from_ai(item, source_image_id=source_image_id)
        for item in output["assets"][: max(1, asset_limit)]
    )
    retained_ids = {asset.asset_id for asset in assets}
    assets = tuple(
        replace(asset, parent_asset_id="")
        if asset.parent_asset_id
        and asset.parent_asset_id not in retained_ids
        else asset
        for asset in assets
    )
    generated: list[AutomaticGeneratedAsset] = []
    failures: list[tuple[str, str]] = []
    stopped_early = False
    for asset in assets:
        if cancellation.cancelled:
            break
        mask, method = visible_asset_mask(rgb, asset.normalized_rect)
        crop = asset_crop_png(rgb, asset, mask)
        instruction = asset_generation_instruction(
            asset.to_dict(),
            output_kind=output_kind,
            scene_type=scene_type,
        )
        instruction = {
            **instruction,
            "output_resolution": image_resolution,
        }
        request = ImageEditRequest(
            instruction=instruction,
            images=(
                full_scene,
                ProviderImage(
                    "asset_visible_crop",
                    "image/png",
                    crop,
                ),
            ),
            model_id=image_model_id,
            change_budget=35,
            user_initiated=True,
            disclosure_confirmed=True,
            timeout_seconds=240.0,
        )
        try:
            response = execution.run_image_edit(
                image_provider,
                request,
                image_credential,
                cancellation,
            )
        except Exception as error:
            if cancellation.cancelled:
                break
            failures.append((asset.asset_id, provider_error_message(error)))
            if is_systemic_provider_error(error):
                stopped_early = True
                break
            continue
        generated.append(
            AutomaticGeneratedAsset(
                asset=replace(
                    asset,
                    mask_method=method,
                ),
                image_bytes=response.image_bytes,
                provider_id=response.provider_id,
                model_id=response.model_id,
                instruction=instruction,
                mask=mask,
                mask_method=method,
            )
        )
    return AutomaticPipelineResult(
        assets=assets,
        generated=tuple(generated),
        failures=tuple(failures),
        repair_notes=repair_notes,
        review_execution=review_execution,
        stopped_early=stopped_early,
        cancelled=cancellation.cancelled,
    )
