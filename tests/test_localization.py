from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from scenelens.core.locales import (
    current_locale,
    normalize_locale,
    output_language_name,
)
from scenelens.providers.contracts import (
    CancellationToken,
    ProviderCapability,
    ProviderManifest,
    ProviderResponse,
    VisionReviewRequest,
)
from scenelens.providers.execution import ProviderExecutionService
from scenelens.storage.app_settings import AppSettings, AppSettingsStore
from scenelens.ui.localization import configure_localization
from scenelens.ui.settings_dialog import GlobalSettingsDialog


def test_language_setting_round_trips_and_old_settings_default_to_chinese(tmp_path):
    path = tmp_path / "settings.json"
    store = AppSettingsStore(path)
    store.save(AppSettings(ui_language="ja", theme_mode="dark"))

    restored = store.load()
    assert restored.ui_language == "ja"
    assert restored.theme_mode == "dark"

    path.write_text(
        '{"format_version": 1, "theme_mode": "light"}',
        encoding="utf-8",
    )
    assert store.load().ui_language == "zh-CN"


def test_locale_normalization_covers_supported_system_variants():
    assert normalize_locale("zh_Hant_TW") == "zh-TW"
    assert normalize_locale("en_US") == "en"
    assert normalize_locale("ja_JP") == "ja"
    assert normalize_locale("unknown") == "zh-CN"


def test_language_switch_translates_existing_widgets_and_can_restore_source(qtbot):
    manager = configure_localization(QApplication.instance(), "zh-CN")
    window = QWidget()
    label = QLabel("全局设置", window)
    plain_text = QPlainTextEdit(window)
    plain_text.setPlaceholderText("等待双图分析")
    table = QTableWidget(0, 1, window)
    table.setHorizontalHeaderItem(0, QTableWidgetItem("参考图"))
    qtbot.addWidget(window)

    manager.set_locale("en")
    manager.translate_tree(window)
    assert label.text() == "Settings"
    assert plain_text.placeholderText() == "Waiting for paired analysis"
    assert table.horizontalHeaderItem(0).text() == "Reference"

    manager.set_locale("zh-CN")
    manager.translate_tree(window)
    assert label.text() == "全局设置"
    assert plain_text.placeholderText() == "等待双图分析"
    assert table.horizontalHeaderItem(0).text() == "参考图"


@dataclass
class CapturingProvider:
    def __post_init__(self):
        self.request = None
        self.manifest = ProviderManifest(
            provider_id="capture",
            display_name="Capture",
            api_style="test",
            base_url="",
            capabilities=(ProviderCapability.VISION_REVIEW,),
            default_models={"vision_review": "test"},
            credential_target="GATalk/test",
        )

    def review(self, request, _credential, _cancellation):
        self.request = request
        return ProviderResponse("capture", "test", {"ok": True})


def test_new_ai_requests_follow_current_ui_language(qtbot):
    manager = configure_localization(QApplication.instance(), "fr")
    provider = CapturingProvider()
    service = ProviderExecutionService(sleep=lambda _delay: None)
    request = VisionReviewRequest(
        system_instruction="Return JSON.",
        payload={},
        images=(),
        output_schema={"type": "object"},
        user_initiated=True,
        disclosure_confirmed=True,
    )
    try:
        service.run_review(provider, request, "", CancellationToken())
    finally:
        service.close()
        manager.set_locale("zh-CN")

    assert current_locale() == "zh-CN"
    assert output_language_name("fr") == "French"
    assert provider.request.payload["output_language"] == "fr"
    assert "locale fr" in provider.request.system_instruction


def test_settings_only_exposes_languages_with_usable_catalog_coverage(qtbot):
    manager = configure_localization(QApplication.instance(), "zh-CN")
    dialog = GlobalSettingsDialog(AppSettings())
    qtbot.addWidget(dialog)
    locales = {
        dialog.language_combo.itemData(index)
        for index in range(dialog.language_combo.count())
    }
    manager.set_locale("zh-CN")

    assert locales == {"system", "zh-CN", "zh-TW", "en", "ja", "fr"}
    assert "de" not in locales


def test_professional_navigation_and_review_terms_are_curated_in_every_locale():
    manager = configure_localization(QApplication.instance(), "zh-CN")
    expected = {
        "zh-TW": {
            "←  工作台首页": "←  工作台首頁",
            "制作任务与验收中心": "製作工作與驗收中心",
            "综合美术审阅": "綜合美術審閱",
            "作品解读": "作品解讀",
            "运行状态": "執行狀態",
            "分析框架": "分析架構",
        },
        "en": {
            "←  工作台首页": "←  Workbench Home",
            "制作任务与验收中心": "Production Tasks & Acceptance",
            "综合美术审阅": "Comprehensive Art Review",
            "作品解读": "Artwork Interpretation",
            "运行状态": "Activity",
            "分析框架": "Analysis Framework",
        },
        "ja": {
            "←  工作台首页": "←  ワークベンチ ホーム",
            "制作任务与验收中心": "制作タスクと受入確認",
            "综合美术审阅": "総合アートレビュー",
            "作品解读": "作品解説",
            "运行状态": "実行状況",
            "分析框架": "分析フレームワーク",
        },
        "fr": {
            "←  工作台首页": "←  Accueil des espaces de travail",
            "制作任务与验收中心": "Tâches de production et validation",
            "综合美术审阅": "Revue artistique complète",
            "作品解读": "Lecture de l’œuvre",
            "运行状态": "Activité",
            "分析框架": "Cadre d’analyse",
        },
    }
    try:
        for locale, values in expected.items():
            manager.set_locale(locale)
            for source, target in values.items():
                assert manager.translate_text(source) == target
    finally:
        manager.set_locale("zh-CN")
