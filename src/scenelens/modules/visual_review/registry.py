from scenelens.core.analyzers import AnalyzerRegistry
from scenelens.modules.visual_review.analyzers import (
    BasicImageMeasurementsAnalyzer,
)


def create_visual_review_registry() -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    registry.register(BasicImageMeasurementsAnalyzer())
    return registry
