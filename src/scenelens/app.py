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
    from scenelens.analysis.models import RenderSettings
    from scenelens.analysis.pipeline import measure_image, render_image
    from scenelens.storage.project_store import ProjectStore

    rgb = np.empty((64, 96, 3), dtype=np.uint8)
    rgb[:, :48] = (35, 75, 120)
    rgb[:, 48:] = (180, 125, 55)
    measurements = measure_image(rgb, palette_colours=8)
    rendered = render_image(rgb, RenderSettings(mode="grayscale", blur_sigma=1.0))
    if len(measurements.palette) != 2 or rendered.shape != rgb.shape:
        raise RuntimeError("Internal image-analysis smoke check failed.")

    with tempfile.TemporaryDirectory(prefix="scenelens-smoke-中文-") as temporary:
        folder = Path(temporary)
        source = folder / "输入 图片.png"
        Image.fromarray(rgb).save(source)
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
        reopened.close()


def main() -> int:
    app = create_application()
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        try:
            _run_internal_smoke_check()
        except Exception:
            return 2

    window = MainWindow()
    window.show()
    if smoke_test:
        QTimer.singleShot(1_000, app.quit)
    return app.exec()
