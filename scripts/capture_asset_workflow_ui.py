from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.asset_breakdown.ui.window import AssetBreakdownWindow
from scenelens.storage.app_settings import AppSettings
from scenelens.ui.theme import apply_appearance


def _scene(path: Path) -> None:
    image = Image.new("RGB", (1280, 720), (28, 39, 54))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 500, 1280, 720), fill=(54, 61, 48))
    for x, width, height in ((90, 250, 300), (420, 390, 390), (870, 280, 270)):
        top = 500 - height
        draw.rectangle((x, top, x + width, 520), fill=(118, 87, 56))
        draw.polygon(
            ((x - 20, top + 35), (x + width // 2, top - 90), (x + width + 20, top + 35)),
            fill=(56, 78, 68),
        )
        for window_x in range(x + 32, x + width - 25, 74):
            draw.rectangle((window_x, top + 85, window_x + 30, top + 130), fill=(190, 150, 72))
    image.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    apply_appearance(
        app,
        AppSettings(theme_mode="dark", accent="blue", density="comfortable"),
    )
    with tempfile.TemporaryDirectory(prefix="gatalk-ui-") as temporary:
        root = Path(temporary)
        image_path = root / "山地聚落.png"
        _scene(image_path)
        store = AssetBreakdownStore.create(root / "山地聚落.scenelens-assets", "山地聚落")
        store.import_image(image_path, "main")
        window = AssetBreakdownWindow()
        window._attach_store(store)
        window.resize(1600, 920)
        window.show()
        window.workflow_tabs.setCurrentIndex(0)
        window.manual_tabs.setCurrentIndex(0)
        for _ in range(80):
            app.processEvents()
            if window._loaded is not None:
                break
            QTest.qWait(25)
        app.processEvents()
        if not window.grab().save(str(args.output), "PNG"):
            raise OSError(f"无法保存界面截图：{args.output}")
        window.close()


if __name__ == "__main__":
    main()
