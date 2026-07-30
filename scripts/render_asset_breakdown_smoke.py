from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import sys
import time
import uuid

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scenelens.analysis.asset_masks import visible_asset_mask
from scenelens.app import create_application
from scenelens.modules.asset_breakdown.artifacts import asset_crop_png
from scenelens.modules.asset_breakdown.models import AssetItem, GenerationRecord
from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.asset_breakdown.ui.window import AssetBreakdownWindow
from scenelens.storage.project_store import utc_now


OUTPUT = ROOT / ".qa" / "asset-breakdown-validation"


def make_scene(path: Path, scene: str) -> None:
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), (45, 62, 85))
    draw = ImageDraw.Draw(image)
    if scene == "village":
        draw.rectangle((0, 500, width, height), fill=(86, 72, 47))
        draw.polygon(
            ((0, 350), (180, 190), (360, 320), (580, 130), (760, 330), (1000, 160), (1280, 340), (1280, 500), (0, 500)),
            fill=(65, 86, 69),
        )
        for index, x in enumerate((70, 330, 620, 930)):
            body = (x, 260 - index * 22, x + 230, 535)
            draw.rectangle(body, fill=(124 + index * 8, 93, 57))
            draw.polygon(
                (
                    (x - 24, body[1] + 12),
                    (x + 115, body[1] - 105),
                    (x + 254, body[1] + 12),
                ),
                fill=(76, 45 + index * 4, 39),
            )
            for window_x in (x + 35, x + 145):
                draw.rectangle(
                    (window_x, body[1] + 70, window_x + 42, body[1] + 125),
                    fill=(225, 165, 72),
                )
            draw.rectangle(
                (x + 92, body[3] - 105, x + 145, body[3]),
                fill=(58, 42, 31),
            )
        for x in (35, 250, 520, 820, 1110):
            draw.ellipse((x, 390, x + 95, 570), fill=(48, 91, 52))
        draw.polygon(
            ((0, 650), (400, 520), (870, 540), (1280, 610), (1280, 720), (0, 720)),
            fill=(116, 99, 70),
        )
        for x in range(80, 1180, 180):
            draw.rectangle((x, 535, x + 95, 600), fill=(140, 75, 38))
    else:
        image = Image.new("RGB", (width, height), (18, 28, 38))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 570, width, height), fill=(45, 47, 50))
        for index, x in enumerate((45, 285, 525, 765, 1005)):
            draw.rectangle(
                (x, 120 - (index % 2) * 45, x + 195, 595),
                fill=(63, 77, 88),
            )
            draw.rectangle((x + 22, 150, x + 52, 555), fill=(18, 142, 176))
            draw.rectangle((x + 75, 180, x + 165, 260), fill=(28, 35, 43))
            for y in (310, 405, 500):
                draw.rectangle((x + 70, y, x + 175, y + 18), fill=(190, 102, 44))
        draw.line((0, 205, width, 285), fill=(194, 88, 38), width=28)
        draw.line((70, 70, 70, 650), fill=(85, 190, 190), width=18)
        draw.line((1170, 40, 1170, 650), fill=(85, 190, 190), width=18)
        for x in (160, 410, 675, 925):
            draw.ellipse((x, 520, x + 125, 645), fill=(88, 91, 94))
            draw.rectangle((x + 45, 490, x + 82, 585), fill=(128, 73, 41))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def asset(
    asset_id: str,
    name: str,
    category: str,
    rect: tuple[float, float, float, float],
    image_id: str,
    *,
    parent: str = "",
    level: int = 0,
    priority: str = "medium",
) -> AssetItem:
    now = utc_now()
    return AssetItem(
        asset_id=asset_id,
        name=name,
        category=category,
        semantic_type="验证样例",
        parent_asset_id=parent,
        level=level,
        normalized_rect=rect,
        evidence_kind="user_added",
        visible_evidence="验证图中可见的轮廓、位置与重复关系。",
        inferred_details="模块边界和复用关系为验证用人工规划。",
        uncertainty="背面与遮挡结构未确认。",
        confidence=1.0,
        production_priority=priority,
        production_strategy="先制作基准件，再派生重复和变体。",
        selected_for_generation=priority in {"critical", "high"},
        user_modified=True,
        source_image_id=image_id,
        created_at=now,
        updated_at=now,
    )


def populate(store: AssetBreakdownStore, source: Path, scene: str) -> None:
    main = store.import_image(source, "main")
    if scene == "village":
        values = (
            asset("v_house_kit", "木石民居模块套件", "building", (0.04, 0.12, 0.89, 0.63), main.image_id, priority="critical"),
            asset("v_roof", "坡屋顶基准件与四种变体", "modular_piece", (0.03, 0.09, 0.91, 0.29), main.image_id, parent="v_house_kit", level=1, priority="high"),
            asset("v_wall", "墙段、门窗与转角", "modular_piece", (0.06, 0.32, 0.88, 0.42), main.image_id, parent="v_house_kit", level=1, priority="high"),
            asset("v_stall", "市集摊位组合", "prop", (0.05, 0.72, 0.86, 0.14), main.image_id, priority="high"),
            asset("v_tree", "阔叶树与灌木群落", "vegetation", (0.01, 0.48, 0.94, 0.32), main.image_id),
            asset("v_terrain", "坡地、道路与石墙", "terrain", (0.0, 0.68, 1.0, 0.32), main.image_id),
        )
        scene_type = "medieval_village"
    else:
        values = (
            asset("s_structure", "工业结构模块组", "building", (0.03, 0.06, 0.94, 0.78), main.image_id, priority="critical"),
            asset("s_bay", "重复框架与面板舱", "modular_piece", (0.03, 0.13, 0.93, 0.68), main.image_id, parent="s_structure", level=1, priority="high"),
            asset("s_pipe", "主输送管线系统", "modular_piece", (0.0, 0.27, 1.0, 0.17), main.image_id, parent="s_structure", level=1, priority="high"),
            asset("s_machine", "地面机械与容器组", "prop", (0.08, 0.67, 0.78, 0.24), main.image_id, priority="high"),
            asset("s_decal", "警示条与工业贴花", "decal", (0.05, 0.42, 0.90, 0.30), main.image_id),
            asset("s_light", "青色引导灯与橙色强调", "lighting_vfx", (0.01, 0.08, 0.96, 0.80), main.image_id),
        )
        scene_type = "scifi_industrial"
    store.replace_assets(values)
    store.state = replace(
        store.state,
        scene_type=scene_type,
        production_goal=(
            "验证模块套件、重复关系、用户修订、可见遮罩与按需生成。"
        ),
        selected_asset_id=values[0].asset_id,
    )
    store.save()
    rgb = np.asarray(Image.open(source).convert("RGB"), dtype=np.uint8)
    for item in values[:2]:
        mask, method = visible_asset_mask(rgb, item.normalized_rect)
        generation_id = str(uuid.uuid4())
        relative = (
            f"artifacts/generated/{item.asset_id}_{generation_id[:8]}.png"
        )
        store.save_artifact(relative, asset_crop_png(rgb, item, mask))
        store.append_generation(
            GenerationRecord(
                generation_id=generation_id,
                asset_id=item.asset_id,
                output_kind="isolated_concept",
                source_image_sha256=main.sha256,
                source_rect=item.normalized_rect,
                provider_id="mock",
                model_id="mock-image-v1",
                parameters={"validation_only": True, "mask_method": method},
                relative_path=relative,
                status="completed",
                created_at=utc_now(),
            )
        )


def render(scene: str) -> Path:
    source = OUTPUT / f"{scene}-concept.png"
    project = OUTPUT / f"{scene}.scenelens-assets"
    output_root = OUTPUT.resolve()
    resolved_project = project.resolve()
    if output_root not in resolved_project.parents:
        raise RuntimeError("Refusing to remove a validation project outside OUTPUT.")
    if project.exists():
        shutil.rmtree(project)
    make_scene(source, scene)
    store = AssetBreakdownStore.create(project, f"{scene} 资产拆分验证")
    populate(store, source, scene)
    window = AssetBreakdownWindow()
    window._attach_store(store)
    window.show()
    app = create_application()
    deadline = time.monotonic() + 8.0
    while window._loaded is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    window._refresh_asset_tree(
        select_id=window._state.assets[0].asset_id
    )
    window._refresh_overlays()
    for _index in range(15):
        app.processEvents()
        time.sleep(0.02)
    output = OUTPUT / f"asset-breakdown-{scene}.png"
    window.grab().save(str(output), "PNG")
    window.close()
    app.processEvents()
    return output


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = create_application([])
    del app
    for scene in ("village", "industrial"):
        print(render(scene))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
