from __future__ import annotations

import json
from importlib.resources import files

from scenelens.providers.contracts import ProviderManifest


def load_provider_manifests() -> tuple[ProviderManifest, ...]:
    resource = files("scenelens.providers.config").joinpath(
        "providers.json"
    )
    data = json.loads(resource.read_text(encoding="utf-8"))
    if int(data.get("schema_version", 0)) != 1:
        raise ValueError("不支持的 Provider Manifest 配置版本。")
    manifests = tuple(
        ProviderManifest.from_dict(item) for item in data["providers"]
    )
    identities = [manifest.provider_id for manifest in manifests]
    if len(identities) != len(set(identities)):
        raise ValueError("Provider Manifest 包含重复 provider_id。")
    return manifests

