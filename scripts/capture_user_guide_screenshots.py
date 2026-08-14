from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDockWidget,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTreeWidget,
    QWidget,
)

from scenelens.app import create_application
from scenelens.modules.artwork_study.storage import ArtworkStudyStore
from scenelens.modules.artwork_study.ui.window import ArtworkStudyWindow
from scenelens.modules.asset_breakdown.service import create_manual_asset
from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.modules.asset_breakdown.ui.window import AssetBreakdownWindow
from scenelens.modules.comparative_study.storage import ComparativeStudyStore
from scenelens.modules.comparative_study.ui.window import ComparativeStudyWindow
from scenelens.modules.knowledge_base.storage import KnowledgeLibraryStore
from scenelens.modules.knowledge_base.ui.window import KnowledgeBaseWindow
from scenelens.modules.review_control.storage import ReviewCenterStore
from scenelens.modules.review_control.ui.window import ReviewControlWindow
from scenelens.storage.app_settings import AppSettings, AppSettingsStore
from scenelens.storage.models import ArtBrief
from scenelens.storage.project_store import ProjectStore
from scenelens.storage.recent_projects import RecentProjects
from scenelens.ui.main_window import MainWindow
from scenelens.ui.settings_controller import GlobalSettingsController
from scenelens.ui.settings_dialog import GlobalSettingsDialog
from scenelens.ui.theme import apply_appearance
from scenelens.ui.workspace_hub import WorkspaceHubWindow


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "images" / "user-guide-0.18.0"
FIXTURE = ROOT / ".artifacts" / "user-guide-fixture-0.18.0"
LOCALE = "zh-CN"

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_DOCUMENTATION_EXACT_ONLY = {"Gene"}
_DOCUMENTATION_EN_OVERRIDES = {
    "双图与成对区域对照": "Paired image and region comparison",
    "美术方向与场景灯光审阅": "Art direction and scene lighting review",
    "优化预演与版本复查": "Optimization previews and version follow-up",
    "单图形式证据": "Single-image visual evidence",
    "视觉语言与场景表达": "Visual language and scene communication",
    "学习笔记与综合报告": "Study notes and consolidated reports",
    "分层拆分与自动资产板": "Layered breakdown and automatic asset boards",
    "区域、复用与优先级": "Regions, reuse, and production priority",
    "提示语协商与结构化导出": "Prompt iteration and structured export",
    "本地测量与专家研究": "Local measurements and expert analysis",
    "资料库来源与研究结论": "Library sources and research findings",
    "美术参考资料": "Art References",
    "全部资料": "All Items",
    "待整理": "Unsorted",
    "关卡设计资料": "Level Design References",
    "策划与系统资料": "Game Design & Systems",
    "项目笔记": "Project Note",
    "未添加标签": "No labels",
    "原画 / 概念图": "Concept Art",
    "手动记录": "Manual entry",
    "用户创建": "User-created",
    "记录画面用途、主题或检索说明。": "Describe the item's use, subject, or retrieval context.",
    "构图组织": "Composition",
    "视觉层级": "Visual Hierarchy",
    "明度结构": "Value Structure",
    "色彩关系": "Color Relationships",
    "灯光组织": "Lighting",
    "空间层次": "Spatial Depth",
    "形状语言": "Shape Language",
    "边缘与细节": "Edges & Detail",
    "材质表现": "Material Treatment",
    "叙事信息": "Narrative Information",
    "风格与技法": "Style & Technique",
    "情绪作用": "Emotional Effect",
    "环境概念设计": "Environment Concept Art",
    "视觉层级：梳理第一视觉焦点、次级焦点与视线停留区域。": "Visual hierarchy: identify the primary focus, secondary focus, and areas where the eye rests.",
    "形式组织：分析明度、色彩、光线、形状与边缘对空间和情绪的作用。": "Visual structure: examine how value, color, light, shape, and edges create space and mood.",
    "场景表达：识别叙事、尺度与世界观信息的承载方式。": "Scene communication: identify how narrative, scale, and world-building information are conveyed.",
    "设计取舍：说明有效选择、实现代价与适用边界。": "Design decisions: explain effective choices, production costs, and limits of use.",
    "迁移原则：提炼可复用的方法，区分设计方法与表面风格。": "Transferable principles: extract reusable methods without copying surface style.",
    "参考图": "Reference",
    "等待双图分析": "Waiting for paired analysis",
    "通用环境": "General Environment",
    "建筑": "Building",
    "模块构件": "Modular Piece",
    "用户补充／修订": "User revision",
    "中": "Medium",
    "灯光初版": "First Lighting Pass",
    "场景美术控制": "Scene Art Direction",
    "待处理": "Pending",
    "高": "High",
    "尚未指定": "Not specified",
    "未记录": "Not recorded",
    "无法打开消息": "Open Source Item",
    "无图片预览": "No image preview",
    "离线 Mock": "Offline Mock",
    "无 EXIF 旋转 · 未发现可用 ICC，假定为 sRGB": "No EXIF rotation · no usable ICC profile · assumed sRGB",
    "测量结果 · 明度直方图": "Measurement · Value Histogram",
    "算法推断 · Oklab 8 色色板": "Algorithmic Inference · 8-color Oklab Palette",
    "暗": "Dark",
    "亮": "Light",
    "原图": "Original",
    "模糊": "Blur",
    "剪影": "Silhouette",
    "原图只读": "Source image is read-only",
    "当前拆分依据": "Current Breakdown Plan",
    "可复用生产套件": "Reusable Production Kit",
    "草稿": "Draft",
    "未关联场景结构": "No linked scene analysis",
    "尚未打开项目": "No project is open",
    "正在计算共享色板与三阶明度比较…": "Computing the shared palette and three-band value comparison…",
    "资料只在主动导入时复制；网页链接只记录地址，不自动下载内容。": "Files are copied only when imported. Web links store the address only and do not download content.",
    "新建研究后导入 2 至 6 件作品。原始图片保持只读。": "Create a study, then import 2–6 works. Source images remain read-only.",
    "制作任务与验收标准保存在本机，来源项目不会被自动改写。": "Tasks and acceptance criteria are stored locally; source projects are never rewritten automatically.",
    "Production Tasks和Acceptance CriteriaSave在本机；SourceItem不会被自动改写。": "Tasks and acceptance criteria are stored locally; source projects are never rewritten automatically.",
    "Harmonized management of pictures, documents, web sources, collections, labels and research notes. It is located on a professional desk: the art domain is now operational, and future level designs, designs and other information domains can be independently registered without altering existing operational data.": "Manage images, documents, web sources, collections, labels, and research notes across every workbench. Additional knowledge domains can be added without changing existing project data.",
    "Enabled: art reference preset: level design information — planning and system information": "Enabled: Art References · Reserved: Level Design and Game Design & Systems",
    "Areas of information and collection": "Domains & Collections",
    "New Collar": "New Collection",
    "Detailed information": "Details",
    "Information note": "Description",
    "Create a local screenshot from the current picture...": "Create Image Excerpt…",
    "Use selected information to establish a control study": "Start Comparative Study from Selection",
    "Open visual panel": "Open Visual Board",
    "Relative dimensions": "Comparison Axes",
    "Research work (checklist 2-6)": "Works (select 2–6)",
    "Core issues": "Research Question",
    "Run Local Contrast": "Run Local Comparison",
    "Local comparisons show only reversible statistics of visibility, colour and detail, and do not automatically judge merit or disadvantage.": "Local comparison reports reproducible value, color, and detail measurements without assigning quality judgments.",
    "New work research": "New Artwork Study",
    "Open the work for research": "Open Artwork Study",
    "Import Works": "Import Artwork",
    "Give it to the asset split": "Send to Asset Breakdown",
    "Observations:": "View:",
    "Original Chart": "Original",
    "Fuzzy:": "Blur:",
    "Clipshot:": "Silhouette:",
    "Known background (leaveable)": "Known Context (optional)",
    "No EXIF rotation required · No ICC found available, assumed sRGB": "No EXIF orientation · no usable ICC profile · assumed sRGB",
    "Form evidence and space agents": "Spatial Evidence",
    "Local evidence has been completed; attention agents are not automatic maps or judgements.": "Local evidence complete; the attention proxy is not an automatic composition or quality judgment.",
    "New Asset Item": "New Asset Project",
    "Open Asset Item": "Open Asset Project",
    "Import Master Drawings": "Import Source Image",
    "Additional reference": "Add Reference",
    "Box assets": "Draw Asset Box",
    "Hide Box": "Hide Boxes",
    "Edit Program": "Edit Plan",
    "Automatic Assetsboard": "Automatic Asset Board",
    "Split basis": "Breakdown Plan",
    "Details of assets": "Asset Details",
    "Production handover": "Production Handoff",
    "Inventory analysis": "Asset List Analysis",
    "Vendors": "Provider",
    "Field in the system certificate": "Save to System Credentials",
    "Filed in the system certificate": "Save to System Credentials",
    "Check sent content and generate list": "Review Data and Generate List",
    "Gene": "Generate",
    "All Statu:": "All Statuses",
    "Prefix": "No.",
    "Other Organiser": "Assignee",
    "Processing notes": "Notes",
    "Conditions for acceptance and inspection": "Acceptance Criteria",
    "Production phase": "Production Stage",
    "No project is open": "Source Project Not Linked",
    "Batch Start": "Start Selected",
    "Batch completed": "Mark Selected Complete",
    "The area of information for the design and planning of the level is reserved and will be activated upon the establishment of the corresponding business module.": "Level Design and Game Design knowledge domains will become available when their workbenches are added.",
    "Visual models generate structured lists based on the current split programme. Photo models are used in the \"Generation and Exporting\" model; the same supplier evidence.": "Vision models generate a structured list from the current breakdown plan. Image models are used only in Generate and Export; provider credentials are shared across workflows.",
}


def _text(zh_cn: str, en: str) -> str:
    return en if LOCALE == "en" else zh_cn


def _documentation_english(text: str) -> str:
    if not text:
        return text
    palette_match = re.fullmatch(
        r"Colorboard Sample\s*([\d,]+)Pixels; the result is not good or bad\.",
        text,
    )
    if palette_match:
        return (
            f"Palette sample: {palette_match.group(1)} pixels; "
            "the measurement does not assign artistic quality."
        )
    summary_match = re.fullmatch(
        r"Total current programme(\d+)entries;user revisions(\d+)items;"
        r"to be generated(\d+)item\.",
        text,
    )
    if summary_match:
        return (
            f"Current plan: {summary_match.group(1)} assets · "
            f"{summary_match.group(2)} user revisions · "
            f"{summary_match.group(3)} selected for generation."
        )
    status_match = re.fullmatch(
        r"Pending(\d+):: Processing(\d+):: Obstruction(\d+)• "
        r"Failure to pass the necessary doors(\d+)",
        text,
    )
    if status_match:
        return (
            f"Pending: {status_match.group(1)} · In progress: {status_match.group(2)} · "
            f"Blocked: {status_match.group(3)} · Failed gates: {status_match.group(4)}"
        )
    count_match = re.fullmatch(r"(\d+)Item", text)
    if count_match:
        return f"{count_match.group(1)} items"
    manager = app.property("gatalkLocalizationManager")
    result = text
    if manager is not None:
        exact = manager.translate_text(result)
        if exact != result:
            result = exact
        strings = getattr(manager, "_strings", {})
        for source, curated in _DOCUMENTATION_EN_OVERRIDES.items():
            machine = strings.get(source)
            if machine and result == machine:
                return curated
    for source, target in sorted(
        _DOCUMENTATION_EN_OVERRIDES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if len(source) <= 2 or source in _DOCUMENTATION_EXACT_ONLY:
            if result == source:
                result = target
        else:
            result = result.replace(source, target)
    if manager is not None and _CJK_RE.search(result):
        strings = getattr(manager, "_strings", {})
        for source in sorted(strings, key=len, reverse=True):
            if source and source in result:
                result = result.replace(source, strings[source])
    return result


def _translate_tree_item(tree: QTreeWidget, item) -> None:
    for column in range(tree.columnCount()):
        item.setText(column, _documentation_english(item.text(column)))
    for index in range(item.childCount()):
        _translate_tree_item(tree, item.child(index))


def _localize_english_fixture(root: QWidget) -> None:
    if LOCALE != "en":
        return
    objects = [root, *root.findChildren(QWidget)]
    blockers = [QSignalBlocker(obj) for obj in objects]
    try:
        for obj in objects:
            if isinstance(obj, QLabel):
                obj.setText(_documentation_english(obj.text()))
            if isinstance(obj, QAbstractButton):
                obj.setText(_documentation_english(obj.text()))
            if isinstance(obj, QGroupBox):
                obj.setTitle(_documentation_english(obj.title()))
            if isinstance(obj, QDockWidget):
                obj.setWindowTitle(_documentation_english(obj.windowTitle()))
            if isinstance(obj, QLineEdit):
                obj.setPlaceholderText(_documentation_english(obj.placeholderText()))
                obj.setText(_documentation_english(obj.text()))
                obj.setCursorPosition(0)
            if isinstance(obj, QPlainTextEdit):
                obj.setPlaceholderText(_documentation_english(obj.placeholderText()))
                obj.setPlainText(_documentation_english(obj.toPlainText()))
            if isinstance(obj, QComboBox):
                for index in range(obj.count()):
                    obj.setItemText(index, _documentation_english(obj.itemText(index)))
            if isinstance(obj, QTabWidget):
                for index in range(obj.count()):
                    obj.setTabText(index, _documentation_english(obj.tabText(index)))
            if isinstance(obj, QListWidget):
                for index in range(obj.count()):
                    item = obj.item(index)
                    item.setText(_documentation_english(item.text()))
            if isinstance(obj, QTreeWidget):
                header = obj.headerItem()
                if header is not None:
                    for column in range(obj.columnCount()):
                        header.setText(
                            column, _documentation_english(header.text(column))
                        )
                for index in range(obj.topLevelItemCount()):
                    _translate_tree_item(obj, obj.topLevelItem(index))
            if isinstance(obj, QTableWidget):
                for column in range(obj.columnCount()):
                    header = obj.horizontalHeaderItem(column)
                    if header is not None:
                        header.setText(_documentation_english(header.text()))
                for row in range(obj.rowCount()):
                    for column in range(obj.columnCount()):
                        item = obj.item(row, column)
                        if item is not None:
                            item.setText(_documentation_english(item.text()))
            if isinstance(obj, QStatusBar):
                obj.showMessage(_documentation_english(obj.currentMessage()))
    finally:
        blockers.clear()
    for action in root.findChildren(QAction):
        action.setText(_documentation_english(action.text()))
    root.setWindowTitle(_documentation_english(root.windowTitle()))


def _visible_cjk_text(root: QWidget) -> list[str]:
    found: list[str] = []
    for obj in [root, *root.findChildren(QWidget)]:
        if not obj.isVisibleTo(root):
            continue
        values: list[str] = []
        if isinstance(obj, QLabel):
            values.append(obj.text())
        if isinstance(obj, QAbstractButton):
            values.append(obj.text())
        if isinstance(obj, QGroupBox):
            values.append(obj.title())
        if isinstance(obj, QLineEdit):
            values.extend((obj.text(), obj.placeholderText()))
        if isinstance(obj, QPlainTextEdit):
            values.extend((obj.toPlainText(), obj.placeholderText()))
        if isinstance(obj, QComboBox):
            values.append(obj.currentText())
        if isinstance(obj, QStatusBar):
            values.append(obj.currentMessage())
        if isinstance(obj, QListWidget):
            values.extend(obj.item(index).text() for index in range(obj.count()))
        if isinstance(obj, QTreeWidget):
            header = obj.headerItem()
            if header is not None:
                values.extend(
                    header.text(column) for column in range(obj.columnCount())
                )
            pending = [
                obj.topLevelItem(index)
                for index in range(obj.topLevelItemCount())
            ]
            while pending:
                item = pending.pop()
                values.extend(
                    item.text(column) for column in range(obj.columnCount())
                )
                pending.extend(
                    item.child(index) for index in range(item.childCount())
                )
        if isinstance(obj, QTableWidget):
            for row in range(obj.rowCount()):
                for column in range(obj.columnCount()):
                    item = obj.item(row, column)
                    if item is not None:
                        values.append(item.text())
        for value in values:
            if _CJK_RE.search(value):
                found.append(value)
    return sorted(set(found))


def _safe_reset(path: Path) -> None:
    resolved = path.resolve()
    allowed = (ROOT / ".artifacts").resolve()
    if allowed not in resolved.parents:
        raise RuntimeError("Refusing fixture cleanup outside .artifacts")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _scene(path: Path, *, variant: int = 0) -> None:
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), (33, 51, 68))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 420, width, height), fill=(54, 72, 65))
    draw.ellipse((-160, -210, 720, 480), fill=(70, 106, 126))
    draw.ellipse((560, -160, 1450, 430), fill=(123, 144, 150))
    offset = 30 * variant
    for x, building_width, building_height in (
        (90, 250, 280),
        (420, 390, 370),
        (890, 250, 250),
    ):
        top = 500 - building_height + offset
        draw.rectangle(
            (x, top, x + building_width, 520),
            fill=(118 + 8 * variant, 87, 56),
        )
        draw.polygon(
            (
                (x - 20, top + 35),
                (x + building_width // 2, top - 90),
                (x + building_width + 20, top + 35),
            ),
            fill=(55, 82 + 6 * variant, 70),
        )
        for window_x in range(x + 32, x + building_width - 25, 74):
            draw.rectangle(
                (window_x, top + 85, window_x + 30, top + 130),
                fill=(202, 157 - 10 * variant, 72),
            )
    image.save(path)


def _capture(
    widget,
    filename: str,
    width: int,
    height: int,
    *,
    close_after: bool = True,
) -> None:
    widget.resize(width, height)
    widget.show()
    for _ in range(10):
        app.processEvents()
        QTest.qWait(20)
    _localize_english_fixture(widget)
    app.processEvents()
    # Layout events can cause the preview localization manager to re-apply a
    # machine-draft string. The second pass is deliberately last so the guide
    # captures the curated documentation wording.
    _localize_english_fixture(widget)
    for child in [widget, *widget.findChildren(QWidget)]:
        if child.layout() is not None:
            child.layout().activate()
    remaining = _visible_cjk_text(widget)
    if LOCALE == "en" and remaining:
        raise RuntimeError(
            "English documentation screenshot still contains CJK text:\n"
            + "\n---\n".join(remaining)
        )
    target = OUTPUT / filename
    if not widget.grab().save(str(target), "PNG"):
        raise OSError(f"无法保存使用手册截图：{target}")
    if close_after:
        widget.close()
        app.processEvents()


def _workspace_hub() -> None:
    _capture(WorkspaceHubWindow(), "01-workspace-hub.png", 1480, 900)


def _global_settings() -> None:
    dialog = GlobalSettingsDialog(settings)
    if LOCALE == "en":
        dialog.language_quality_note.setText(
            "Preview: core terms reviewed; native-language review still required."
        )
        dialog.language_quality_note.setFixedHeight(30)
    _capture(
        dialog,
        "02-global-settings.png",
        760 if LOCALE == "en" else 680,
        720 if LOCALE == "en" else 650,
    )


def _knowledge_base(source: Path) -> None:
    library_name = _text("环境美术资料库", "Environment Art Library")
    store = KnowledgeLibraryStore.create(FIXTURE / library_name, library_name)
    item = store.import_file(source, title=_text("山地聚落概念图", "Mountain Settlement Concept"))
    collection = store.add_collection(_text("建筑语言", "Architectural Language"))
    store.set_memberships(item.item_id, (collection.collection_id,))
    store.add_note(
        _text("研究笔记", "Study Note"),
        body=_text(
            "屋顶轮廓建立节奏，连廊负责尺度过渡。",
            "Roof silhouettes establish rhythm; covered walkways manage scale transitions.",
        ),
    )
    window = KnowledgeBaseWindow()
    window.open_path(store.root)
    window.library_label.setText(library_name)
    _capture(window, "03-knowledge-base.png", 1520, 900)


def _comparative_study(first: Path, second: Path) -> None:
    folder = _text("聚落对照研究", "Settlement Comparison")
    store = ComparativeStudyStore.create(
        FIXTURE / folder,
        _text("聚落空间层级对照", "Settlement Spatial Hierarchy"),
    )
    left = store.import_image(first, title=_text("清晨方案", "Morning Study"))
    right = store.import_image(second, title=_text("阴天方案", "Overcast Study"))
    store.save(
        replace(
            store.state,
            research_question=_text(
                "比较两种明度与空间组织对建筑层级的影响。",
                "Compare how value structure and spatial organization affect architectural hierarchy.",
            ),
            known_context=_text("教学用合成场景。", "Synthetic scene created for documentation."),
            active_item_ids=(left.item_id, right.item_id),
            selected_axes=(
                _text("构图与层级", "Composition & Hierarchy"),
                _text("明度结构", "Value Structure"),
                _text("色彩组织", "Color Organization"),
            ),
        )
    )
    window = ComparativeStudyWindow()
    window._store = store
    window._load_state()
    _capture(window, "04-comparative-study.png", 1580, 920)


def _artwork_study(source: Path) -> None:
    study_name = _text("山地聚落作品研究", "Mountain Settlement Study")
    store = ArtworkStudyStore.create(FIXTURE / study_name, study_name)
    store.import_image(source)
    window = ArtworkStudyWindow()
    window._set_store(store)
    window.goal_edit.setPlainText(
        _text(
            "研究建筑剪影、雾与明度层级。",
            "Study architectural silhouettes, fog, and value hierarchy.",
        )
    )
    window.context_edit.setPlainText(
        _text("教学用合成图片。", "Synthetic image created for documentation.")
    )
    window.show()
    for _ in range(600):
        app.processEvents()
        if window._local_analysis is not None:
            break
        QTest.qWait(50)
    if window._local_analysis is None:
        raise TimeoutError("作品研究截图未能在 30 秒内完成本地分析")
    if LOCALE == "en":
        window.local_summary.setPlainText(
            "Measurement\n"
            "Mean linear luminance: 0.125; P10/P50/P90: 0.058 / 0.110 / 0.264.\n"
            "Three-band values: shadows 38.7%, midtones 61.3%, highlights 0.0%.\n"
            "Mean chroma: 0.355; low-chroma pixels: 48.7%.\n\n"
            "Algorithmic inference\n"
            "The local attention proxy is strongest in cells 2-3, 1-2, and 2-2. "
            "It is not eye tracking or a semantic focal-point judgment."
        )
    _capture(window, "05-artwork-study.png", 1540, 920)


def _asset_breakdown(source: Path) -> None:
    folder = _text("山地聚落资产", "Mountain Settlement Assets")
    store = AssetBreakdownStore.create(
        FIXTURE / folder,
        _text("山地聚落资产规划", "Mountain Settlement Asset Plan"),
    )
    main = store.import_image(source, "main")
    hall = create_manual_asset(
        name=_text("中央主殿", "Central Hall"),
        category="building",
        rect=(0.32, 0.18, 0.35, 0.58),
        source_image_id=main.image_id,
    )
    roof = replace(
        create_manual_asset(
            name=_text("屋顶模块套件", "Modular Roof Kit"),
            category="modular_piece",
            rect=(0.36, 0.18, 0.28, 0.22),
            source_image_id=main.image_id,
        ),
        parent_asset_id=hall.asset_id,
        reuse_group="roof-kit",
    )
    store.add_or_replace_asset(hall)
    store.add_or_replace_asset(roof)
    window = AssetBreakdownWindow()
    window._attach_store(store)
    window.workflow_tabs.setCurrentIndex(0)
    window.manual_tabs.setCurrentIndex(1)
    if LOCALE == "en":
        window.asset_tree.setColumnWidth(0, 72)
    _capture(window, "06-asset-breakdown.png", 1600, 920)


def _visual_review(reference: Path, current: Path) -> None:
    project_name = _text("中世纪村庄", "Medieval Village")
    store = ProjectStore.create(FIXTURE / f"{project_name}.scenelens", project_name)
    store.save_art_brief(
        ArtBrief(
            scene_type=_text("山地聚落", "Mountain settlement"),
            production_stage=_text("灯光初版", "First lighting pass"),
            target_style=_text("写实风格化", "Stylized realism"),
            time_weather=_text("清晨薄雾", "Misty morning"),
            target_mood=_text("宁静、神秘", "Quiet, mysterious"),
            primary_focus=_text("中央主殿", "Central hall"),
            secondary_focus=_text("远山", "Distant mountains"),
            preserve_content=_text("建筑剪影", "Architectural silhouettes"),
            main_issues=_text("焦点不够集中", "Visual focus is too diffuse"),
            excluded_review=_text("材质微细节", "Fine material detail"),
            constraints=_text("使用现有资产", "Use existing assets"),
        )
    )
    shot = store.create_shot(_text("村口固定机位", "Village Entrance Camera"))
    store.import_reference(shot.id, reference)
    store.add_version(shot.id, current, _text("灯光 v1", "Lighting v1"))
    store.close()
    window = MainWindow(RecentProjects(FIXTURE / "recent-projects.json"))
    controller = GlobalSettingsController(app)
    controller.register_window(window, "user_guide_visual_review")
    window.open_project(store.root)
    for _ in range(160):
        app.processEvents()
        if window._shared_palette_result is not None:
            break
        QTest.qWait(40)
    window.analysis_tabs.setCurrentIndex(2)
    _capture(
        window,
        "07-visual-review.png",
        1580,
        920,
        close_after=False,
    )
    window._comparison_generation += 1
    window._project_store = None
    window.close()
    app.processEvents()


def _review_control() -> None:
    store = ReviewCenterStore.open_or_create(FIXTURE / "review-center")
    store.add_task_from_handoff(
        {
            "title": _text(
                "加强主殿与天空的剪影分离",
                "Improve silhouette separation between the main hall and sky",
            ),
            "description": _text(
                "缩略图下主塔轮廓不连续。",
                "The main tower silhouette breaks down at thumbnail scale.",
            ),
            "acceptance_criteria": _text(
                "25% 缩略图下轮廓保持连续可辨。",
                "The silhouette remains continuous and readable at 25% scale.",
            ),
            "priority": "high",
            "production_stage": "lighting_first",
            "source_module_id": "scenelens.visual_review",
            "source_project_id": "village",
            "source_project_title": _text("中世纪村庄", "Medieval Village"),
            "source_entity_type": "review_finding",
            "source_entity_id": "silhouette",
        }
    )
    store.apply_gate_template(
        "lighting_first",
        source_project_id="village",
        source_project_title=_text("中世纪村庄", "Medieval Village"),
    )
    _capture(ReviewControlWindow(store), "08-review-control.png", 1500, 900)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Capture localized screenshots for the GATalk user guides."
    )
    parser.add_argument(
        "--locale",
        choices=("zh-CN", "en"),
        default="zh-CN",
        help="UI language to capture.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output directory. Defaults to the matching guide image folder.",
    )
    args = parser.parse_args()
    LOCALE = args.locale
    suffix = "" if LOCALE == "zh-CN" else "-en"
    OUTPUT = args.output or ROOT / "docs" / "images" / f"user-guide-0.18.0{suffix}"
    FIXTURE = ROOT / ".artifacts" / f"user-guide-fixture-0.18.0{suffix}"
    _safe_reset(FIXTURE)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT.glob("*.png"):
        old.unlink()
    os.environ["LOCALAPPDATA"] = str(FIXTURE / "local-app-data")
    settings = AppSettings(
        ui_language=LOCALE,
        theme_mode="dark",
        accent="teal",
        font_size=10,
        density="comfortable",
    )
    AppSettingsStore().save(settings)
    app = create_application([], settings)
    apply_appearance(app, settings)
    reference = FIXTURE / _text("山地聚落参考.png", "mountain-settlement-reference.png")
    current = FIXTURE / _text("山地聚落当前.png", "mountain-settlement-current.png")
    _scene(reference)
    _scene(current, variant=1)
    _workspace_hub()
    _global_settings()
    _knowledge_base(reference)
    _comparative_study(reference, current)
    _artwork_study(reference)
    _asset_breakdown(reference)
    _visual_review(reference, current)
    _review_control()
    print(OUTPUT)
    app.quit()
