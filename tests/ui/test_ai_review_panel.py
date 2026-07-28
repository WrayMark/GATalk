from PySide6.QtWidgets import QLabel

from scenelens.analysis.evidence_validation import (
    EvidenceStatus,
    EvidenceValidation,
)
from scenelens.modules.visual_review.review_coordinator import (
    ReviewRunOutcome,
)
from scenelens.modules.visual_review.reviews import DeepArtDirectorReview
from scenelens.modules.visual_review.ui.ai_review_panel import (
    AIReviewPanel,
    DataDisclosureDialog,
)
from scenelens.providers.contracts import DataDisclosurePreview
from scenelens.providers.manifests import load_provider_manifests
from scenelens.providers.mock import _default_mock_output


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


def test_gemini_disclosure_warns_about_one_structure_repair_call(
    qtbot,
) -> None:
    dialog = DataDisclosureDialog(
        DataDisclosurePreview(
            provider_id="google_gemini",
            model_id="gemini-3.5-flash",
            payload_fields=("creative_intent",),
            images=(),
        ),
        second_opinion=False,
    )
    qtbot.addWidget(dialog)

    labels = [item.text() for item in dialog.findChildren(QLabel)]

    assert any("最多会自动执行一次结构纠错" in text for text in labels)
    assert any("增加少量费用" in text for text in labels)


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


def test_panel_presents_eight_dimensions_actions_and_local_conflict(
    qtbot,
) -> None:
    from scenelens.modules.visual_review.review_services import MergedFinding

    panel = AIReviewPanel(load_provider_manifests())
    qtbot.addWidget(panel)
    output = _default_mock_output(DeepArtDirectorReview().output_schema)
    output["target_readback"]["production_stage"] = "灯光初版"
    output["findings"] = [
        {
            "finding_id": "finding-1",
            "priority": "high",
            "observation": "主体与背景分离不足",
            "dimension_ids": ["focus_hierarchy"],
            "evidence_claims": [{"claim_id": "claim-1"}],
        }
    ]
    output["action_plan"] = [
        {
            "order": 1,
            "action": "先建立主体明度分离",
            "ue5_steps": ["锁定曝光", "调整主光"],
        }
    ]
    output["preserve_items"] = ["保留村口轮廓"]
    outcome = ReviewRunOutcome(
        reviewer_id="deep_art_director_review",
        provider_id="mock",
        model_id="mock",
        output=output,
        component_validations=(
            EvidenceValidation(
                claim_id="claim-1",
                status=EvidenceStatus.CONFLICT,
                measured_value=0.8,
                threshold=0.2,
                adjusted_confidence=0.4,
                reason="本地测量存在冲突",
            ),
        ),
        merged_findings=(
            MergedFinding(
                finding=output["findings"][0],
                primary_provider_id="mock",
                second_opinion_provider_id=None,
                second_opinion_status=None,
                disagreement=None,
            ),
        ),
    )

    panel.show_outcome(outcome)

    assert panel.dimension_tree.topLevelItemCount() == 8
    assert panel.action_plan_list.count() == 1
    assert panel.preserve_list.count() == 1
    assert panel.findings_tree.topLevelItem(0).text(4) == "存在冲突"


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
