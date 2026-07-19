"""Render a deterministic offscreen M0.5 screenshot for visual QA."""

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
from scenelens.ui.main_window import MainWindow


def _create_test_images(folder: Path) -> tuple[Path, Path]:
    width, height = 1280, 720
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]

    reference = np.empty((height, width, 3), dtype=np.uint8)
    reference[..., 0] = np.clip(35 + 150 * x + 25 * y, 0, 255)
    reference[..., 1] = np.clip(65 + 110 * x + 35 * y, 0, 255)
    reference[..., 2] = np.clip(100 + 70 * x + 45 * y, 0, 255)
    reference[390:650, 230:510] = (175, 115, 55)
    reference[290:430, 750:1010] = (70, 105, 80)

    current = np.empty((height, width, 3), dtype=np.uint8)
    current[..., 0] = np.clip(25 + 110 * x + 10 * y, 0, 255)
    current[..., 1] = np.clip(45 + 85 * x + 20 * y, 0, 255)
    current[..., 2] = np.clip(70 + 70 * x + 30 * y, 0, 255)
    current[400:670, 260:560] = (125, 95, 65)
    current[300:455, 760:1040] = (55, 75, 65)

    reference_path = folder / "参考 概念图.png"
    current_path = folder / "当前 UE截图.png"
    Image.fromarray(reference).save(reference_path)
    Image.fromarray(current).save(current_path)
    return reference_path, current_path


def main() -> int:
    output_path = Path(sys.argv[1] if len(sys.argv) > 1 else "m05-smoke.png")
    app = create_application([])
    window = MainWindow()
    window.resize(1500, 900)
    window.show()

    temp_folder = Path(tempfile.mkdtemp(prefix="scenelens-中文-"))
    reference_path, current_path = _create_test_images(temp_folder)
    window._load_path("reference", str(reference_path))
    window._load_path("current", str(current_path))

    def capture_when_ready() -> None:
        ready = all(
            "色板采样" in window.analysis_widgets[role].sample_label.text()
            for role in ("reference", "current")
        )
        if not ready:
            QTimer.singleShot(100, capture_when_ready)
            return
        output_path.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(output_path))
        app.quit()

    QTimer.singleShot(100, capture_when_ready)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

