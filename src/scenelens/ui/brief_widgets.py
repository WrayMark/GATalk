from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scenelens.modules.visual_review.presets import PresetCatalog
from scenelens.storage.models import BriefFieldValue, FieldSource


@dataclass(frozen=True)
class BriefFieldSpec:
    key: str
    label: str
    group: str
    editor: str = "line"
    preset_key: str | None = None


CREATIVE_INTENT_FIELDS = (
    BriefFieldSpec("scene_type", "场景类型", "制作意图"),
    BriefFieldSpec(
        "production_stage",
        "当前制作阶段",
        "制作意图",
        "preset_single",
        "production_stage",
    ),
    BriefFieldSpec("target_style", "目标风格", "制作意图"),
    BriefFieldSpec("worldview", "时代或世界观", "制作意图"),
    BriefFieldSpec("time", "时间", "环境", "preset_single", "time"),
    BriefFieldSpec("season", "季节", "环境", "preset_single", "season"),
    BriefFieldSpec("weather", "天气", "环境", "preset_single", "weather"),
    BriefFieldSpec(
        "target_moods",
        "目标情绪",
        "环境",
        "preset_multi",
        "target_moods",
    ),
    BriefFieldSpec("primary_focus", "第一视觉焦点", "视觉重点"),
    BriefFieldSpec("secondary_focus", "次要视觉焦点", "视觉重点"),
    BriefFieldSpec(
        "preserve_content",
        "希望保留的内容",
        "制作约束",
        "multiline",
    ),
    BriefFieldSpec(
        "main_issues",
        "当前主要问题",
        "制作约束",
        "multiline",
    ),
    BriefFieldSpec(
        "excluded_review",
        "暂不审阅的内容",
        "制作约束",
        "multiline",
    ),
    BriefFieldSpec(
        "constraints",
        "制作条件与限制",
        "制作约束",
        "multiline",
    ),
    BriefFieldSpec(
        "additional_notes",
        "自定义补充说明",
        "制作约束",
        "multiline",
    ),
)


REFERENCE_VISUAL_FIELDS = (
    BriefFieldSpec(
        "reference_use",
        "参考用途",
        "1. 参考用途",
        "preset_multi",
        "reference_use",
    ),
    BriefFieldSpec("inferred_time", "推断时间", "2. 时间与环境", "preset_single", "time"),
    BriefFieldSpec(
        "inferred_season",
        "推断季节",
        "2. 时间与环境",
        "preset_single",
        "season",
    ),
    BriefFieldSpec(
        "inferred_weather",
        "推断天气",
        "2. 时间与环境",
        "preset_single",
        "weather",
    ),
    BriefFieldSpec("air_state", "空气状态", "2. 时间与环境"),
    BriefFieldSpec("visibility", "能见度", "2. 时间与环境"),
    BriefFieldSpec("wetness", "环境干湿感", "2. 时间与环境"),
    BriefFieldSpec("lighting_environment", "光照环境", "2. 时间与环境"),
    BriefFieldSpec("primary_focus", "第一视觉焦点", "3. 构图与层级"),
    BriefFieldSpec("secondary_focus", "次要视觉焦点", "3. 构图与层级"),
    BriefFieldSpec("visual_flow", "视觉动线", "3. 构图与层级", "multiline"),
    BriefFieldSpec("depth_roles", "前中远景作用", "3. 构图与层级", "multiline"),
    BriefFieldSpec("visual_balance", "画面重心", "3. 构图与层级"),
    BriefFieldSpec("negative_space", "主要负空间", "3. 构图与层级"),
    BriefFieldSpec("framing", "遮挡与框景关系", "3. 构图与层级", "multiline"),
    BriefFieldSpec("dominant_colour", "主色倾向", "4. Color Key"),
    BriefFieldSpec("supporting_colour", "辅助色倾向", "4. Color Key"),
    BriefFieldSpec("accent_colour", "点缀色倾向", "4. Color Key"),
    BriefFieldSpec("overall_value", "整体明度", "4. Color Key"),
    BriefFieldSpec("overall_saturation", "整体饱和度", "4. Color Key"),
    BriefFieldSpec("temperature_relation", "冷暖关系", "4. Color Key"),
    BriefFieldSpec("shadow_highlight_colour", "暗部与亮部色彩", "4. Color Key"),
    BriefFieldSpec("depth_colour_relation", "前中远景色彩关系", "4. Color Key"),
    BriefFieldSpec("colour_mood", "色彩情绪", "4. Color Key"),
    BriefFieldSpec("key_direction", "主光方向", "5. 灯光与氛围"),
    BriefFieldSpec("key_softness", "主光软硬", "5. 灯光与氛围"),
    BriefFieldSpec("key_colour", "主光颜色", "5. 灯光与氛围"),
    BriefFieldSpec("sky_light", "天空光倾向", "5. 灯光与氛围"),
    BriefFieldSpec("shadow_tendency", "阴影倾向", "5. 灯光与氛围"),
    BriefFieldSpec("local_highlights", "局部高光", "5. 灯光与氛围"),
    BriefFieldSpec("fog_perspective", "雾与空气透视", "5. 灯光与氛围"),
    BriefFieldSpec("contrast_distribution", "明暗反差分配", "5. 灯光与氛围"),
    BriefFieldSpec("spatial_layers", "空间层次", "5. 灯光与氛围"),
    BriefFieldSpec("overall_mood", "整体情绪", "5. 灯光与氛围"),
    BriefFieldSpec("architecture_language", "建筑语言", "6. 内容与制作"),
    BriefFieldSpec("material_features", "材质特征", "6. 内容与制作"),
    BriefFieldSpec("terrain_features", "地形特点", "6. 内容与制作"),
    BriefFieldSpec("vegetation_features", "植被特点", "6. 内容与制作"),
    BriefFieldSpec("detail_density", "资产和细节密度", "6. 内容与制作"),
    BriefFieldSpec("narrative_clues", "叙事线索", "6. 内容与制作"),
    BriefFieldSpec(
        "essential_features",
        "最值得还原的视觉特征",
        "6. 内容与制作",
        "multiline",
    ),
    BriefFieldSpec("simplifiable_content", "可以简化的内容", "6. 内容与制作", "multiline"),
    BriefFieldSpec("ue_notes", "UE 制作提示", "6. 内容与制作", "multiline"),
)


AUTOMATIC_REFERENCE_FIELDS = (
    ("image_dimensions", "图片尺寸", "自动测量"),
    ("aspect_ratio", "宽高比", "自动测量"),
    ("source_format", "源格式", "自动测量"),
    ("icc_status", "ICC / 色彩空间", "自动测量"),
    ("oklab_palette", "Oklab 色板", "算法推断"),
    ("luminance_histogram", "明度分布", "自动测量"),
    ("three_value_ratios", "三阶明度比例", "自动测量"),
    ("five_value_ratios", "五阶明度比例", "自动测量"),
    ("hue_distribution", "色相分布", "自动测量"),
    ("saturation_distribution", "饱和度分布", "自动测量"),
)


SOURCE_LABELS = {
    FieldSource.AUTOMATIC_MEASUREMENT: "自动测量",
    FieldSource.ALGORITHM_INFERENCE: "算法推断",
    FieldSource.AI_ANALYSIS: "AI 分析",
    FieldSource.USER_INPUT: "用户填写",
    FieldSource.USER_REVISION: "用户修订",
}


class MultiPresetEditor(QWidget):
    def __init__(
        self,
        options: tuple[str, ...],
        value: Any,
        parent=None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        self.list_widget.setMaximumHeight(130)
        layout.addWidget(self.list_widget)
        current = _value_list(value)
        known = set(options)
        for option in options:
            item = QListWidgetItem(option)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if option in current
                else Qt.CheckState.Unchecked
            )
            self.list_widget.addItem(item)
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("自定义，可用顿号或逗号分隔")
        self.custom_edit.setText("、".join(item for item in current if item not in known))
        layout.addWidget(self.custom_edit)

    def value(self) -> list[str]:
        selected = [
            self.list_widget.item(index).text()
            for index in range(self.list_widget.count())
            if self.list_widget.item(index).checkState() == Qt.CheckState.Checked
        ]
        for item in _value_list(self.custom_edit.text()):
            if item not in selected:
                selected.append(item)
        return selected


class BriefEditorDialog(QDialog):
    def __init__(
        self,
        title: str,
        field_specs: tuple[BriefFieldSpec, ...],
        fields: dict[str, BriefFieldValue],
        presets: PresetCatalog,
        *,
        read_only: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 820)
        self._fields = fields
        self._field_specs = field_specs
        self._read_only = read_only
        self.editors: dict[str, QWidget] = {}

        root = QVBoxLayout(self)
        source_hint = QLabel(
            "字段标签显示当前来源。保存即视为用户确认；自动、算法或 AI 内容"
            "不会覆盖用户填写或修订。"
        )
        source_hint.setWordWrap(True)
        root.addWidget(source_hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        contents = QWidget()
        contents_layout = QVBoxLayout(contents)
        for group_name in dict.fromkeys(spec.group for spec in field_specs):
            box = QGroupBox(group_name)
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            for spec in (item for item in field_specs if item.group == group_name):
                field = fields.get(spec.key)
                value = "" if field is None else field.value
                editor = self._make_editor(spec, value, presets)
                editor.setEnabled(not read_only)
                self.editors[spec.key] = editor
                source = "未填写" if field is None else SOURCE_LABELS[field.source]
                confirmed = (
                    " · 已确认"
                    if field is not None and field.user_confirmed
                    else ""
                )
                form.addRow(f"{spec.label} [{source}{confirmed}]：", editor)
            contents_layout.addWidget(box)
        contents_layout.addStretch(1)
        scroll.setWidget(contents)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            (
                QDialogButtonBox.StandardButton.Close
                if read_only
                else QDialogButtonBox.StandardButton.Save
                | QDialogButtonBox.StandardButton.Cancel
            )
        )
        if read_only:
            buttons.rejected.connect(self.reject)
            buttons.accepted.connect(self.accept)
        else:
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for spec in self._field_specs:
            editor = self.editors[spec.key]
            if isinstance(editor, QTextEdit):
                result[spec.key] = editor.toPlainText().strip()
            elif isinstance(editor, QComboBox):
                data = editor.currentData()
                result[spec.key] = (
                    str(data)
                    if data is not None
                    and editor.currentText() == editor.itemText(editor.currentIndex())
                    else editor.currentText().strip()
                )
            elif isinstance(editor, MultiPresetEditor):
                result[spec.key] = editor.value()
            elif isinstance(editor, QLineEdit):
                result[spec.key] = editor.text().strip()
        return result

    @staticmethod
    def _make_editor(
        spec: BriefFieldSpec,
        value: Any,
        presets: PresetCatalog,
    ) -> QWidget:
        if spec.editor == "multiline":
            editor = QTextEdit()
            editor.setPlainText(_display_value(value))
            editor.setMinimumHeight(72)
            return editor
        if spec.editor == "preset_single" and spec.preset_key:
            editor = QComboBox()
            editor.setEditable(True)
            for option in presets.field(spec.preset_key).options:
                editor.addItem(option.label, option.label)
            wanted = _display_value(value)
            index = editor.findData(wanted)
            if index >= 0:
                editor.setCurrentIndex(index)
            else:
                editor.setEditText(wanted)
            return editor
        if spec.editor == "preset_multi" and spec.preset_key:
            return MultiPresetEditor(
                tuple(
                    option.label
                    for option in presets.field(spec.preset_key).options
                ),
                value,
            )
        return QLineEdit(_display_value(value))


class ReferenceVisualBriefDialog(BriefEditorDialog):
    def __init__(
        self,
        fields: dict[str, BriefFieldValue],
        presets: PresetCatalog,
        *,
        read_only: bool = False,
        parent=None,
    ) -> None:
        super().__init__(
            "参考图视觉简报",
            REFERENCE_VISUAL_FIELDS,
            fields,
            presets,
            read_only=read_only,
            parent=parent,
        )
        scroll = self.findChild(QScrollArea)
        if scroll is None or scroll.widget() is None:
            return
        layout = scroll.widget().layout()
        if not isinstance(layout, QVBoxLayout):
            return
        automatic_box = QGroupBox("自动关联（只读）")
        form = QFormLayout(automatic_box)
        for key, label, source_label in AUTOMATIC_REFERENCE_FIELDS:
            field = fields.get(key)
            value_label = QLabel(
                (
                    "等待分析"
                    if field is None
                    else _automatic_display_value(key, field.value)
                )
            )
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            form.addRow(f"{label} [{source_label}]：", value_label)
        layout.insertWidget(0, automatic_box)


def _display_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    if isinstance(value, (dict, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def _value_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = "" if value is None else str(value)
    return [
        item.strip()
        for item in re.split(r"[、,，;；\n]+", text)
        if item.strip()
    ]


def _automatic_display_value(key: str, value: Any) -> str:
    if key == "image_dimensions" and isinstance(value, dict):
        return f"{value.get('width', '?')} × {value.get('height', '?')}"
    if key == "aspect_ratio":
        try:
            return f"{float(value):.3f}:1"
        except (TypeError, ValueError):
            return _display_value(value)
    if key == "oklab_palette" and isinstance(value, list):
        return " · ".join(
            f"{item.get('hex', '?')} {float(item.get('proportion', 0)) * 100:.1f}%"
            for item in value
            if isinstance(item, dict)
        )
    if key == "luminance_histogram" and isinstance(value, list):
        return f"{len(value)} 个明度区间（结构化数据已保存）"
    if key in {"three_value_ratios", "five_value_ratios"} and isinstance(
        value,
        list,
    ):
        return " / ".join(f"{float(item) * 100:.1f}%" for item in value)
    if key == "hue_distribution" and isinstance(value, dict):
        return (
            f"{value.get('bins_degrees', '?')} 个色相区间"
            "（低饱和像素不参与色相比例）"
        )
    if key == "saturation_distribution" and isinstance(value, dict):
        try:
            return f"平均饱和度 {float(value.get('mean', 0)) * 100:.1f}%"
        except (TypeError, ValueError):
            pass
    return _display_value(value)
