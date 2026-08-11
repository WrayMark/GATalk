from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QFont, QFontDatabase, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox

from scenelens.storage.app_settings import AppSettings, AppSettingsStore
from scenelens.ui.main_window import MainWindow
from scenelens.ui.settings_controller import GlobalSettingsController
from scenelens.ui.theme import apply_appearance, create_brand_icon
from scenelens.ui.workspace_hub import WorkspaceHubWindow
from scenelens.storage.session_guard import ApplicationSessionGuard
from scenelens.ui.diagnostics_dialog import DiagnosticsDialog
from scenelens.ui.global_search import GlobalSearchDialog
from scenelens.ui.task_center import TaskCenterDialog


def _configure_application(
    app: QApplication,
    settings: AppSettings | None = None,
) -> QApplication:
    app.setApplicationName("GATalk")
    app.setApplicationDisplayName("GATalk")
    app.setOrganizationName("GATalk")
    app.setStyle("Fusion")
    # The Windows offscreen Qt plugin used by tests may not enumerate system
    # fonts. Register the installed CJK font as a fallback without bundling it.
    windows_font = Path("C:/Windows/Fonts/msyh.ttc")
    if windows_font.is_file():
        QFontDatabase.addApplicationFont(str(windows_font))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setWindowIcon(create_brand_icon())
    apply_appearance(
        app,
        settings or AppSettingsStore().load(),
    )
    return app


def create_application(
    argv: list[str] | None = None,
    settings: AppSettings | None = None,
) -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return _configure_application(existing, settings)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv if argv is not None else sys.argv)
    return _configure_application(app, settings)


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
    from scenelens.modules.asset_breakdown.reviews import (
        AssetBreakdownContext,
        AssetBreakdownReview,
    )
    from scenelens.modules.asset_breakdown.service import asset_from_ai
    from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
    from scenelens.modules.comparative_study.analysis import (
        build_local_comparison,
    )
    from scenelens.modules.comparative_study.reviews import (
        load_comparative_study_schema,
    )
    from scenelens.modules.registry import create_builtin_workbench_registry
    from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
    from scenelens.modules.knowledge_base.translation import (
        create_translation_request,
        validate_translation_output,
    )
    from scenelens.modules.review_control.storage import ReviewCenterStore

    rgb = np.empty((64, 96, 3), dtype=np.uint8)
    rgb[:, :48] = (35, 75, 120)
    rgb[:, 48:] = (180, 125, 55)
    measurements = measure_image(rgb, palette_colours=8)
    artwork_analysis = analyze_artwork(rgb, measurements)
    comparative = build_local_comparison(
        (
            ("作品一", artwork_analysis.to_dict()),
            ("作品二", artwork_analysis.to_dict()),
        )
    )
    builtins = create_builtin_workbench_registry()
    rendered = render_image(rgb, RenderSettings(mode="grayscale", blur_sigma=1.0))
    if (
        len(measurements.palette) != 2
        or rendered.shape != rgb.shape
        or len(artwork_analysis.spatial_cells) != 9
        or len(comparative["rows"]) != 2
        or load_comparative_study_schema().get("title")
        != "GATalk Comparative Artwork Study"
        or sum(item.level == "platform" for item in builtins.workspaces()) < 2
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
        asset_store = AssetBreakdownStore.create(
            folder / "资产拆分.scenelens-assets",
            "资产拆分烟测",
        )
        asset_source = asset_store.import_image(source, "main")
        asset_reviewer = AssetBreakdownReview()
        asset_request = asset_reviewer.create_request(
            AssetBreakdownContext(
                project_id=asset_store.state.project_id,
                title=asset_store.state.title,
                scene_type="general_environment",
                scene_focus=("建筑", "道具"),
                production_goal="验证完整结构化流程",
                image_metadata={"width": 96, "height": 64},
                supplemental_references=(),
            ),
            (
                ProviderImage(
                    "main_concept",
                    "image/png",
                    image_bytes,
                ),
            ),
            user_initiated=True,
            disclosure_confirmed=True,
        )
        asset_output = asset_reviewer.validate_output(
            provider_registry.get("mock")
            .review(
                asset_request,
                "",
                CancellationToken(),
            )
            .output
        )
        asset_store.add_or_replace_asset(
            asset_from_ai(
                asset_output["assets"][0],
                source_image_id=asset_source.image_id,
            )
        )
        if (
            not asset_store.state.assets
            or asset_store.image_path(asset_source).read_bytes()
            != source.read_bytes()
        ):
            raise RuntimeError("Internal asset-breakdown smoke check failed.")
        asset_store.close()
        knowledge_store = KnowledgeLibraryStore.create(
            folder / "参考资料.scenelens-knowledge",
            "美术参考资料",
        )
        knowledge_item = knowledge_store.import_file(source)
        source_bytes = source.read_bytes()
        excerpt = knowledge_store.create_image_excerpt(
            knowledge_item.item_id,
            (0.0, 0.0, 0.5, 1.0),
            title="烟测局部",
        )
        translation_response = provider_registry.get("mock").generate_structured(
            create_translation_request(
                "Key light",
                user_initiated=True,
                disclosure_confirmed=True,
            ),
            "",
            CancellationToken(),
        )
        translation = validate_translation_output(translation_response.output)
        if (
            source.read_bytes() != source_bytes
            or excerpt.parent_item_id != knowledge_item.item_id
            or not translation.translation
        ):
            raise RuntimeError("Internal knowledge-library smoke check failed.")
        review_center = ReviewCenterStore.open_or_create(
            folder / "review-control"
        )
        review_task = review_center.add_task_from_handoff(
            {
                "title": "烟测审阅任务",
                "source_module_id": "scenelens.artwork_study",
                "source_project_id": artwork_store.state.study_id,
                "source_entity_type": "dimension_study",
                "source_entity_id": "value_structure",
            }
        )
        review_center.add_verification(
            review_task.task_id,
            version_label="烟测版本 v2",
            version_id="smoke-v2",
            state="improved",
            evidence_summary="仅验证版本复查记录。",
        )
        gate = review_center.add_gate(
            name="烟测质量门禁",
            dimension="明度结构",
            acceptance_criteria="验证门禁保存流程。",
            required=True,
        )
        review_center.evaluate_gate(
            gate.gate_id,
            version_label="烟测版本 v2",
            state="pass",
            evidence_summary="仅验证门禁记录。",
        )
        reopened_review = ReviewCenterStore.open_or_create(review_center.root)
        if (
            len(reopened_review.state.verifications) != 1
            or reopened_review.state.gates[0].state != "pass"
        ):
            raise RuntimeError("Internal review-control smoke check failed.")
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
    settings_store = AppSettingsStore()
    app = create_application(settings=settings_store.load())
    settings_controller = GlobalSettingsController(app, settings_store)
    session_guard = ApplicationSessionGuard()
    session_guard.start()
    app.aboutToQuit.connect(session_guard.close)
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        try:
            _run_internal_smoke_check()
        except Exception:
            return 2

    hub = WorkspaceHubWindow()
    settings_controller.register_window(hub, "workspace_hub")
    hub.settings_requested.connect(
        lambda: settings_controller.open_dialog(hub)
    )
    settings_controller.task_center_requested.connect(
        lambda parent: TaskCenterDialog(parent).exec()
    )
    settings_controller.diagnostics_requested.connect(
        lambda parent: DiagnosticsDialog(
            bool(session_guard.previous_unclean_session), parent
        ).exec()
    )
    settings_controller.global_search_requested.connect(
        lambda parent: show_global_search(parent)
    )
    hub.task_center_requested.connect(lambda: TaskCenterDialog(hub).exec())
    hub.diagnostics_requested.connect(
        lambda: DiagnosticsDialog(
            bool(session_guard.previous_unclean_session), hub
        ).exec()
    )
    active_windows: list[QApplication | MainWindow | object] = []
    review_store_holder: list[object] = []

    def close_review_store() -> None:
        if review_store_holder:
            close = getattr(review_store_holder[0], "close", None)
            if callable(close):
                close()

    app.aboutToQuit.connect(close_review_store)

    def review_center_store():
        if not review_store_holder:
            from scenelens.modules.review_control.storage import (
                ReviewCenterStore,
            )

            review_store_holder.append(ReviewCenterStore.open_default())
        return review_store_holder[0]

    def show_hub() -> None:
        for value in tuple(active_windows):
            close = getattr(value, "close", None)
            if callable(close):
                close()
        active_windows.clear()
        hub.show()
        hub.raise_()
        hub.activateWindow()

    def open_workspace(workspace_id: str):
        if workspace_id == "scene_art_control":
            window = MainWindow()
        elif workspace_id == "artwork_study":
            from scenelens.modules.artwork_study.ui.window import (
                ArtworkStudyWindow,
            )

            window = ArtworkStudyWindow()
        elif workspace_id == "asset_breakdown":
            from scenelens.modules.asset_breakdown.ui.window import (
                AssetBreakdownWindow,
            )

            window = AssetBreakdownWindow()
        elif workspace_id == "reference_knowledge":
            from scenelens.modules.knowledge_base.ui.window import (
                KnowledgeBaseWindow,
            )

            window = KnowledgeBaseWindow()
        elif workspace_id == "comparative_study":
            from scenelens.modules.comparative_study.ui.window import (
                ComparativeStudyWindow,
            )

            window = ComparativeStudyWindow()
        elif workspace_id == "review_control":
            from scenelens.modules.review_control.ui.window import (
                ReviewControlWindow,
            )

            window = ReviewControlWindow(review_center_store())
        else:
            return None
        settings_controller.register_window(window, workspace_id)
        search_action = QAction("全局检索", window)
        search_action.setShortcut(QKeySequence("Ctrl+K"))
        search_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        search_action.triggered.connect(
            lambda _checked=False, parent=window: show_global_search(parent)
        )
        window.addAction(search_action)
        window.workspace_home_requested.connect(show_hub)
        if workspace_id == "artwork_study":
            window.asset_breakdown_requested.connect(
                open_asset_breakdown_handoff
            )
        if workspace_id == "reference_knowledge":
            window.comparative_study_requested.connect(
                open_comparative_handoff
            )
        if hasattr(window, "review_task_requested"):
            window.review_task_requested.connect(
                lambda payload, parent=window: submit_review_task(
                    payload, parent
                )
            )
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
        return window

    def open_search_result(record: object) -> None:
        workspace_id = str(getattr(record, "workspace_id", ""))
        window = open_workspace(workspace_id)
        if window is None:
            return
        if workspace_id != "review_control":
            project_root = str(getattr(record, "project_root", ""))
            opener = getattr(window, "open_path", None)
            if workspace_id == "scene_art_control":
                opener = getattr(window, "open_project", None)
            if project_root and callable(opener):
                opener(Path(project_root))
        focus = getattr(window, "focus_entity", None)
        if callable(focus):
            focus(
                str(getattr(record, "entity_type", "")),
                str(getattr(record, "entity_id", "")),
            )

    def show_global_search(parent=None) -> None:
        dialog = GlobalSearchDialog(parent=parent or hub)
        dialog.result_activated.connect(open_search_result)
        dialog.exec()

    def open_asset_breakdown_handoff(handoff: object) -> None:
        window = open_workspace("asset_breakdown")
        if window is not None:
            window.receive_workspace_handoff(handoff)

    def open_comparative_handoff(handoff: object) -> None:
        window = open_workspace("comparative_study")
        if window is not None:
            window.receive_knowledge_handoff(handoff)

    def submit_review_task(payload: object, parent: object) -> None:
        try:
            store = review_center_store()
            values = payload if isinstance(payload, (list, tuple)) else (payload,)
            added = 0
            for value in values:
                if isinstance(value, dict):
                    before = len(store.state.tasks)
                    store.add_task_from_handoff(value)
                    added += len(store.state.tasks) - before
            for window in active_windows:
                refresh = getattr(window, "refresh", None)
                if callable(refresh) and window.__class__.__name__ == "ReviewControlWindow":
                    refresh()
            message = (
                f"已加入审阅中心：{added} 项新任务。"
                if added
                else "该来源已在审阅中心中，不再重复建立。"
            )
            status = getattr(parent, "statusBar", None)
            if callable(status):
                status().showMessage(message, 5000)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                parent if hasattr(parent, "winId") else hub,
                "无法写入审阅中心",
                str(exc),
            )

    hub.workspace_selected.connect(open_workspace)
    hub.global_search_requested.connect(show_global_search)
    hub.show()
    if smoke_test:
        QTimer.singleShot(0, lambda: open_workspace("asset_breakdown"))
        QTimer.singleShot(1_000, app.quit)
    return app.exec()
