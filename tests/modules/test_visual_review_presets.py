from __future__ import annotations

import json
from importlib.resources import files

from scenelens.modules.visual_review.presets import load_visual_review_presets


def test_visual_review_presets_are_loaded_from_module_configuration():
    catalog = load_visual_review_presets()

    production_stage = catalog.field("production_stage")
    weather = catalog.field("weather")
    moods = catalog.field("target_moods")

    assert production_stage.input_mode == "editable_single"
    assert production_stage.allow_custom is True
    assert "白盒" in {option.label for option in production_stage.options}
    assert "薄雾" in {option.label for option in weather.options}
    assert moods.input_mode == "editable_multi"
    assert "神秘" in {option.label for option in moods.options}


def test_preset_catalog_does_not_translate_or_reject_unknown_user_values():
    catalog = load_visual_review_presets()
    known_labels = {
        option.label for option in catalog.field("weather").options
    }
    user_value = "魔法尘暴"

    assert user_value not in known_labels
    assert catalog.field("weather").allow_custom is True


def test_reference_visual_brief_exchange_schema_is_packaged():
    resource = files(
        "scenelens.modules.visual_review.schemas"
    ).joinpath("reference_visual_brief.schema.json")
    schema = json.loads(resource.read_text(encoding="utf-8"))

    assert schema["properties"]["format"]["const"] == (
        "scenelens.reference_visual_brief"
    )
    assert "ai_analysis" in schema["$defs"]["field"]["properties"]["source"][
        "enum"
    ]
