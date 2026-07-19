"""Small cross-module contracts used by the SceneLens application shell."""

from scenelens.core.analyzers import (
    Analyzer,
    AnalyzerDescriptor,
    AnalyzerRegistry,
    AnalyzerRequest,
)

__all__ = [
    "Analyzer",
    "AnalyzerDescriptor",
    "AnalyzerRegistry",
    "AnalyzerRequest",
]
