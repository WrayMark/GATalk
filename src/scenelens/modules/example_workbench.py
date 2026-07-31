"""Trusted example contributions used to verify explicit registration.

This is intentionally not a dynamic plugin loader.
"""

from __future__ import annotations

from typing import Any, Mapping

from scenelens.core.workspaces import (
    ReviewerDescriptor,
    WorkbenchRegistry,
    WorkspaceDescriptor,
)
from scenelens.providers.contracts import (
    CancellationToken,
    ProviderCapability,
    ProviderManifest,
    ProviderResponse,
    VisionReviewRequest,
    require_user_approval,
)


class ExampleReviewer:
    descriptor = ReviewerDescriptor(
        module_id="scenelens.example",
        reviewer_id="example_review",
        display_name="示例审阅器",
        version="1.0.0",
        supported_inputs=("text",),
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
    )


class ExampleVisionProvider:
    manifest = ProviderManifest(
        provider_id="example_echo",
        display_name="示例离线 Provider",
        api_style="example",
        base_url="",
        capabilities=(ProviderCapability.VISION_REVIEW,),
        default_models={"vision_review": "example-v1"},
        credential_target="GATalk/provider/example",
        optional=True,
    )

    def review(
        self,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        del credential
        require_user_approval(request)
        cancellation.raise_if_cancelled()
        output: Mapping[str, Any] = {"message": "example"}
        return ProviderResponse(
            provider_id=self.manifest.provider_id,
            model_id=self.manifest.model_for(
                ProviderCapability.VISION_REVIEW
            ),
            output=output,
        )


def register_example_contributions(
    registry: WorkbenchRegistry,
) -> None:
    registry.register_workspace(
        WorkspaceDescriptor(
            module_id="scenelens.example",
            workspace_id="example_workspace",
            display_name="示例工作区",
            version="1.0.0",
        )
    )
    registry.register_reviewer(ExampleReviewer())
    registry.register_provider(ExampleVisionProvider())
