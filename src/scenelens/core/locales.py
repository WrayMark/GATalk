from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageDescriptor:
    locale: str
    native_name: str
    ai_name: str
    release_stage: str = "preview"


SUPPORTED_LANGUAGES = (
    LanguageDescriptor("zh-CN", "简体中文", "Simplified Chinese", "source"),
    LanguageDescriptor("zh-TW", "繁體中文", "Traditional Chinese"),
    LanguageDescriptor("en", "English", "English"),
    LanguageDescriptor("ja", "日本語", "Japanese"),
    LanguageDescriptor("fr", "Français", "French"),
)
SUPPORTED_LOCALES = frozenset(item.locale for item in SUPPORTED_LANGUAGES)
SOURCE_LOCALE = "zh-CN"
_current_locale = SOURCE_LOCALE
NATIVE_PREVIEW_LABELS = {
    "zh-TW": "預覽",
    "en": "Preview",
    "ja": "プレビュー",
    "fr": "Aperçu",
}
SYSTEM_LANGUAGE_LABELS = {
    "zh-CN": "跟随系统 / System",
    "zh-TW": "跟隨系統 / System",
    "en": "Follow system",
    "ja": "システム設定に従う",
    "fr": "Suivre la langue du système",
}


def normalize_locale(value: str | None) -> str:
    text = str(value or "").strip().replace("_", "-")
    lowered = text.lower()
    if lowered in {"zh", "zh-cn", "zh-sg", "zh-hans", "zh-hans-cn"}:
        return "zh-CN"
    if lowered in {"zh-tw", "zh-hk", "zh-mo", "zh-hant", "zh-hant-tw"}:
        return "zh-TW"
    language = lowered.split("-", 1)[0]
    for locale in SUPPORTED_LOCALES:
        if locale.lower() == lowered or locale.lower() == language:
            return locale
    return SOURCE_LOCALE


def set_current_locale(locale: str) -> None:
    global _current_locale
    _current_locale = normalize_locale(locale)


def current_locale() -> str:
    return _current_locale


def output_language_name(locale: str | None = None) -> str:
    resolved = normalize_locale(locale or _current_locale)
    return next(
        (item.ai_name for item in SUPPORTED_LANGUAGES if item.locale == resolved),
        "Simplified Chinese",
    )


def output_language_instruction(locale: str | None = None) -> str:
    resolved = normalize_locale(locale or _current_locale)
    name = output_language_name(resolved)
    return (
        "\n\n[FINAL OUTPUT LANGUAGE]\n"
        f"Write every user-visible natural-language value in {name} "
        f"(locale {resolved}). Keep JSON keys, schema IDs, enum values, model IDs, "
        "file hashes, hexadecimal colors, Oklab, UE5, P10 and other required "
        "technical identifiers unchanged. This final language instruction "
        "overrides any earlier default-language wording. Use concise, professional "
        "game-art terminology; do not translate user-authored text or proper names."
    )
