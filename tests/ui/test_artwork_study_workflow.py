from copy import deepcopy
from io import BytesIO

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from scenelens.modules.artwork_study.reviews import (
    ArtworkMasterStudyReview,
    ArtworkStudyContext,
)
from scenelens.modules.artwork_study.storage import ArtworkStudyStore
from scenelens.modules.artwork_study.ui.window import ArtworkStudyWindow
from scenelens.core.handoffs import WorkspaceHandoff
from scenelens.providers.contracts import (
    CancellationToken,
    ProviderImage,
    ProviderResponse,
)
from scenelens.providers.mock import MockProvider
from scenelens.ui.workspace_hub import WorkspaceHubWindow


def test_workspace_hub_exposes_two_major_modules(qtbot):
    hub = WorkspaceHubWindow()
    qtbot.addWidget(hub)
    selected = []
    hub.workspace_selected.connect(selected.append)

    artwork_button = next(
        button
        for button in hub.findChildren(QPushButton)
        if button.text() == "进入作品研究"
    )
    qtbot.mouseClick(artwork_button, Qt.MouseButton.LeftButton)
    assert selected == ["artwork_study"]


def test_artwork_study_window_loads_analyzes_and_restores_project(
    qtbot, tmp_path
):
    source = tmp_path / "优秀 场景.png"
    rgb = np.zeros((80, 120, 3), dtype=np.uint8)
    rgb[:, :60] = (28, 54, 88)
    rgb[:, 60:] = (205, 142, 74)
    Image.fromarray(rgb).save(source)
    store = ArtworkStudyStore.create(
        tmp_path / "作品研究.scenelens-study",
        "作品研究",
    )
    store.import_image(source)

    window = ArtworkStudyWindow()
    qtbot.addWidget(window)
    window._set_store(ArtworkStudyStore.open(store.root))
    qtbot.waitUntil(
        lambda: window._local_analysis is not None,
        timeout=15_000,
    )

    assert window.canvas.has_image
    assert window.spatial_tree.topLevelItemCount() == 9
    assert "注意力代理" in window.local_summary.toPlainText()
    window.goal_edit.setPlainText("学习空间与色彩")
    window.notes_edit.setPlainText("个人判断")
    window._save_state(force=True)

    reopened = ArtworkStudyStore.open(store.root)
    assert reopened.state.study_goal == "学习空间与色彩"
    assert reopened.state.personal_notes == "个人判断"
    assert reopened.state.local_analysis["analyzer_id"]


def test_artwork_study_emits_editable_asset_breakdown_handoff(
    qtbot, tmp_path
) -> None:
    source = tmp_path / "寺院 原画.png"
    Image.new("RGB", (120, 80), (50, 80, 100)).save(source)
    store = ArtworkStudyStore.create(
        tmp_path / "寺院研究.scenelens-study",
        "寺院研究",
    )
    store.import_image(source)
    window = ArtworkStudyWindow()
    qtbot.addWidget(window)
    window._set_store(ArtworkStudyStore.open(store.root))
    qtbot.waitUntil(lambda: window._loaded is not None, timeout=5000)
    window.goal_edit.setPlainText("理解建筑族与空间层级")
    window.notes_edit.setPlainText("中央高塔是地标")
    received = []
    window.asset_breakdown_requested.connect(received.append)
    window._send_to_asset_breakdown()
    assert len(received) == 1
    handoff = received[0]
    assert isinstance(handoff, WorkspaceHandoff)
    assert handoff.primary_image_sha256 == store.state.image_sha256
    assert handoff.payload["personal_notes"] == "中央高塔是地标"
    assert "image_path" not in handoff.payload


def test_artwork_result_status_is_chinese_and_old_english_is_hidden(qtbot):
    buffer = BytesIO()
    Image.fromarray(np.zeros((24, 32, 3), dtype=np.uint8)).save(
        buffer, format="PNG"
    )
    reviewer = ArtworkMasterStudyReview()
    request = reviewer.create_request(
        ArtworkStudyContext(
            study_id="study",
            title="test",
            work_type="environment_concept",
            study_goal="理解构图",
            known_context="",
            image_metadata={"width": 32, "height": 24},
            local_evidence={},
        ),
        (
            ProviderImage(
                "artwork",
                "image/png",
                buffer.getvalue(),
            ),
        ),
        user_initiated=True,
        disclosure_confirmed=True,
    )
    output = MockProvider().review(
        request, "", CancellationToken()
    ).output
    window = ArtworkStudyWindow()
    qtbot.addWidget(window)

    window._show_ai_output(output)
    assert window.ai_dimension_tree.topLevelItem(0).text(1) == "证据不足"

    english = deepcopy(output)
    english["dimension_studies"][0]["observation"] = (
        "The composition directs the eye through a diagonal."
    )
    assert window._review_is_current_and_chinese(english) is False
    window._clear_ai_output()
    assert window.ai_dimension_tree.topLevelItemCount() == 0


def test_artwork_english_response_gets_one_chinese_normalization_call(qtbot):
    buffer = BytesIO()
    Image.fromarray(np.zeros((24, 32, 3), dtype=np.uint8)).save(
        buffer, format="PNG"
    )
    reviewer = ArtworkMasterStudyReview()
    request = reviewer.create_request(
        ArtworkStudyContext(
            study_id="study",
            title="test",
            work_type="environment_concept",
            study_goal="理解构图",
            known_context="",
            image_metadata={"width": 32, "height": 24},
            local_evidence={},
        ),
        (
            ProviderImage(
                "artwork",
                "image/png",
                buffer.getvalue(),
            ),
        ),
        model_id="test-model",
        user_initiated=True,
        disclosure_confirmed=True,
    )
    chinese = MockProvider().review(
        request, "", CancellationToken()
    ).output
    english = deepcopy(chinese)
    english["dimension_studies"][0]["observation"] = (
        "The composition directs the eye through a diagonal."
    )

    class SequenceExecution:
        def __init__(self):
            self.requests = []
            self.responses = [
                ProviderResponse("test", "test-model", english),
                ProviderResponse("test", "test-model", chinese),
            ]

        def run_review(
            self, _provider, value, _credential, _cancellation
        ):
            self.requests.append(value)
            return self.responses.pop(0)

        def run_review_with_model_fallback(
            self,
            provider,
            value,
            credential,
            cancellation,
            _fallback_model_ids=(),
        ):
            from scenelens.providers.execution import ReviewExecutionResult

            response = self.run_review(
                provider,
                value,
                credential,
                cancellation,
            )
            return ReviewExecutionResult(
                response=response,
                requested_model_id=str(value.model_id),
                attempted_model_ids=(str(value.model_id),),
            )

        def close(self):
            pass

    window = ArtworkStudyWindow()
    qtbot.addWidget(window)
    window._execution.close()
    execution = SequenceExecution()
    window._execution = execution

    response, output, normalized, execution_result = (
        window._execute_review_with_language_contract(
            object(),
            request,
            "secret",
            CancellationToken(),
        )
    )

    assert response.provider_id == "test"
    assert output["dimension_studies"][0]["observation"] == "Mock 未观察图片。"
    assert normalized is True
    assert execution_result.fallback_used is False
    assert len(execution.requests) == 2
    assert execution.requests[1].images == ()
