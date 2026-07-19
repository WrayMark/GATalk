from scenelens.analysis.grading import SafeGradeRecipe
from scenelens.analysis.match_profile import MatchDimension, MatchProfile
from scenelens.analysis.preview_validation import PreviewValidation
from scenelens.core.domain import AIConceptPreviewStatus
from scenelens.modules.visual_review.preview_instructions import (
    PreviewEditMode,
)
from scenelens.modules.visual_review.ui.optimization_lab import (
    OptimizationLabPanel,
)
from scenelens.providers.manifests import load_provider_manifests


def test_optimization_lab_defaults_to_explicit_offline_flow(qtbot) -> None:
    panel = OptimizationLabPanel(load_provider_manifests())
    qtbot.addWidget(panel)

    assert panel.image_provider_combo.currentData() == "mock"
    assert panel.concept_run_button.text() == "查看发送清单并生成预演"
    assert panel.preview_remove_metadata.isChecked()
    assert panel.concept_options().maximum_side == 2048
    assert panel.concept_options().mode == PreviewEditMode.LIGHTING_ONLY


def test_change_budget_is_quantized_and_warns_above_75(qtbot) -> None:
    panel = OptimizationLabPanel(load_provider_manifests())
    qtbot.addWidget(panel)

    panel.concept_strength.setValue(83)
    assert panel.concept_strength.value() == 85
    assert panel.concept_options().change_budget_percent == 85
    assert "高风险" in panel.budget_semantics.text()


def test_match_profile_keeps_missing_evidence_visible(qtbot) -> None:
    panel = OptimizationLabPanel(load_provider_manifests())
    qtbot.addWidget(panel)
    panel.show_match_profile(
        MatchProfile(
            dimensions=(
                MatchDimension(
                    "luminance_structure",
                    "明度结构",
                    0.75,
                    "measurement",
                    "测试证据",
                ),
                MatchDimension(
                    "visual_focus",
                    "视觉焦点",
                    None,
                    "art_judgment",
                    "不能猜测",
                ),
            ),
            weights={
                "luminance_structure": 1.0,
                "visual_focus": 1.0,
            },
            estimated_match=0.75,
            evidence_coverage=0.5,
        )
    )

    assert panel.match_tree.topLevelItemCount() == 2
    assert panel.match_tree.topLevelItem(1).text(1) == "证据不足"
    assert "75.0%" in panel.match_summary.text()
    assert "50.0%" in panel.match_summary.text()


def test_grade_recipe_marks_non_lut_workflow(qtbot) -> None:
    panel = OptimizationLabPanel(load_provider_manifests())
    qtbot.addWidget(panel)
    recipe = SafeGradeRecipe(
        reference_colour_transfer=0.2,
        strength_percent=25,
    )
    panel.show_grade_preview(recipe)

    assert panel.export_png_button.isEnabled()
    assert panel.export_json_button.isEnabled()
    assert not panel.export_cube_button.isEnabled()
    assert "原图保持只读" in panel.grade_status.text()


def test_concept_validation_displays_concept_only_boundary(qtbot) -> None:
    panel = OptimizationLabPanel(load_provider_manifests())
    qtbot.addWidget(panel)
    validation = PreviewValidation(
        structure_drift=0.3,
        stable_region_change=0.1,
        protected_region_change=0.2,
        composition_shift=0.15,
        target_improvement=0.04,
        status=AIConceptPreviewStatus.CONCEPT_ONLY,
        reasons=("结构漂移超过阈值",),
    )
    panel.show_concept_validation(
        validation,
        provider_id="mock",
        model_id="mock-image-v1",
    )

    assert "仅适合概念参考" in panel.concept_status.text()
    assert "结构漂移" in panel.concept_status.text()
    assert panel.concept_task_button.isEnabled()
