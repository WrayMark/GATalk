from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class WorkspaceDescriptor:
    module_id: str
    workspace_id: str
    display_name: str
    version: str

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


class WorkbenchRegistry:
    """Explicit registrations for trusted, built-in workbench contributions."""

    def __init__(self) -> None:
        self._workspaces: dict[
            tuple[str, str], WorkspaceDescriptor
        ] = {}
        self._reviewers: dict[tuple[str, str], Any] = {}
        self._providers: dict[str, Any] = {}

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

