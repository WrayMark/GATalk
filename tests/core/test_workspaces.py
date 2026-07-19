from dataclasses import dataclass

import pytest

from scenelens.core.workspaces import (
    ReviewerDescriptor,
    WorkbenchRegistry,
    WorkspaceDescriptor,
)


@dataclass(frozen=True)
class DummyReviewer:
    descriptor: ReviewerDescriptor


@dataclass(frozen=True)
class DummyManifest:
    provider_id: str


@dataclass(frozen=True)
class DummyProvider:
    manifest: DummyManifest


def test_workbench_registry_accepts_trusted_workspace_reviewer_and_provider():
    registry = WorkbenchRegistry()
    workspace = WorkspaceDescriptor(
        module_id="example.notes",
        workspace_id="research",
        display_name="研究示例",
        version="1",
    )
    reviewer = DummyReviewer(
        ReviewerDescriptor(
            module_id="example.notes",
            reviewer_id="source_review",
            display_name="来源审阅",
            version="1",
            supported_inputs=("source_document",),
            output_schema={"type": "object"},
        )
    )
    provider = DummyProvider(DummyManifest("example.mock"))

    registry.register_workspace(workspace)
    registry.register_reviewer(reviewer)
    registry.register_provider(provider)

    assert registry.workspaces() == (workspace,)
    assert registry.reviewers() == (reviewer.descriptor,)
    assert registry.get_reviewer("example.notes", "source_review") is reviewer
    assert registry.get_provider("example.mock") is provider


def test_workbench_registry_rejects_duplicate_contributions():
    registry = WorkbenchRegistry()
    workspace = WorkspaceDescriptor("example", "one", "示例", "1")
    registry.register_workspace(workspace)

    with pytest.raises(ValueError, match="already registered"):
        registry.register_workspace(workspace)

