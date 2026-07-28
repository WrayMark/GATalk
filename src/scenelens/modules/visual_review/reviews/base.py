from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Mapping

from scenelens.core.schema_validation import require_valid_json_schema
from scenelens.providers.contracts import (
    ProviderImage,
    VisionReviewRequest,
)

from .context import ReviewContext


@dataclass(frozen=True)
class ValidatedReview:
    reviewer_id: str
    output: Mapping[str, Any]


def load_review_schema(filename: str) -> Mapping[str, Any]:
    resource = files(
        "scenelens.modules.visual_review.schemas"
    ).joinpath(filename)
    return json.loads(resource.read_text(encoding="utf-8"))


class StructuredVisionReviewer:
    schema_filename: str
    system_instruction: str
    max_output_tokens: int | None = None

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return load_review_schema(self.schema_filename)

    def create_request(
        self,
        context: ReviewContext,
        images: tuple[ProviderImage, ...],
        *,
        model_id: str | None = None,
        user_initiated: bool = False,
        disclosure_confirmed: bool = False,
    ) -> VisionReviewRequest:
        roles = {image.role for image in images}
        if not {"reference", "current"}.issubset(roles):
            raise ValueError("专项审阅需要 reference 和 current 两张图片。")
        return VisionReviewRequest(
            system_instruction=self.system_instruction,
            payload=context.to_payload(),
            images=images,
            output_schema=self.output_schema,
            model_id=model_id,
            user_initiated=user_initiated,
            disclosure_confirmed=disclosure_confirmed,
            max_output_tokens=self.max_output_tokens,
        )

    def validate_output(
        self,
        output: Mapping[str, Any],
    ) -> ValidatedReview:
        require_valid_json_schema(output, self.output_schema)
        return ValidatedReview(
            reviewer_id=self.descriptor.reviewer_id,
            output=dict(output),
        )
