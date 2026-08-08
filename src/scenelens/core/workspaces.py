from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class WorkspaceDescriptor:
    module_id: str
    workspace_id: str
    display_name: str
    version: str
    level: str = "professional"
    parent_workspace_id: str | None = None
    category: str = ""

    @property
    def identity(self) -> tuple[str, str]:
        return self.module_id, self.workspace_id


@dataclass(frozen=True)
class ReviewerDescriptor:
    module_id: str
    reviewer_id: str
    display_name: str
    version: str
    supported_inputs: tuple[str, ...]
    output_schema: Mapping[str, Any]

    @property
    def identity(self) -> tuple[str, str]:
        return self.module_id, self.reviewer_id


@dataclass(frozen=True)
class KnowledgeDomainDescriptor:
    domain_id: str
    display_name: str
    description: str
    version: str
    enabled: bool = True


@dataclass(frozen=True)
class HandoffDescriptor:
    source_workspace_id: str
    target_workspace_id: str
    payload_type: str
    display_name: str


class WorkbenchRegistry:
    """Explicit registrations for trusted, built-in workbench contributions."""

    def __init__(self) -> None:
        self._workspaces: dict[
            tuple[str, str], WorkspaceDescriptor
        ] = {}
        self._reviewers: dict[tuple[str, str], Any] = {}
        self._providers: dict[str, Any] = {}
        self._knowledge_domains: dict[str, KnowledgeDomainDescriptor] = {}
        self._handoffs: dict[
            tuple[str, str, str], HandoffDescriptor
        ] = {}

    def register_workspace(self, descriptor: WorkspaceDescriptor) -> None:
        if descriptor.identity in self._workspaces:
            raise ValueError(
                "Workspace already registered: "
                f"{descriptor.module_id}/{descriptor.workspace_id}"
            )
        self._workspaces[descriptor.identity] = descriptor

    def register_reviewer(self, reviewer: Any) -> None:
        descriptor = reviewer.descriptor
        if not isinstance(descriptor, ReviewerDescriptor):
            raise TypeError("Reviewer must expose a ReviewerDescriptor.")
        if descriptor.identity in self._reviewers:
            raise ValueError(
                "Reviewer already registered: "
                f"{descriptor.module_id}/{descriptor.reviewer_id}"
            )
        self._reviewers[descriptor.identity] = reviewer

    def register_provider(self, provider: Any) -> None:
        provider_id = str(provider.manifest.provider_id)
        if provider_id in self._providers:
            raise ValueError(f"Provider already registered: {provider_id}")
        self._providers[provider_id] = provider

    def register_knowledge_domain(
        self,
        descriptor: KnowledgeDomainDescriptor,
    ) -> None:
        if descriptor.domain_id in self._knowledge_domains:
            raise ValueError(
                f"Knowledge domain already registered: {descriptor.domain_id}"
            )
        self._knowledge_domains[descriptor.domain_id] = descriptor

    def register_handoff(self, descriptor: HandoffDescriptor) -> None:
        identity = (
            descriptor.source_workspace_id,
            descriptor.target_workspace_id,
            descriptor.payload_type,
        )
        if identity in self._handoffs:
            raise ValueError(f"Handoff already registered: {identity}")
        self._handoffs[identity] = descriptor

    def get_reviewer(self, module_id: str, reviewer_id: str) -> Any:
        try:
            return self._reviewers[(module_id, reviewer_id)]
        except KeyError as exc:
            raise KeyError(
                f"Unknown reviewer: {module_id}/{reviewer_id}"
            ) from exc

    def get_provider(self, provider_id: str) -> Any:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"Unknown provider: {provider_id}") from exc

    def workspaces(self) -> tuple[WorkspaceDescriptor, ...]:
        return tuple(
            self._workspaces[key] for key in sorted(self._workspaces)
        )

    def reviewers(self) -> tuple[ReviewerDescriptor, ...]:
        return tuple(
            self._reviewers[key].descriptor
            for key in sorted(self._reviewers)
        )

    def providers(self) -> tuple[Any, ...]:
        return tuple(self._providers[key] for key in sorted(self._providers))

    def knowledge_domains(self) -> tuple[KnowledgeDomainDescriptor, ...]:
        return tuple(
            self._knowledge_domains[key]
            for key in sorted(self._knowledge_domains)
        )

    def handoffs(self) -> tuple[HandoffDescriptor, ...]:
        return tuple(self._handoffs[key] for key in sorted(self._handoffs))
