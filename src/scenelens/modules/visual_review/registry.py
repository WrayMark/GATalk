from scenelens.core.analyzers import AnalyzerRegistry
from scenelens.modules.visual_review.analyzers import (
    BasicImageMeasurementsAnalyzer,
    LuminanceComparisonAnalyzer,
    PairedRegionAnalyzer,
    SharedPaletteAnalyzer,
)


def create_visual_review_registry() -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    registry.register(BasicImageMeasurementsAnalyzer())
    registry.register(SharedPaletteAnalyzer())
    registry.register(LuminanceComparisonAnalyzer())
    registry.register(PairedRegionAnalyzer())
    return registry
