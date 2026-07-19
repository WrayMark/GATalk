from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ReviewContext:
    project_id: str
    shot_id: str
    version_id: str
    creative_intent: Mapping[str, Any]
    reference_visual_brief: Mapping[str, Any]
    global_measurements: Mapping[str, Any]
    paired_region_measurements: tuple[Mapping[str, Any], ...] = ()
    version_history: tuple[Mapping[str, Any], ...] = ()
    locked_goals: tuple[str, ...] = ()
    quality_gates: tuple[Mapping[str, Any], ...] = ()
    production_context: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "shot_id": self.shot_id,
            "version_id": self.version_id,
            "creative_intent": dict(self.creative_intent),
            "reference_visual_brief": dict(
                self.reference_visual_brief
            ),
            "global_measurements": dict(self.global_measurements),
            "paired_region_measurements": [
                dict(value) for value in self.paired_region_measurements
            ],
            "version_history": [
                dict(value) for value in self.version_history
            ],
            "locked_goals": list(self.locked_goals),
            "quality_gates": [
                dict(value) for value in self.quality_gates
            ],
            "production_context": dict(self.production_context),
        }
