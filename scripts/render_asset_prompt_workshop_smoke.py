from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from scenelens.modules.asset_breakdown.models import (
    AssetPromptSession,
    PromptMessage,
    PromptRevision,
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
    screenshot = (
        PROJECT_ROOT
        / ".qa"
        / "asset-prompt-workshop-smoke"
        / "asset-prompt-workshop-0.9.0.png"
    )
    screenshot.parent.mkdir(parents=True, exist_ok=True)

    application = QApplication.instance() or QApplication([])
    for font_path in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ):
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    application.setFont(QFont("Microsoft YaHei UI", 9))

    with TemporaryDirectory(prefix="scenelens-prompt-workshop-") as temporary:
        store = AssetBreakdownStore.create(
            Path(temporary) / "smoke.scenelens-assets",
            "赛博城市资产拆分提示语",
        )
        main_image = store.import_image(source_image, "main")
        now = utc_now()
        revision = PromptRevision(
            revision_id="prompt-smoke-r1",
            origin="ai",
            title="雨夜赛博街区资产展示板",
            target_tool="nano_banana",
            analysis_summary=(
                "画面由高层建筑外壳、临街商业模块、交通与人物道具、"
                "湿地表材质及远景体积雾共同构成。"
            ),
            prompt_zh=(
                "以输入原画为唯一设计依据，生成一张专业游戏环境资产拆分"
                "展示板。按建筑模块、店铺构件、街道道具、交通元素、材质"
                "与远景氛围分组；所有资产彼此分离、完整可见、保持原画的"
                "绿色雨夜赛博设计语言，使用中性深灰背景和清晰中文标签。"
            ),
            prompt_en=(
                "Create a professional game-environment asset breakdown board "
                "based only on the supplied concept art. Group modular "
                "architecture, storefront parts, street props, vehicles, "
                "materials, and distant atmosphere on a neutral dark backdrop."
            ),
            negative_prompt=(
                "不要改变场景身份；不要合并不同资产；不要裁切；"
                "不要把不可见背面表现为确定设计。"
            ),
            constraints=(
                "保持原画绿色雨夜赛博设计语言",
                "资产彼此分离且轮廓完整",
                "不可见结构仅作保守补全",
            ),
            asset_groups=(
                {
                    "name": "临街建筑模块",
                    "category": "建筑／模块构件",
                    "visible_evidence": "左侧连续立面、雨棚、窗格和招牌。",
                    "uncertainty": "背面与内部结构不可见。",
                    "prompt_fragment_zh": "模块化临街建筑套件。",
                    "prompt_fragment_en": "modular street-front building kit",
                },
                {
                    "name": "街道道具与交通",
                    "category": "道具／载具",
                    "visible_evidence": "车辆、护栏、灯箱和路面引导标识。",
                    "uncertainty": "小型道具数量以可见项为准。",
                    "prompt_fragment_zh": "街道道具和交通元素分组。",
                    "prompt_fragment_en": "grouped street props and vehicles",
                },
            ),
            change_summary="已生成第一版，可继续要求减少道具或强化模块化。",
            provider_id="offline_smoke",
            model_id="mock-vision-v1",
            created_at=now,
        )
        session = AssetPromptSession(
            session_id="prompt-smoke",
            title=revision.title,
            source_image_sha256=main_image.sha256,
            target_tool=revision.target_tool,
            revisions=(revision,),
            messages=(
                PromptMessage(
                    message_id="prompt-smoke-message",
                    role="assistant",
                    content=revision.change_summary,
                    created_at=now,
                ),
            ),
            created_at=now,
            updated_at=now,
        )
        store.add_or_replace_prompt_session(session)
        window = AssetBreakdownWindow()
        window._attach_store(store)
        window.workflow_tabs.setCurrentIndex(2)
        window.resize(1600, 980)
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
