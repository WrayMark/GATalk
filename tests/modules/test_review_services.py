from scenelens.core.domain import QualityGate, QualityGateState
from scenelens.modules.visual_review.review_services import (
    SecondOpinionItem,
    VersionChangeStatus,
    build_offline_review_pack,
    compare_versions_to_target,
    evaluate_quality_gate,
    merge_second_opinion,
)


def _gate() -> QualityGate:
    return QualityGate(
        id="gate",
        profile_id="profile",
        dimension_id="focus",
        display_name="焦点分离",
        metric_key="focus_delta",
        operator=">=",
        threshold={"value": 0.2, "warning_margin": 0.03},
        weight=1.0,
        state=QualityGateState.NOT_EVALUATED,
        updated_at="2026-07-19T00:00:00Z",
    )


def test_quality_gates_replace_generic_total_score() -> None:
    assert (
        evaluate_quality_gate(_gate(), {"focus_delta": 0.22}).state
        == QualityGateState.PASS
    )
    assert (
        evaluate_quality_gate(_gate(), {"focus_delta": 0.18}).state
        == QualityGateState.WARNING
    )
    assert (
        evaluate_quality_gate(_gate(), {}).state
        == QualityGateState.INSUFFICIENT_EVIDENCE
    )


def test_version_comparison_reports_change_not_a_score() -> None:
    assert (
        compare_versions_to_target(0.3, 0.2)
        == VersionChangeStatus.IMPROVED
    )
    assert (
        compare_versions_to_target(0.2, 0.3)
        == VersionChangeStatus.FURTHER_AWAY
    )
    assert (
        compare_versions_to_target(0.2, 0.195)
        == VersionChangeStatus.NO_CLEAR_CHANGE
    )
    assert (
        compare_versions_to_target(None, 0.2)
        == VersionChangeStatus.INSUFFICIENT_EVIDENCE
    )


def test_second_opinion_preserves_sources_and_disagreement() -> None:
    findings = [{"finding_id": "f1", "observation": "入口偏暗"}]
    merged = merge_second_opinion(
        findings,
        primary_provider_id="aliyun_bailian",
        second_provider_id="openai",
        opinions=(
            SecondOpinionItem(
                finding_id="f1",
                source_provider_id="openai",
                status="conflict",
                critique="区域测量显示入口并不暗。",
            ),
        ),
    )
    assert merged[0].primary_provider_id == "aliyun_bailian"
    assert merged[0].second_opinion_provider_id == "openai"
    assert merged[0].disagreement == "区域测量显示入口并不暗。"


def test_offline_pack_excludes_local_paths_and_credentials() -> None:
    result = build_offline_review_pack(
        reviewer_id="lighting_review",
        context={"creative_intent": {"目标情绪": "宁静"}},
        image_manifest=(
            {
                "role": "current",
                "sha256": "abc",
                "media_type": "image/png",
                "filename": "截图.png",
                "local_path": "C:/秘密/截图.png",
            },
        ),
        output_schema={"type": "object"},
    )
    assert "local_path" not in result["images"][0]
    assert result["format"] == "scenelens.offline_review_pack"
