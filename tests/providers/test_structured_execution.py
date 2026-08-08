from __future__ import annotations

from scenelens.core.runtime_tasks import RuntimeTaskCenter, RuntimeTaskStatus
from scenelens.modules.knowledge_base.translation import (
    create_translation_request,
    validate_translation_output,
)
from scenelens.providers.contracts import CancellationToken
from scenelens.providers.execution import ProviderExecutionService
from scenelens.providers.mock import MockProvider


def test_structured_translation_runs_offline_and_is_tracked(tmp_path):
    center = RuntimeTaskCenter(tmp_path / "runtime-tasks.json")
    service = ProviderExecutionService(
        sleep=lambda _delay: None,
        task_center=center,
    )
    provider = MockProvider()
    request = create_translation_request(
        "Key light",
        user_initiated=True,
        disclosure_confirmed=True,
    )
    try:
        response = service.run_structured(
            provider,
            request,
            "",
            CancellationToken(),
        )
    finally:
        service.close()

    translated = validate_translation_output(response.output)
    tasks = center.tasks()
    assert translated.translation
    assert tasks[-1].task_type == "structured_output"
    assert tasks[-1].status == RuntimeTaskStatus.COMPLETED
    assert "source_text" in tasks[-1].input_summary["payload_fields"]
