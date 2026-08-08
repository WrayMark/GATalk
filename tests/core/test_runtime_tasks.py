from pathlib import Path

from scenelens.core.runtime_tasks import (
    RuntimeTaskCenter,
    RuntimeTaskStatus,
)


def test_runtime_task_center_persists_only_safe_summary(tmp_path: Path):
    path = tmp_path / "tasks.json"
    center = RuntimeTaskCenter(path)
    task_id = center.begin(
        title="AI 审阅",
        task_type="vision_review",
        module_id="test.module",
        provider_id="provider",
        model_id="model",
        input_summary={"image_count": 2},
        max_attempts=3,
    )
    center.finish(task_id)

    text = path.read_text(encoding="utf-8")
    assert "image_count" in text
    assert "api_key" not in text.casefold()
    assert RuntimeTaskCenter(path).tasks()[0].status == RuntimeTaskStatus.COMPLETED


def test_incomplete_persisted_task_is_marked_interrupted(tmp_path: Path):
    path = tmp_path / "tasks.json"
    center = RuntimeTaskCenter(path)
    center.begin(
        title="生成",
        task_type="image_edit",
        module_id="test",
    )

    reopened = RuntimeTaskCenter(path)

    assert reopened.tasks()[0].status == RuntimeTaskStatus.INTERRUPTED


def test_task_cancel_invokes_registered_canceller(tmp_path: Path):
    cancelled = []
    center = RuntimeTaskCenter(tmp_path / "tasks.json")
    task_id = center.begin(
        title="生成",
        task_type="image_edit",
        module_id="test",
        cancel=lambda: cancelled.append(True),
    )

    assert center.cancel(task_id)
    assert cancelled == [True]
    assert center.tasks()[0].status == RuntimeTaskStatus.CANCELLED

