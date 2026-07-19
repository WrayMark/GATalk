from scenelens.modules.visual_review.review_coordinator import (
    ReviewRunOutcome,
)
from scenelens.modules.visual_review.ui.ai_review_panel import AIReviewPanel
from scenelens.providers.manifests import load_provider_manifests


def test_ai_panel_defaults_to_offline_mock_and_explicit_send(qtbot) -> None:
    panel = AIReviewPanel(load_provider_manifests())
    qtbot.addWidget(panel)
    assert panel.provider_combo.currentData() == "mock"
    assert panel.run_button.text() == "查看发送清单并审阅"
    assert panel.remove_metadata_checkbox.isChecked()
    assert panel.options().maximum_side == 2048


def test_second_opinion_has_visible_extra_cost_warning(qtbot) -> None:
    panel = AIReviewPanel(load_provider_manifests())
    qtbot.addWidget(panel)
    panel.second_opinion_checkbox.setChecked(True)
    assert panel.second_provider_combo.isEnabled()
    assert panel.cost_warning.isVisibleTo(panel)


def test_panel_displays_conflicts_instead_of_hiding_them(qtbot) -> None:
    panel = AIReviewPanel(load_provider_manifests())
    qtbot.addWidget(panel)
    from scenelens.modules.visual_review.review_services import MergedFinding

    outcome = ReviewRunOutcome(
        reviewer_id="art_director_review",
        provider_id="mock",
        model_id="mock-v1",
        output={"summary": "需要复核"},
        component_validations=(),
        merged_findings=(
            MergedFinding(
                finding={
                    "priority": "high",
                    "observation": "入口偏暗",
                },
                primary_provider_id="mock",
                second_opinion_provider_id="other",
                second_opinion_status="conflict",
                disagreement="测量不支持。",
            ),
        ),
    )
    panel.show_outcome(outcome)
    assert panel.findings_tree.topLevelItemCount() == 1
    assert (
        panel.findings_tree.topLevelItem(0).text(2) == "conflict"
    )
    assert (
        panel.findings_tree.topLevelItem(0).toolTip(2) == "测量不支持。"
    )


def test_panel_emits_selected_lighting_scheme_annotations(qtbot) -> None:
    panel = AIReviewPanel(load_provider_manifests())
    qtbot.addWidget(panel)
    scheme = {
        "strategy": "faithful_to_reference",
        "annotations": [
            {
                "kind": "light_arrow",
                "points": [{"x": 0.1, "y": 0.2}, {"x": 0.4, "y": 0.5}],
                "label": "主光",
            }
        ],
    }
    outcome = ReviewRunOutcome(
        reviewer_id="lighting_review",
        provider_id="mock",
        model_id="mock",
        output={"summary": "mock", "target_schemes": [scheme]},
        component_validations=(),
        merged_findings=(),
    )
    with qtbot.waitSignal(panel.annotations_selected) as blocker:
        panel.show_outcome(outcome)
    assert blocker.args[0]["annotations"][0]["label"] == "主光"
