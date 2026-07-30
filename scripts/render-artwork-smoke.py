"""Render a deterministic offscreen artwork-study screenshot for visual QA."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from scenelens.app import create_application
from scenelens.modules.artwork_study.storage import ArtworkStudyStore
from scenelens.modules.artwork_study.ui.window import ArtworkStudyWindow


def main() -> int:
    output = Path(
        sys.argv[1] if len(sys.argv) > 1 else ".qa/artwork-study-smoke.png"
    )
    temporary = Path(tempfile.mkdtemp(prefix="作品研究-"))
    width, height = 1280, 720
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    rgb[..., 0] = np.clip(25 + 150 * x + 35 * y, 0, 255)
    rgb[..., 1] = np.clip(45 + 105 * x + 20 * y, 0, 255)
    rgb[..., 2] = np.clip(90 + 55 * x + 20 * y, 0, 255)
    rgb[350:690, 170:560] = (130, 82, 45)
    rgb[220:520, 730:1090] = (62, 105, 91)
    image = temporary / "雾中村庄 概念图.png"
    Image.fromarray(rgb).save(image)
    store = ArtworkStudyStore.create(
        temporary / "雾中村庄.scenelens-study",
        "雾中村庄作品研究",
    )
    store.import_image(image)

    app = create_application([])
    window = ArtworkStudyWindow()
    window.resize(1540, 920)
    window.show()
    window._set_store(ArtworkStudyStore.open(store.root))
    window.goal_edit.setPlainText("研究明度、雾与建筑剪影如何组织空间")
    window.context_edit.setPlainText("教学用合成图片，不代表真实作品")

    def capture() -> None:
        if window._local_analysis is None:
            QTimer.singleShot(80, capture)
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(output))
        app.quit()

    QTimer.singleShot(100, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
