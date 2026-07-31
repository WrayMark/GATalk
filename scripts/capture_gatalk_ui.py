from __future__ import annotations

import argparse
from pathlib import Path

from scenelens.app import create_application
from scenelens.storage.app_settings import AppSettings
from scenelens.ui.settings_dialog import GlobalSettingsDialog
from scenelens.ui.theme import apply_appearance
from scenelens.ui.workspace_hub import WorkspaceHubWindow


def _capture(app, widget, path: Path) -> None:
    widget.show()
    widget.raise_()
    widget.activateWindow()
    handle = widget.window().windowHandle()
    if handle is not None:
        handle.requestActivate()
    widget.repaint()
    app.processEvents()
    if not widget.grab().save(str(path), "PNG"):
        raise RuntimeError(f"无法保存界面截图：{path}")
    widget.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".qa") / "gatalk-ui-smoke",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = create_application([], AppSettings(theme_mode="dark"))

    for mode in ("dark", "light"):
        settings = AppSettings(theme_mode=mode, accent="violet")
        apply_appearance(app, settings)
        hub = WorkspaceHubWindow()
        hub.resize(1440, 860)
        _capture(app, hub, output / f"gatalk-hub-{mode}-0.10.0.png")

    settings = AppSettings(
        theme_mode="dark",
        accent="blue",
        font_size=10,
        density="comfortable",
    )
    apply_appearance(app, settings)
    dialog = GlobalSettingsDialog(settings)
    _capture(app, dialog, output / "gatalk-global-settings-0.10.0.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
