from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from scenelens.analysis.artwork_study import analyze_artwork
from scenelens.analysis.pipeline import measure_image
from scenelens.modules.comparative_study.analysis import build_local_comparison
from scenelens.modules.comparative_study.storage import ComparativeStudyStore


def _analysis(rgb: np.ndarray):
    return analyze_artwork(rgb, measure_image(rgb, palette_colours=4)).to_dict()


def test_local_comparison_uses_first_work_as_explicit_baseline():
    dark = np.full((48, 64, 3), 25, dtype=np.uint8)
    bright = np.full((48, 64, 3), 220, dtype=np.uint8)

    result = build_local_comparison(
        (("暗调", _analysis(dark)), ("亮调", _analysis(bright)))
    )

    assert result["baseline_title"] == "暗调"
    assert result["differences"][0]["mean_luminance_delta"] > 0.5
    assert result["result_type"] == "measurement"


def test_comparative_store_preserves_sources_and_active_selection(tmp_path: Path):
    root = tmp_path / "中文 对照研究"
    store = ComparativeStudyStore.create(root, "雾景对照")
    paths = []
    for name, value in (("作品一.png", 30), ("作品二.png", 190)):
        path = tmp_path / name
        Image.fromarray(np.full((32, 48, 3), value, dtype=np.uint8)).save(path)
        paths.append(path)
    first = store.import_image(
        paths[0],
        source_kind="knowledge_library",
        source_reference="library:item-1",
    )
    second = store.import_image(paths[1])
    store.set_active_items((second.item_id, first.item_id))
    store.save(
        replace(
            store.state,
            ai_history=(
                {
                    "run_id": "run-1",
                    "run": {"provider_id": "mock", "model_id": "mock"},
                    "output": {"executive_summary": "历史结果"},
                },
            ),
        )
    )

    reopened = ComparativeStudyStore.open(root)

    assert reopened.state.active_item_ids == (second.item_id, first.item_id)
    assert reopened.item(first.item_id).source_reference == "library:item-1"
    assert reopened.integrity_issues() == ()
    assert reopened.state.ai_history[0]["run_id"] == "run-1"


def test_removing_comparative_item_does_not_delete_original_asset(tmp_path: Path):
    store = ComparativeStudyStore.create(tmp_path / "study", "测试")
    source = tmp_path / "input.png"
    Image.new("RGB", (16, 16), (10, 20, 30)).save(source)
    item = store.import_image(source)
    copied = store.item_path(item)

    store.remove_items((item.item_id,))

    assert source.is_file()
    assert copied.is_file()


def test_comparative_study_limits_active_items_to_six(tmp_path: Path):
    store = ComparativeStudyStore.create(tmp_path / "study", "测试")
    ids = []
    for index in range(7):
        source = tmp_path / f"{index}.png"
        Image.new("RGB", (8, 8), (index, 0, 0)).save(source)
        ids.append(store.import_image(source).item_id)

    try:
        store.set_active_items(ids)
    except ValueError as exc:
        assert "六件" in str(exc)
    else:
        raise AssertionError("Expected selection limit to be enforced")
