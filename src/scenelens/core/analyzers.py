from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class AnalyzerDescriptor:
    module_id: str
    analyzer_id: str
    display_name: str
    version: str
    supported_inputs: tuple[str, ...]
    parameter_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]

    @property
    def identity(self) -> tuple[str, str]:
        return self.module_id, self.analyzer_id


@dataclass(frozen=True)
class AnalyzerRequest:
    inputs: Mapping[str, Any]
    input_hashes: Mapping[str, str]
    parameters: Mapping[str, Any]


@runtime_checkable
class Analyzer(Protocol):
    descriptor: AnalyzerDescriptor

    def run(self, request: AnalyzerRequest) -> Any:
        """Run the analyzer without UI or storage side effects."""

    def cache_key(self, request: AnalyzerRequest) -> str:
        """Return a deterministic key for identity, inputs and parameters."""


class AnalyzerRegistry:
    def __init__(self) -> None:
        self._analyzers: dict[tuple[str, str], Analyzer] = {}

    def register(self, analyzer: Analyzer) -> None:
        identity = analyzer.descriptor.identity
        if identity in self._analyzers:
            raise ValueError(
                "Analyzer already registered: "
                f"{identity[0]}/{identity[1]}"
            )
        self._analyzers[identity] = analyzer

    def get(self, module_id: str, analyzer_id: str) -> Analyzer:
        try:
            return self._analyzers[(module_id, analyzer_id)]
        except KeyError as exc:
            raise KeyError(
                f"Unknown analyzer: {module_id}/{analyzer_id}"
            ) from exc

    def descriptors(self) -> tuple[AnalyzerDescriptor, ...]:
        return tuple(
            analyzer.descriptor
            for _, analyzer in sorted(self._analyzers.items())
        )


def deterministic_analyzer_cache_key(
    descriptor: AnalyzerDescriptor,
    request: AnalyzerRequest,
) -> str:
    payload = {
        "module_id": descriptor.module_id,
        "analyzer_id": descriptor.analyzer_id,
        "version": descriptor.version,
        "input_hashes": dict(request.input_hashes),
        "parameters": dict(request.parameters),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
