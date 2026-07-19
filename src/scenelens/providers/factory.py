from __future__ import annotations

from scenelens.providers.adapters import create_vision_provider
from scenelens.providers.contracts import ProviderCapability
from scenelens.providers.image_slots import ImageEditSlotProvider
from scenelens.providers.image_adapters import create_image_edit_provider
from scenelens.providers.manifests import load_provider_manifests
from scenelens.providers.mock import MockProvider
from scenelens.providers.registry import ProviderRegistry


def create_default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for manifest in load_provider_manifests():
        if manifest.provider_id == "mock":
            registry.register(MockProvider())
        elif ProviderCapability.VISION_REVIEW in manifest.capabilities:
            registry.register(create_vision_provider(manifest))
        elif ProviderCapability.IMAGE_EDIT in manifest.capabilities:
            if manifest.api_style == "image_edit_slot":
                registry.register(ImageEditSlotProvider(manifest))
            else:
                registry.register(create_image_edit_provider(manifest))
    return registry
