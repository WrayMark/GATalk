from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from scenelens.core.schema_validation import require_valid_json_schema
from scenelens.providers.contracts import StructuredOutputRequest


TRANSLATION_SCHEMA: Mapping[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GATalk Knowledge Translation",
    "type": "object",
    "additionalProperties": False,
    "required": ["translation", "terminology_notes", "uncertainties"],
    "properties": {
        "translation": {"type": "string", "minLength": 1},
        "terminology_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "uncertainties": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


@dataclass(frozen=True)
class KnowledgeTranslation:
    translation: str
    terminology_notes: tuple[str, ...]
    uncertainties: tuple[str, ...]


def create_translation_request(
    source_text: str,
    *,
    target_language: str = "简体中文",
    context: str = "游戏美术、CG、环境设计资料",
    model_id: str | None = None,
    user_initiated: bool = False,
    disclosure_confirmed: bool = False,
) -> StructuredOutputRequest:
    text = source_text.strip()
    if not text:
        raise ValueError("请先填写需要翻译的原文。")
    return StructuredOutputRequest(
        system_instruction=(
            "你是熟悉游戏美术、CG 制作、灯光、材质、关卡设计和技术美术术语的"
            "专业译者。忠实翻译，不补写原文没有的事实；保留软件名、模型名、"
            "数值、快捷键和专有名词。遇到多义术语，在 terminology_notes 中说明"
            "选择；无法确认的内容写入 uncertainties。只输出符合 JSON Schema 的"
            "结构化结果。"
        ),
        payload={
            "module_id": "gatalk.knowledge_base",
            "source_text": text,
            "target_language": target_language,
            "professional_context": context,
        },
        output_schema=TRANSLATION_SCHEMA,
        model_id=model_id,
        user_initiated=user_initiated,
        disclosure_confirmed=disclosure_confirmed,
        timeout_seconds=120.0,
    )


def validate_translation_output(
    output: Mapping[str, Any],
) -> KnowledgeTranslation:
    require_valid_json_schema(output, TRANSLATION_SCHEMA)
    return KnowledgeTranslation(
        translation=str(output["translation"]).strip(),
        terminology_notes=tuple(
            str(item).strip()
            for item in output.get("terminology_notes", ())
            if str(item).strip()
        ),
        uncertainties=tuple(
            str(item).strip()
            for item in output.get("uncertainties", ())
            if str(item).strip()
        ),
    )
