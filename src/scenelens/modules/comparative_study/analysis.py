from __future__ import annotations

from typing import Any, Mapping, Sequence


ANALYZER_ID = "comparative_formal_evidence"
ANALYZER_VERSION = "1.0.0"


def build_local_comparison(
    items: Sequence[tuple[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    if len(items) < 2:
        raise ValueError("对照研究至少需要两件作品。")
    rows: list[dict[str, Any]] = []
    for title, analysis in items:
        value = dict(analysis.get("value_structure", {}))
        colour = dict(analysis.get("colour_structure", {}))
        structure = dict(analysis.get("structure", {}))
        rows.append(
            {
                "title": title,
                "mean_luminance": float(value.get("mean_linear_luminance", 0.0)),
                "effective_span": float(value.get("effective_span_p10_p90", 0.0)),
                "three_value_ratios": list(
                    value.get("three_value_ratios", (0.0, 0.0, 0.0))
                ),
                "mean_saturation": float(colour.get("mean_saturation", 0.0)),
                "neutral_ratio": float(colour.get("neutral_ratio", 0.0)),
                "edge_density": float(structure.get("global_edge_density", 0.0)),
                "palette": list(colour.get("palette", ())),
            }
        )
    baseline = rows[0]
    differences = []
    for row in rows[1:]:
        differences.append(
            {
                "baseline": baseline["title"],
                "compared": row["title"],
                "mean_luminance_delta": row["mean_luminance"]
                - baseline["mean_luminance"],
                "effective_span_delta": row["effective_span"]
                - baseline["effective_span"],
                "mean_saturation_delta": row["mean_saturation"]
                - baseline["mean_saturation"],
                "neutral_ratio_delta": row["neutral_ratio"]
                - baseline["neutral_ratio"],
                "edge_density_delta": row["edge_density"]
                - baseline["edge_density"],
                "three_value_ratio_delta": [
                    current - reference
                    for reference, current in zip(
                        baseline["three_value_ratios"],
                        row["three_value_ratios"],
                        strict=True,
                    )
                ],
            }
        )
    return {
        "analyzer_id": ANALYZER_ID,
        "analyzer_version": ANALYZER_VERSION,
        "baseline_title": baseline["title"],
        "rows": rows,
        "differences": differences,
        "result_type": "measurement",
        "limitations": [
            "数值差异只描述画面特征，不自动判断优劣。",
            "不同题材、媒介和展示尺寸会影响可比性。",
            "构图、叙事和风格判断仍需结合画面证据人工确认。",
        ],
    }


def format_local_comparison(value: Mapping[str, Any]) -> str:
    rows = list(value.get("rows", ()))
    differences = list(value.get("differences", ()))
    lines = ["本地测量对照"]
    for row in rows:
        bands = row["three_value_ratios"]
        lines.append(
            f"{row['title']}：平均明度 {row['mean_luminance']:.3f}；"
            f"暗/中/亮 {bands[0] * 100:.1f}% / {bands[1] * 100:.1f}% / "
            f"{bands[2] * 100:.1f}%；平均饱和度 {row['mean_saturation']:.3f}；"
            f"中性色 {row['neutral_ratio'] * 100:.1f}%；"
            f"边缘密度 {row['edge_density']:.3f}。"
        )
    lines.append("")
    lines.append("相对第一件作品的差异（百分点与数值差）")
    for item in differences:
        lines.append(
            f"{item['compared']}：明度 {item['mean_luminance_delta']:+.3f}；"
            f"明度跨度 {item['effective_span_delta']:+.3f}；"
            f"饱和度 {item['mean_saturation_delta']:+.3f}；"
            f"中性色比例 {item['neutral_ratio_delta'] * 100:+.1f} 个百分点；"
            f"边缘密度 {item['edge_density_delta']:+.3f}。"
        )
    lines.extend(("", "边界：这些是测量结果，不等同于审美结论或质量评分。"))
    return "\n".join(lines)
