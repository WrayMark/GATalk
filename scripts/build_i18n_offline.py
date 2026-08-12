from __future__ import annotations

import json
import shutil
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

from build_i18n_catalogs import (
    GLOSSARY,
    OUTPUT_ROOT,
    extract_patterns,
    extract_strings,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts"
TOOLS = ARTIFACTS / "i18n-tools"
# SentencePiece on Windows cannot reliably open model files through a path
# containing CJK characters. Build tools therefore unpack to the ASCII-safe
# user temp directory; catalogs are still written back to the repository.
MODELS = Path(tempfile.gettempdir()) / "gatalk-i18n-models"
MODEL_ARCHIVES = {
    "en": ARTIFACTS / "translate-zh_en-1_9.argosmodel",
    "fr": ARTIFACTS / "translate-en_fr-1_9.argosmodel",
    "de": ARTIFACTS / "translate-en_de-1_3.argosmodel",
    "ja": ARTIFACTS / "translate-en_ja-1_1.argosmodel",
    "ko": ARTIFACTS / "translate-en_ko-1_1.argosmodel",
    "es": ARTIFACTS / "translate-en_es-1_0.argosmodel",
}
PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}|%\d|%[sdif]|<[^>]+>")


def _prepare_imports() -> None:
    sys.path.insert(0, str(TOOLS))


def _extract_model(archive: Path, name: str) -> Path:
    destination = MODELS / name
    if destination.is_dir():
        return destination
    temporary = MODELS / f".{name}-unpack"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        package.extractall(temporary)
    children = [item for item in temporary.iterdir() if item.is_dir()]
    if len(children) != 1:
        raise RuntimeError(f"Unexpected model package layout: {archive.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(children[0]), destination)
    shutil.rmtree(temporary, ignore_errors=True)
    return destination


class OfflineTranslator:
    def __init__(self, model_path: Path) -> None:
        _prepare_imports()
        import ctranslate2
        import sentencepiece

        self.processor = sentencepiece.SentencePieceProcessor(
            model_file=str(model_path / "sentencepiece.model")
        )
        self.translator = ctranslate2.Translator(
            str(model_path / "model"),
            device="cpu",
            compute_type="int8",
        )

    def translate(self, strings: Iterable[str]) -> list[str]:
        source = list(strings)
        result: list[str] = []
        for start in range(0, len(source), 96):
            batch = source[start : start + 96]
            encoded = [
                self.processor.encode(value, out_type=str) for value in batch
            ]
            translated = self.translator.translate_batch(
                encoded,
                replace_unknowns=True,
                max_batch_size=96,
                batch_type="examples",
                beam_size=4,
            )
            result.extend(
                self.processor.decode_pieces(item.hypotheses[0])
                .replace("▁", " ")
                .replace("_", " ")
                .strip()
                for item in translated
            )
            print(f"{min(start + len(batch), len(source))}/{len(source)}")
        return result


def _write_catalog(locale: str, source: list[str], target: list[str]) -> None:
    _write_catalog_with_patterns(locale, source, target, [], [])


def _write_catalog_with_patterns(
    locale: str,
    source: list[str],
    target: list[str],
    source_patterns: list[str],
    target_patterns: list[str],
) -> None:
    catalog = {
        original: (
            translated
            if translated
            and sorted(PLACEHOLDER_RE.findall(original))
            == sorted(PLACEHOLDER_RE.findall(translated))
            else original
        )
        for original, translated in zip(source, target, strict=True)
    }
    catalog.update(GLOSSARY.get(locale, {}))
    translated_count = sum(
        bool(catalog.get(item, "").strip()) for item in source
    )
    pattern_catalog = [
        {"source": original, "target": translated}
        for original, translated in zip(
            source_patterns,
            target_patterns,
            strict=True,
        )
        if sorted(PLACEHOLDER_RE.findall(original))
        == sorted(PLACEHOLDER_RE.findall(translated))
    ]
    payload = {
        "locale": locale,
        "source_locale": "zh-CN",
        "catalog_version": 1,
        "translation_stage": "machine_draft",
        "status": "preview",
        "translated_count": translated_count + len(pattern_catalog),
        "reviewed_count": sum(
            item in GLOSSARY.get(locale, {}) for item in source
        ),
        "total_count": len(source) + len(source_patterns),
        "strings": catalog,
        "patterns": pattern_catalog,
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / f"{locale}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _translate_patterns(
    translator: OfflineTranslator,
    patterns: list[str],
) -> list[str]:
    split = [re.split(r"(\{\d+\})", value) for value in patterns]
    literals = sorted(
        {
            part
            for parts in split
            for part in parts
            if part and not re.fullmatch(r"\{\d+\}", part)
        }
    )
    translated = translator.translate(literals)
    lookup = dict(zip(literals, translated, strict=True))
    return [
        "".join(
            part if re.fullmatch(r"\{\d+\}", part) else lookup.get(part, part)
            for part in parts
        )
        for parts in split
    ]


def build_traditional_chinese(source: list[str], patterns: list[str]) -> None:
    _prepare_imports()
    from opencc import OpenCC

    converter = OpenCC("s2twp")
    converted = [converter.convert(value) for value in source]
    converted_patterns = [converter.convert(value) for value in patterns]
    _write_catalog_with_patterns(
        "zh-TW", source, converted, patterns, converted_patterns
    )


def build_english(
    source: list[str], patterns: list[str]
) -> tuple[list[str], list[str]]:
    model = _extract_model(MODEL_ARCHIVES["en"], "zh_en")
    translator = OfflineTranslator(model)
    translated = translator.translate(source)
    translated_patterns = _translate_patterns(translator, patterns)
    _write_catalog_with_patterns(
        "en", source, translated, patterns, translated_patterns
    )
    return (
        [GLOSSARY.get("en", {}).get(item, value) for item, value in zip(source, translated)],
        translated_patterns,
    )


def build_from_english(
    locale: str,
    source: list[str],
    patterns: list[str],
    english: list[str],
    english_patterns: list[str],
) -> None:
    archive = MODEL_ARCHIVES[locale]
    if not zipfile.is_zipfile(archive):
        raise RuntimeError(f"Model archive is incomplete: {archive.name}")
    model = _extract_model(archive, f"en_{locale}")
    translator = OfflineTranslator(model)
    translated = translator.translate(english)
    translated_patterns = _translate_patterns(translator, english_patterns)
    _write_catalog_with_patterns(
        locale, source, translated, patterns, translated_patterns
    )


def main() -> int:
    source = extract_strings()
    patterns = extract_patterns()
    requested = tuple(sys.argv[1:]) or ("zh-TW", "en", "ja", "fr")
    english: list[str] | None = None
    english_patterns: list[str] | None = None
    if "zh-TW" in requested:
        build_traditional_chinese(source, patterns)
    if any(locale != "zh-TW" for locale in requested):
        english, english_patterns = build_english(source, patterns)
    for locale in requested:
        if locale in {"zh-TW", "en"}:
            continue
        if locale not in {"ja", "fr", "de", "es", "ko"}:
            raise ValueError(f"Unsupported locale: {locale}")
        build_from_english(
            locale,
            source,
            patterns,
            english or [],
            english_patterns or [],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
