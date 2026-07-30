from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PySide6.QtWidgets import QApplication

from scenelens.analysis.asset_masks import normalized_rect_to_pixels
from scenelens.imaging.loader import load_image
from scenelens.modules.asset_breakdown.artifacts import (
    asset_crop_png,
    make_asset_board,
)
from scenelens.modules.asset_breakdown.models import (
    AssetItem,
    AutomaticAssetRun,
    GenerationRecord,
)
from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.asset_breakdown.ui.window import AssetBreakdownWindow
from scenelens.storage.project_store import utc_now


def main() -> int:
    validation = PROJECT_ROOT / ".qa" / "asset-breakdown-validation"
    source_project = validation / "real-cyberpunk.scenelens-assets"
    source_data = json.loads(
        (source_project / "asset_project.json").read_text(encoding="utf-8")
    )
    source_record = source_data["state"]["source_images"][0]
    source_image = source_project / source_record["relative_path"]
    source_assets = tuple(
        AssetItem.from_dict(item)
        for item in source_data["state"]["assets"][:6]
    )
    loaded = load_image(source_image)
    screenshot = (
        PROJECT_ROOT
        / ".qa"
        / "automatic-asset-board-smoke"
        / "automatic-asset-board-0.8.0.png"
    )
    screenshot.parent.mkdir(parents=True, exist_ok=True)

    application = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="scenelens-auto-board-") as temporary:
        store = AssetBreakdownStore.create(
            Path(temporary) / "smoke.scenelens-assets",
            "赛博城市全自动资产板",
        )
        main_image = store.import_image(source_image, "main")
        run_id = "automatic-smoke"
        assets = tuple(
            replace(
                item,
                source_image_id=main_image.image_id,
                mask_relative_path="",
                mask_method="",
            )
            for item in source_assets
        )
        generations = []
        entries = []
        for asset in assets:
            mask = np.zeros(loaded.rgb.shape[:2], dtype=np.uint8)
            left, top, width, height = normalized_rect_to_pixels(
                asset.normalized_rect,
                loaded.rgb.shape,
            )
            mask[top : top + height, left : left + width] = 255
            method = "rectangle_proxy_v1"
            relative = (
                f"artifacts/automatic/{run_id}/assets/"
                f"{asset.asset_id}.png"
            )
            path = store.save_artifact(
                relative,
                asset_crop_png(loaded.rgb, asset, mask),
            )
            entries.append((asset, path))
            generations.append(
                GenerationRecord(
                    generation_id=f"smoke-{asset.asset_id}",
                    asset_id=asset.asset_id,
                    output_kind="isolated_concept",
                    source_image_sha256=main_image.sha256,
                    source_rect=asset.normalized_rect,
                    provider_id="offline_smoke",
                    model_id="local-visible-crop",
                    parameters={"purpose": "ui_smoke_only"},
                    relative_path=relative,
                    status="completed",
                    created_at=utc_now(),
                )
            )
        board_relative = (
            f"artifacts/automatic/{run_id}/asset_board.png"
        )
        store.save_artifact(
            board_relative,
            make_asset_board(
                entries,
                title="赛博城市 — 全自动资产板界面烟测",
            ),
        )
        store.append_automatic_run(
            AutomaticAssetRun(
                run_id=run_id,
                status="completed",
                source_image_sha256=main_image.sha256,
                vision_provider_id="offline_smoke",
                vision_model_id="local-structure-fixture",
                image_provider_id="offline_smoke",
                image_model_id="local-visible-crop",
                output_kind="isolated_concept",
                asset_limit=len(assets),
                assets=assets,
                generations=tuple(generations),
                board_relative_path=board_relative,
                created_at=utc_now(),
            )
        )
        window = AssetBreakdownWindow()
        window._attach_store(store)
        window.workflow_tabs.setCurrentIndex(1)
        window.show()
        deadline = time.monotonic() + 5.0
        while window._loaded is None and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.02)
        application.processEvents()
        if not window.grab().save(str(screenshot), "PNG"):
            window.close()
            return 2
        window.close()
    print(screenshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
