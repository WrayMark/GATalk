from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QApplication

from scenelens.ui.main_window import MainWindow
from scenelens.ui.workspace_hub import WorkspaceHubWindow


APP_STYLESHEET = """
QWidget {
    background: #202124;
    color: #E8EAED;
    font-size: 10pt;
}
QMainWindow, QToolBar, QStatusBar {
    background: #202124;
}
QToolBar {
    border-bottom: 1px solid #3C4043;
    spacing: 5px;
    padding: 4px;
}
QPushButton, QComboBox {
    background: #303134;
    border: 1px solid #5F6368;
    border-radius: 4px;
    padding: 5px 8px;
}
QPushButton:hover, QComboBox:hover {
    border-color: #8AB4F8;
}
QPushButton:disabled {
    color: #80868B;
    border-color: #3C4043;
}
QComboBox QAbstractItemView {
    background: #303134;
    selection-background-color: #3C5F8A;
}
QTabWidget::pane {
    border: 1px solid #3C4043;
}
QTabBar::tab {
    background: #292A2D;
    padding: 7px 10px;
    border: 1px solid #3C4043;
}
QTabBar::tab:selected {
    background: #3C4043;
}
QSplitter::handle {
    background: #3C4043;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #5F6368;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: #8AB4F8;
}
QProgressBar {
    border: 1px solid #5F6368;
    border-radius: 3px;
    text-align: center;
}
"""


def _configure_application(app: QApplication) -> QApplication:
    app.setApplicationName("SceneLens")
    app.setOrganizationName("SceneLens")
    app.setStyle("Fusion")
    # The Windows offscreen Qt plugin used by tests may not enumerate system
    # fonts. Register the installed CJK font as a fallback without bundling it.
    windows_font = Path("C:/Windows/Fonts/msyh.ttc")
    if windows_font.is_file():
        QFontDatabase.addApplicationFont(str(windows_font))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(APP_STYLESHEET)
    return app


def create_application(argv: list[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return _configure_application(existing)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv if argv is not None else sys.argv)
    return _configure_application(app)


def _run_internal_smoke_check() -> None:
    from io import BytesIO

    from scenelens.analysis.grading import (
        SafeGradeRecipe,
        apply_safe_grade,
    )
    from scenelens.analysis.artwork_study import analyze_artwork
    from scenelens.analysis.match_profile import build_match_profile
    from scenelens.analysis.preview_validation import (
        validate_concept_preview,
    )
    from scenelens.core.analyzers import AnalyzerRequest
    from scenelens.core.domain import AIConceptPreview
    from scenelens.analysis.models import RenderSettings
    from scenelens.analysis.pipeline import measure_image, render_image
    from scenelens.modules.visual_review.analyzers import PairedRegionAnalyzer
    from scenelens.modules.visual_review.composition_guides import (
        composition_guide,
    )
    from scenelens.modules.visual_review.review_evidence import (
        build_review_evidence_digest,
    )
    from scenelens.modules.visual_review.region_results import (
        paired_region_to_payload,
    )
    from scenelens.modules.visual_review.region_store import RegionStore
    from scenelens.modules.visual_review.regions import NormalizedRect
    from scenelens.storage.project_store import ProjectStore
    from scenelens.modules.visual_review.review_coordinator import (
        ReviewCoordinator,
        ReviewRunOptions,
    )
    from scenelens.modules.visual_review.reviews import (
        DeepArtDirectorReview,
        ReviewContext,
    )
    from scenelens.providers.contracts import (
        CancellationToken,
        ImageEditRequest,
        ProviderImage,
    )
    from scenelens.providers.mock import MockProvider
    from scenelens.providers.registry import ProviderRegistry
    from scenelens.storage.project_store import utc_now
    from scenelens.storage.workbench_store import WorkbenchStore
    from scenelens.modules.visual_review import MODULE_ID
    from scenelens.modules.artwork_study.reviews import (
        ArtworkMasterStudyReview,
        ArtworkStudyContext,
    )
    from scenelens.modules.artwork_study.storage import ArtworkStudyStore

    rgb = np.empty((64, 96, 3), dtype=np.uint8)
    rgb[:, :48] = (35, 75, 120)
    rgb[:, 48:] = (180, 125, 55)
    measurements = measure_image(rgb, palette_colours=8)
    artwork_analysis = analyze_artwork(rgb, measurements)
    rendered = render_image(rgb, RenderSettings(mode="grayscale", blur_sigma=1.0))
    if (
        len(measurements.palette) != 2
        or rendered.shape != rgb.shape
        or len(artwork_analysis.spatial_cells) != 9
    ):
        raise RuntimeError("Internal image-analysis smoke check failed.")
    original = rgb.copy()
    graded = apply_safe_grade(
        rgb,
        SafeGradeRecipe(
            exposure_stops=0.2,
            strength_percent=25,
        ),
    )
    match = build_match_profile(rgb, graded)
    preview_validation = validate_concept_preview(rgb, graded, rgb)
    if (
        np.array_equal(graded, rgb)
        or not np.array_equal(original, rgb)
        or match.estimated_match is None
        or preview_validation.structure_drift < 0.0
    ):
        raise RuntimeError("Internal M3 local optimization smoke check failed.")

    provider_registry = ProviderRegistry()
    provider_registry.register(MockProvider())
    deep_reviewer = DeepArtDirectorReview()
    coordinator = ReviewCoordinator(
        provider_registry,
        {"deep_art_director_review": deep_reviewer},
    )
    evidence_digest = build_review_evidence_digest(
        rgb,
        rgb,
        low_threshold=1.0 / 3.0,
        high_threshold=2.0 / 3.0,
        measurements={
            "reference": measurements,
            "current": measurements,
        },
    )
    review = coordinator.run(
        options=ReviewRunOptions("deep_art_director_review", "mock"),
        context=ReviewContext(
            project_id="smoke",
            shot_id="smoke",
            version_id="smoke",
            creative_intent={},
            reference_visual_brief={},
            global_measurements={},
            local_evidence_digest=evidence_digest,
        ),
        images=(
            ProviderImage("reference", "image/png", b"smoke-reference"),
            ProviderImage("current", "image/png", b"smoke-current"),
        ),
        current_rgb=rgb,
        reference_rgb=rgb,
        credentials={},
        cancellation=CancellationToken(),
    )
    thirds = composition_guide("thirds")
    if (
        review.output.get("reviewer_id")
        != "deep_art_director_review"
        or len(review.output.get("dimension_reviews", [])) != 8
        or thirds is None
        or len(thirds.lines) != 4
    ):
        raise RuntimeError("Internal offline AI review smoke check failed.")
    image_buffer = BytesIO()
    Image.fromarray(rgb).save(image_buffer, format="PNG")
    image_bytes = image_buffer.getvalue()
    concept_response = coordinator.execution.run_image_edit(
        provider_registry.get("mock"),
        ImageEditRequest(
            instruction={
                "output_type": "AIConceptPreview",
                "edit_mode": "lighting_only",
            },
            images=(
                ProviderImage("reference", "image/png", image_bytes),
                ProviderImage("current", "image/png", image_bytes),
            ),
            change_budget=25,
            user_initiated=True,
            disclosure_confirmed=True,
        ),
        "",
        CancellationToken(),
    )
    if concept_response.image_bytes != image_bytes:
        raise RuntimeError("Internal M3 image-edit Mock smoke check failed.")
    artwork_reviewer = ArtworkMasterStudyReview()
    artwork_request = artwork_reviewer.create_request(
        ArtworkStudyContext(
            study_id="smoke-study",
            title="作品研究烟测",
            work_type="environment_concept",
            study_goal="验证结构化研究流程",
            known_context="",
            image_metadata={"width": 96, "height": 64},
            local_evidence=artwork_analysis.to_dict(),
        ),
        (ProviderImage("artwork", "image/png", image_bytes),),
        user_initiated=True,
        disclosure_confirmed=True,
    )
    artwork_output = provider_registry.get("mock").review(
        artwork_request,
        "",
        CancellationToken(),
    )
    validated_artwork = artwork_reviewer.validate_output(
        artwork_output.output
    )
    if len(validated_artwork["dimension_studies"]) != 12:
        raise RuntimeError("Internal artwork-study review smoke check failed.")
    coordinator.close()

    with tempfile.TemporaryDirectory(prefix="scenelens-smoke-中文-") as temporary:
        folder = Path(temporary)
        source = folder / "输入 图片.png"
        Image.fromarray(rgb).save(source)
        artwork_store = ArtworkStudyStore.create(
            folder / "作品研究.scenelens-study",
            "作品研究烟测",
        )
        artwork_state = artwork_store.import_image(source)
        if (
            not artwork_state.image_sha256
            or artwork_store.image_path() is None
            or artwork_store.image_path().read_bytes() != source.read_bytes()
        ):
            raise RuntimeError("Internal artwork-study storage smoke check failed.")
        store = ProjectStore.create(
            folder / "烟测 项目.scenelens",
            "烟测项目",
        )
        shot = store.create_shot("固定机位")
        reference = store.import_reference(shot.id, source)
        version = store.add_version(shot.id, source)
        store.save_measurements(version.asset_id, measurements)
        store.close()
        reopened = ProjectStore.open(store.root)
        if (
            reopened.get_shot(shot.id).reference_asset_id != reference.id
            or reopened.get_version(version.id).asset_id != reference.id
            or reopened.load_measurements(version.asset_id) is None
        ):
            raise RuntimeError("Internal project-storage smoke check failed.")
        region_store = RegionStore(reopened)
        reference_region = region_store.create_region(
            shot.id,
            "reference",
            None,
            "主体参考",
            "主体",
            NormalizedRect(0.0, 0.0, 0.5, 1.0),
        )
        current_region = region_store.create_region(
            shot.id,
            "current",
            version.id,
            "主体当前",
            "主体",
            NormalizedRect(0.0, 0.0, 0.5, 1.0),
        )
        pair = region_store.create_pair(
            reference_region.id,
            current_region.id,
            "主体",
            "主体",
        )
        analyzer = PairedRegionAnalyzer()
        parameters = analyzer.default_parameters(max_colour_samples=2_000)
        request = AnalyzerRequest(
            inputs={
                "reference_rgb": rgb,
                "current_rgb": rgb,
                "reference_rect": (0.0, 0.0, 0.5, 1.0),
                "current_rect": (0.0, 0.0, 0.5, 1.0),
                "shared_palette_centres": np.asarray(
                    [item.oklab for item in measurements.palette]
                ),
            },
            input_hashes={
                "reference_image": reference.sha256,
                "current_image": reference.sha256,
                "reference_geometry": "smoke-reference",
                "current_geometry": "smoke-current",
                "shared_palette": "smoke-shared",
            },
            parameters=parameters,
        )
        region_result = analyzer.run(request)
        cache_key = analyzer.cache_key(request)
        region_store.save_analysis(
            pair.id,
            analyzer_id=analyzer.descriptor.analyzer_id,
            analyzer_version=analyzer.descriptor.version,
            reference_image_hash=reference.sha256,
            current_image_hash=reference.sha256,
            reference_region_geometry=reference_region.normalized_rect.to_dict(),
            current_region_geometry=current_region.normalized_rect.to_dict(),
            shared_palette_cache_key="smoke-shared",
            parameters=parameters,
            cache_key=cache_key,
            result=paired_region_to_payload(region_result),
        )
        if region_store.load_analysis(cache_key) is None:
            raise RuntimeError("Internal paired-region smoke check failed.")
        preview_id = "smoke-ai-concept-preview"
        preview_relative = (
            f"artifacts/ai_previews/{preview_id}.png"
        )
        preview_path = reopened.root / preview_relative
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(graded).save(preview_path)
        WorkbenchStore(reopened).save_ai_concept_preview(
            AIConceptPreview(
                id=preview_id,
                module_id=MODULE_ID,
                shot_id=shot.id,
                source_version_id=version.id,
                provider_id="mock",
                model_id="mock-image-v1",
                relative_path=preview_relative,
                input_hashes={
                    "reference": reference.sha256,
                    "current": reference.sha256,
                },
                instruction={
                    "output_type": "AIConceptPreview",
                    "edit_mode": "lighting_only",
                },
                protection_constraints={
                    "preserve_geometry": True,
                },
                validation_metrics=preview_validation.to_dict(),
                preview_status=preview_validation.status,
                created_at=utc_now(),
            )
        )
        if (
            len(
                WorkbenchStore(reopened).list_ai_concept_previews(
                    MODULE_ID,
                    shot_id=shot.id,
                    source_version_id=version.id,
                )
            )
            != 1
            or len(reopened.list_versions(shot.id)) != 1
        ):
            raise RuntimeError(
                "Internal AIConceptPreview isolation smoke check failed."
            )
        reopened.close()


def main() -> int:
    app = create_application()
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        try:
            _run_internal_smoke_check()
        except Exception:
            return 2

    hub = WorkspaceHubWindow()
    active_windows: list[QApplication | MainWindow | object] = []

    def show_hub() -> None:
        for value in tuple(active_windows):
            close = getattr(value, "close", None)
            if callable(close):
                close()
        active_windows.clear()
        hub.show()
        hub.raise_()
        hub.activateWindow()

    def open_workspace(workspace_id: str) -> None:
        if workspace_id == "scene_art_control":
            window = MainWindow()
        elif workspace_id == "artwork_study":
            from scenelens.modules.artwork_study.ui.window import (
                ArtworkStudyWindow,
            )

            window = ArtworkStudyWindow()
        else:
            return
        window.workspace_home_requested.connect(show_hub)
        window.destroyed.connect(
            lambda *_args, value=window: (
                active_windows.remove(value)
                if value in active_windows
                else None
            )
        )
        active_windows.append(window)
        hub.hide()
        window.show()

    hub.workspace_selected.connect(open_workspace)
    hub.show()
    if smoke_test:
        QTimer.singleShot(0, lambda: open_workspace("artwork_study"))
        QTimer.singleShot(1_000, app.quit)
    return app.exec()
