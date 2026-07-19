from __future__ import annotations

from typing import Any

from scenelens.providers.contracts import (
    ProviderCapability,
    ProviderManifest,
)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}
        self._manifests: dict[str, ProviderManifest] = {}

    def register(self, provider: Any) -> None:
        manifest = provider.manifest
        if not isinstance(manifest, ProviderManifest):
            raise TypeError("Provider must expose a ProviderManifest.")
        if manifest.provider_id in self._providers:
            raise ValueError(
                f"Provider already registered: {manifest.provider_id}"
            )
        self._providers[manifest.provider_id] = provider
        self._manifests[manifest.provider_id] = manifest

    def get(self, provider_id: str) -> Any:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"Unknown provider: {provider_id}") from exc

    def manifest(self, provider_id: str) -> ProviderManifest:
        try:
            return self._manifests[provider_id]
        except KeyError as exc:
            raise KeyError(f"Unknown provider: {provider_id}") from exc

    def for_capability(
        self,
        capability: ProviderCapability,
    ) -> tuple[Any, ...]:
        providers = (
            provider
            for provider in self._providers.values()
            if capability in provider.manifest.capabilities
        )
        return tuple(
            sorted(
                providers,
                key=lambda item: (
                    item.manifest.mainland_priority,
                    item.manifest.display_name,
                ),
            )
        )

    def manifests(self) -> tuple[ProviderManifest, ...]:
        return tuple(
            self._manifests[key] for key in sorted(self._manifests)
        )

