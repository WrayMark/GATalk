from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src" / "scenelens"
OUTPUT_ROOT = SOURCE_ROOT / "i18n"
TARGETS = ("zh-TW", "en", "ja", "fr", "de", "es", "ko")
TRANSLATE_API = "https://translate.googleapis.com/translate_a/single"
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}|%\d|%[sdif]|<[^>]+>")

# Product and game-art terms take precedence over generic machine translation.
GLOSSARY: dict[str, dict[str, str]] = {
    "en": {
        "工作台首页": "Workbench Home",
        "全局检索": "Global Search",
        "任务中心": "Task Center",
        "全局设置": "Settings",
        "项目诊断": "Project Diagnostics",
        "参考资料与知识库": "Reference Library & Knowledge Base",
        "审阅任务与质量门禁中心": "Review Tasks & Quality Gates",
        "场景美术控制": "Scene Art Direction",
        "作品研究": "Artwork Study",
        "资产拆分工作台": "Asset Breakdown",
        "作品研究集合与对照研究": "Study Collections & Comparative Analysis",
        "制作意图": "Creative Intent",
        "参考图视觉简报": "Reference Visual Brief",
        "参考图": "Reference",
        "当前截图": "Current Capture",
        "参考分析": "Reference Analysis",
        "截图分析": "Capture Analysis",
        "对比分析": "Comparison",
        "AI 审阅与任务": "AI Review & Tasks",
        "优化实验室": "Optimization Lab",
        "双图证据概览": "Paired Evidence Overview",
        "共享 Oklab 色板": "Shared Oklab Palette",
        "三阶明度比例": "Three-Band Value Distribution",
        "主美专项审阅": "Art Direction Review",
        "灯光专项审阅": "Lighting Review",
        "深度主美审阅": "In-Depth Art Direction Review",
        "质量门禁": "Quality Gate",
        "可校正拆分": "Guided Breakdown",
        "全自动资产板": "Automated Asset Board",
        "生成提示语": "Prompt Workshop",
        "算法推断": "Algorithmic Inference",
        "测量结果": "Measurement",
        "用户填写": "User Input",
        "用户修订": "User Revision",
        "自动测量": "Automated Measurement",
        "AI分析": "AI Analysis",
        "AI 分析": "AI Analysis",
        "明度": "Value",
        "彩度": "Chroma",
        "色相": "Hue",
        "饱和度": "Saturation",
        "色板": "Palette",
        "构图": "Composition",
        "灯光与氛围": "Lighting & Atmosphere",
        "空间层次": "Spatial Depth",
        "视觉焦点": "Visual Focus",
        "资产清单": "Asset List",
        "保存项目": "Save Project",
        "打开项目": "Open Project",
        "新建项目": "New Project",
        "删除": "Delete",
        "取消": "Cancel",
        "保存": "Save",
        "关闭": "Close",
        "应用": "Apply",
        "恢复默认": "Restore Defaults",
        "界面语言": "Display Language",
        "主题": "Theme",
        "强调色": "Accent Color",
        "界面字号": "Interface Font Size",
        "控件密度": "UI Density",
        "进入场景美术控制": "Open Scene Art Direction",
        "进入作品研究": "Open Artwork Study",
        "进入资产拆分工作台": "Open Asset Breakdown",
        "进入作品研究集合与对照研究": "Open Comparative Study",
        "游戏美术与创作知识工作台": "Game Art & Creative Knowledge Workbench",
        "专业工作台": "Professional Workbenches",
        "针对明确任务的项目、分析与生产流程": "Project-based analysis and production workflows",
        "全局检索  Ctrl+K": "Search  Ctrl+K",
        "原始图片只读  ·  无 API Key 仍可使用本地功能  ·  所有网络发送均需主动确认": "Source images stay read-only  ·  Local tools work without an API key  ·  Every network request requires confirmation",
        "围绕制作目标、参考图与 UE 截图，完成证据化审阅、任务和版本复查。": "Review targets, references, and UE captures with evidence, tasks, and version follow-up.",
        "逐层研究一张原画、概念图或成品，理解视觉选择为何有效。": "Study an artwork, concept, or finished image layer by layer to understand why its visual choices work.",
        "把复杂场景原画转成可校正、可追溯的结构化生产资产规划。": "Turn complex environment art into an editable, traceable production asset plan.",
        "把多件作品放在同一研究问题下并置，找出策略差异、共同规律与适用边界。": "Compare several works under one research question to identify strategic differences, shared principles, and limits.",
        "双图与成对区域对照": "Paired images and matched regions",
        "主美、灯光专项审阅": "Art direction and lighting reviews",
        "优化预演与版本闭环": "Optimization previews and version follow-up",
        "单图形式证据": "Single-image formal evidence",
        "主美十二维拆解": "Twelve-dimension art direction study",
        "学习笔记与综合报告": "Study notes and consolidated report",
        "分层拆分与自动资产板": "Layered breakdown and automated asset boards",
        "区域、复用与优先级": "Regions, reuse, and priority",
        "提示语协商与结构化导出": "Prompt iteration and structured export",
        "2–6 件作品同轴对照": "Compare 2–6 works on shared axes",
        "本地测量与专家研究": "Local measurement and expert study",
        "资料库来源与研究结论": "Library sources and study conclusions",
        "平台层  ·  跨工作台资料基础设施": "Platform  ·  Cross-workbench reference infrastructure",
        "平台层  ·  跨项目审阅闭环": "Platform  ·  Cross-project review loop",
        "进入参考资料与知识库": "Open Reference Library",
        "进入审阅任务与质量门禁中心": "Open Review Tasks & Quality Gates",
        "跟随系统 / System": "Follow system / System",
        "保存后立即应用，并在以后启动时保持。": "Applies when saved and remains selected for future launches.",
        "简体中文为完整基准语言。": "Simplified Chinese is the complete source language.",
        "界面预览": "Interface Preview",
        "主要操作": "Primary Action",
        "确定": "OK",
        "GATalk — 全局设置": "GATalk — Settings",
        "这些设置作用于首页和全部工作台，并保存在本机；不会写入项目或上传。": "These settings apply to the home screen and every workbench. They are stored locally and never written to a project or uploaded.",
        "翻译状态": "Translation Status",
        "跟随 Windows": "Follow Windows",
        "浅色": "Light",
        "深色": "Dark",
        "主美紫": "Art Direction Violet",
        "工作台蓝": "Workbench Blue",
        "青绿色": "Teal",
        "暖橙色": "Warm Orange",
        "较小 · 9 pt": "Small · 9 pt",
        "标准 · 10 pt": "Standard · 10 pt",
        "较大 · 11 pt": "Large · 11 pt",
        "大 · 12 pt": "Extra Large · 12 pt",
        "紧凑": "Compact",
        "舒适": "Comfortable",
        "宽松": "Spacious",
        "记住每个工作台的窗口大小、停靠面板和工具栏布局": "Remember window size, dock panels, and toolbars for each workbench",
        "关闭后仍保留数据，但启动时不再恢复。": "Keeps saved layouts but stops restoring them at startup.",
        "清除已保存布局": "Clear Saved Layouts",
        "GATalk 使用中性色建立层级，只把强调色用于当前页签、主要按钮和交互反馈。": "GATalk uses neutral colors for hierarchy and reserves the accent color for active tabs, primary actions, and feedback.",
        "预览语言包": "Preview language pack",
        "已校核核心术语": "Reviewed core terms",
        "翻译初稿，正式发布前需母语审校。": "Translation draft; native-language review is required before release.",
        "未覆盖内容回退为简体中文。": "Untranslated text falls back to Simplified Chinese.",
    },
    "ja": {
        "工作台首页": "ワークベンチ ホーム",
        "全局检索": "全体検索",
        "任务中心": "タスクセンター",
        "全局设置": "設定",
        "项目诊断": "プロジェクト診断",
        "场景美术控制": "シーンアートディレクション",
        "作品研究": "作品研究",
        "资产拆分工作台": "アセット分解",
        "审阅任务与质量门禁中心": "レビュータスクと品質ゲート",
        "制作意图": "制作意図",
        "参考图视觉简报": "リファレンス ビジュアルブリーフ",
        "参考图": "リファレンス",
        "当前截图": "現在のキャプチャ",
        "对比分析": "比較分析",
        "灯光专项审阅": "ライティングレビュー",
        "质量门禁": "品質ゲート",
        "资产清单": "アセットリスト",
        "保存": "保存",
        "删除": "削除",
        "取消": "キャンセル",
        "界面语言": "表示言語",
        "预览语言包": "プレビュー言語パック",
        "已校核核心术语": "確認済みの主要用語",
        "翻译初稿，正式发布前需母语审校。": "翻訳初稿です。正式公開前にネイティブチェックが必要です。",
        "未覆盖内容回退为简体中文。": "未翻訳のテキストは簡体字中国語で表示されます。",
        "GATalk — 全局设置": "GATalk — 設定",
        "全局设置": "設定",
        "这些设置作用于首页和全部工作台，并保存在本机；不会写入项目或上传。": "この設定はホームとすべてのワークベンチに適用され、PC に保存されます。プロジェクトへの書き込みやアップロードは行いません。",
        "保存后立即应用，并在以后启动时保持。": "保存するとすぐに適用され、次回以降も保持されます。",
        "翻译状态": "翻訳ステータス",
        "主题": "テーマ",
        "跟随 Windows": "Windows の設定に従う",
        "浅色": "ライト",
        "深色": "ダーク",
        "强调色": "アクセントカラー",
        "主美紫": "アートディレクション・バイオレット",
        "工作台蓝": "ワークベンチ・ブルー",
        "青绿色": "ティール",
        "暖橙色": "ウォームオレンジ",
        "界面字号": "UI フォントサイズ",
        "较小 · 9 pt": "小 · 9 pt",
        "标准 · 10 pt": "標準 · 10 pt",
        "较大 · 11 pt": "大 · 11 pt",
        "大 · 12 pt": "特大 · 12 pt",
        "控件密度": "UI 密度",
        "紧凑": "コンパクト",
        "舒适": "標準",
        "宽松": "ゆったり",
        "记住每个工作台的窗口大小、停靠面板和工具栏布局": "ワークベンチごとのウィンドウサイズ、ドック、ツールバー配置を記憶する",
        "关闭后仍保留数据，但启动时不再恢复。": "保存済みの配置は残しますが、起動時に復元しません。",
        "清除已保存布局": "保存済み配置を消去",
        "界面预览": "UI プレビュー",
        "GATalk 使用中性色建立层级，只把强调色用于当前页签、主要按钮和交互反馈。": "GATalk はニュートラルカラーで階層を示し、アクセントカラーは選択中のタブ、主要操作、フィードバックに限定します。",
        "主要操作": "主要操作",
        "确定": "OK",
        "恢复默认": "既定値に戻す",
        "应用": "適用",
    },
    "fr": {
        "工作台首页": "Accueil des espaces de travail",
        "全局检索": "Recherche globale",
        "任务中心": "Centre des tâches",
        "全局设置": "Paramètres",
        "项目诊断": "Diagnostic du projet",
        "场景美术控制": "Direction artistique de scène",
        "作品研究": "Étude d’œuvre",
        "资产拆分工作台": "Décomposition des assets",
        "审阅任务与质量门禁中心": "Tâches de revue et critères qualité",
        "制作意图": "Intention artistique",
        "参考图": "Référence",
        "当前截图": "Capture actuelle",
        "质量门禁": "Critère qualité",
        "保存": "Enregistrer",
        "删除": "Supprimer",
        "取消": "Annuler",
        "界面语言": "Langue d’affichage",
        "预览语言包": "Pack linguistique en aperçu",
        "已校核核心术语": "Termes clés vérifiés",
        "翻译初稿，正式发布前需母语审校。": "Traduction provisoire ; une révision par un locuteur natif est requise avant publication.",
        "未覆盖内容回退为简体中文。": "Les textes non traduits s’affichent en chinois simplifié.",
        "GATalk — 全局设置": "GATalk — Paramètres",
        "全局设置": "Paramètres",
        "这些设置作用于首页和全部工作台，并保存在本机；不会写入项目或上传。": "Ces paramètres s’appliquent à l’accueil et à tous les espaces de travail. Ils restent sur cet ordinateur et ne sont ni ajoutés aux projets ni envoyés en ligne.",
        "保存后立即应用，并在以后启动时保持。": "Les modifications s’appliquent dès l’enregistrement et sont conservées aux prochains démarrages.",
        "翻译状态": "État de la traduction",
        "主题": "Thème",
        "跟随 Windows": "Suivre Windows",
        "浅色": "Clair",
        "深色": "Sombre",
        "强调色": "Couleur d’accentuation",
        "主美紫": "Violet direction artistique",
        "工作台蓝": "Bleu espace de travail",
        "青绿色": "Bleu sarcelle",
        "暖橙色": "Orange chaud",
        "界面字号": "Taille du texte",
        "较小 · 9 pt": "Petit · 9 pt",
        "标准 · 10 pt": "Standard · 10 pt",
        "较大 · 11 pt": "Grand · 11 pt",
        "大 · 12 pt": "Très grand · 12 pt",
        "控件密度": "Densité de l’interface",
        "紧凑": "Compacte",
        "舒适": "Confortable",
        "宽松": "Aérée",
        "记住每个工作台的窗口大小、停靠面板和工具栏布局": "Mémoriser la taille de fenêtre, les panneaux ancrés et les barres d’outils de chaque espace",
        "关闭后仍保留数据，但启动时不再恢复。": "Conserve les dispositions enregistrées sans les restaurer au démarrage.",
        "清除已保存布局": "Effacer les dispositions",
        "界面预览": "Aperçu de l’interface",
        "GATalk 使用中性色建立层级，只把强调色用于当前页签、主要按钮和交互反馈。": "GATalk utilise des tons neutres pour la hiérarchie et réserve la couleur d’accentuation aux onglets actifs, aux actions principales et aux retours.",
        "主要操作": "Action principale",
        "确定": "OK",
        "恢复默认": "Rétablir les valeurs par défaut",
        "应用": "Appliquer",
    },
    "de": {
        "工作台首页": "Arbeitsbereich-Startseite",
        "全局检索": "Globale Suche",
        "任务中心": "Aufgabenzentrale",
        "全局设置": "Einstellungen",
        "项目诊断": "Projektdiagnose",
        "场景美术控制": "Szenen-Art-Direction",
        "作品研究": "Werkanalyse",
        "资产拆分工作台": "Asset-Aufschlüsselung",
        "审阅任务与质量门禁中心": "Review-Aufgaben und Qualitätsprüfungen",
        "制作意图": "Gestaltungsabsicht",
        "参考图": "Referenz",
        "当前截图": "Aktueller Screenshot",
        "质量门禁": "Qualitätsprüfung",
        "保存": "Speichern",
        "删除": "Löschen",
        "取消": "Abbrechen",
        "界面语言": "Anzeigesprache",
        "预览语言包": "Sprachpaket-Vorschau",
        "已校核核心术语": "Geprüfte Kernbegriffe",
        "翻译初稿，正式发布前需母语审校。": "Übersetzungsentwurf; vor der Veröffentlichung ist eine muttersprachliche Prüfung erforderlich.",
        "未覆盖内容回退为简体中文。": "Nicht übersetzte Texte werden auf vereinfachtem Chinesisch angezeigt.",
    },
    "es": {
        "工作台首页": "Inicio de espacios de trabajo",
        "全局检索": "Búsqueda global",
        "任务中心": "Centro de tareas",
        "全局设置": "Configuración",
        "项目诊断": "Diagnóstico del proyecto",
        "场景美术控制": "Dirección artística de escena",
        "作品研究": "Estudio de obra",
        "资产拆分工作台": "Desglose de recursos",
        "审阅任务与质量门禁中心": "Tareas de revisión y controles de calidad",
        "制作意图": "Intención artística",
        "参考图": "Referencia",
        "当前截图": "Captura actual",
        "质量门禁": "Control de calidad",
        "保存": "Guardar",
        "删除": "Eliminar",
        "取消": "Cancelar",
        "界面语言": "Idioma de la interfaz",
        "预览语言包": "Paquete de idioma en vista previa",
        "已校核核心术语": "Términos clave revisados",
        "翻译初稿，正式发布前需母语审校。": "Traducción provisional; requiere revisión nativa antes de publicarse.",
        "未覆盖内容回退为简体中文。": "El texto no traducido se muestra en chino simplificado.",
    },
    "ko": {
        "工作台首页": "워크벤치 홈",
        "全局检索": "전체 검색",
        "任务中心": "작업 센터",
        "全局设置": "설정",
        "项目诊断": "프로젝트 진단",
        "场景美术控制": "씬 아트 디렉션",
        "作品研究": "작품 연구",
        "资产拆分工作台": "에셋 분해",
        "审阅任务与质量门禁中心": "리뷰 작업 및 품질 게이트",
        "制作意图": "제작 의도",
        "参考图": "레퍼런스",
        "当前截图": "현재 캡처",
        "质量门禁": "품질 게이트",
        "保存": "저장",
        "删除": "삭제",
        "取消": "취소",
        "界面语言": "표시 언어",
        "预览语言包": "미리 보기 언어 팩",
        "已校核核心术语": "검토된 핵심 용어",
        "翻译初稿，正式发布前需母语审校。": "번역 초안이며, 정식 배포 전 원어민 검수가 필요합니다.",
        "未覆盖内容回退为简体中文。": "번역되지 않은 텍스트는 중국어 간체로 표시됩니다.",
    },
    "zh-TW": {
        "工作台首页": "工作台首頁",
        "全局检索": "全域搜尋",
        "任务中心": "工作中心",
        "全局设置": "全域設定",
        "项目诊断": "專案診斷",
        "参考资料与知识库": "參考資料與知識庫",
        "审阅任务与质量门禁中心": "審閱工作與品質門檻中心",
        "场景美术控制": "場景美術控制",
        "作品研究": "作品研究",
        "资产拆分工作台": "資產拆分工作台",
        "作品研究集合与对照研究": "作品研究集合與對照研究",
        "制作意图": "製作意圖",
        "参考图视觉简报": "參考圖視覺簡報",
        "参考图": "參考圖",
        "当前截图": "目前截圖",
        "对比分析": "對照分析",
        "质量门禁": "品質門檻",
        "资产清单": "資產清單",
        "保存": "儲存",
        "删除": "刪除",
        "取消": "取消",
        "界面语言": "介面語言",
        "预览语言包": "預覽語言套件",
        "已校核核心术语": "已校核核心術語",
        "翻译初稿，正式发布前需母语审校。": "翻譯初稿，正式發佈前需由母語使用者審校。",
        "未覆盖内容回退为简体中文。": "未涵蓋內容會回退為簡體中文。",
        "GATalk — 全局设置": "GATalk — 全域設定",
        "全局设置": "全域設定",
        "这些设置作用于首页和全部工作台，并保存在本机；不会写入项目或上传。": "這些設定套用於首頁與所有工作台，並儲存在本機；不會寫入專案或上傳。",
        "保存后立即应用，并在以后启动时保持。": "儲存後立即套用，之後啟動時仍會保留。",
        "翻译状态": "翻譯狀態",
        "主题": "主題",
        "跟随 Windows": "跟隨 Windows",
        "浅色": "淺色",
        "深色": "深色",
        "强调色": "強調色",
        "主美紫": "主美紫",
        "工作台蓝": "工作台藍",
        "青绿色": "藍綠色",
        "暖橙色": "暖橙色",
        "界面字号": "介面字級",
        "较小 · 9 pt": "較小 · 9 pt",
        "标准 · 10 pt": "標準 · 10 pt",
        "较大 · 11 pt": "較大 · 11 pt",
        "大 · 12 pt": "大 · 12 pt",
        "控件密度": "控制項密度",
        "紧凑": "緊湊",
        "舒适": "舒適",
        "宽松": "寬鬆",
        "记住每个工作台的窗口大小、停靠面板和工具栏布局": "記住每個工作台的視窗大小、停駐面板與工具列配置",
        "关闭后仍保留数据，但启动时不再恢复。": "關閉後仍保留資料，但啟動時不再還原。",
        "清除已保存布局": "清除已儲存配置",
        "界面预览": "介面預覽",
        "GATalk 使用中性色建立层级，只把强调色用于当前页签、主要按钮和交互反馈。": "GATalk 使用中性色建立層級，只把強調色用於目前分頁、主要按鈕與互動回饋。",
        "主要操作": "主要操作",
        "确定": "確定",
        "恢复默认": "還原預設值",
        "应用": "套用",
    },
}


def source_files() -> list[Path]:
    return sorted(
        list((SOURCE_ROOT / "ui").rglob("*.py"))
        + list((SOURCE_ROOT / "modules").glob("*/ui/*.py"))
        + list((SOURCE_ROOT / "modules").glob("*/workbench.py"))
    )


def extract_strings() -> list[str]:
    result: set[str] = set()
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value.strip()
            if not value or len(value) > 260 or not CHINESE_RE.search(value):
                continue
            if "{" in value and "}" in value:
                continue
            result.add(value)
    return sorted(result)


def extract_patterns() -> list[str]:
    result: set[str] = set()
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            parts: list[str] = []
            placeholder = 0
            valid = True
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue):
                    parts.append("{" + str(placeholder) + "}")
                    placeholder += 1
                else:
                    valid = False
                    break
            pattern = "".join(parts).strip()
            if (
                valid
                and placeholder
                and len(pattern) <= 300
                and CHINESE_RE.search(pattern)
            ):
                result.add(pattern)
    return sorted(result)


def translate_batch(strings: list[str], locale: str) -> list[str]:
    marker = "<<<GATALK_SPLIT_{:04d}>>>"
    joined = "\n".join(
        item
        for index, text in enumerate(strings)
        for item in ((marker.format(index) + "\n" if index else "") + text,)
    )
    data = urlencode(
        {"client": "gtx", "sl": "zh-CN", "tl": locale, "dt": "t", "q": joined}
    ).encode("utf-8")
    request = Request(TRANSLATE_API, data=data, headers={"User-Agent": "GATalk-i18n-builder/1.0"})
    with urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    translated = "".join(part[0] for part in payload[0])
    parts = re.split(r"<<<GATALK_SPLIT_\d{4}>>>", translated)
    return [part.strip() for part in parts]


def translate_all(strings: list[str], locale: str) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for start in range(0, len(strings), 35):
        batch = strings[start : start + 35]
        result = translate_batch(batch, locale)
        if len(result) != len(batch):
            raise RuntimeError(f"Translation split mismatch for {locale} at {start}.")
        for source, target in zip(batch, result, strict=True):
            catalog[source] = target or source
        print(f"{locale}: {min(start + len(batch), len(strings))}/{len(strings)}")
    catalog.update(GLOSSARY.get(locale, {}))
    return catalog


def validate_catalog(
    source: list[str],
    catalog: dict[str, str],
    locale: str,
    *,
    require_complete: bool,
) -> None:
    missing = (
        [item for item in source if not catalog.get(item, "").strip()]
        if require_complete
        else []
    )
    placeholder_mismatch = [
        item
        for item in catalog
        if sorted(PLACEHOLDER_RE.findall(item))
        != sorted(PLACEHOLDER_RE.findall(catalog.get(item, "")))
    ]
    if missing or placeholder_mismatch:
        raise RuntimeError(
            f"{locale}: missing={len(missing)}, placeholder_mismatch={len(placeholder_mismatch)}"
        )


def main() -> int:
    strings = extract_strings()
    patterns = extract_patterns()
    targets = tuple(sys.argv[1:]) or TARGETS
    glossary_only = "--glossary-only" in targets
    targets = tuple(value for value in targets if value != "--glossary-only")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for locale in targets:
        if locale not in TARGETS:
            raise ValueError(f"Unsupported target locale: {locale}")
        if glossary_only:
            existing: dict[str, str] = {}
            destination = OUTPUT_ROOT / f"{locale}.json"
            if destination.is_file():
                payload = json.loads(destination.read_text(encoding="utf-8"))
                existing = {
                    str(key): str(value)
                    for key, value in dict(payload.get("strings", {})).items()
                }
            catalog = {
                item: existing[item]
                for item in strings
                if item in existing and existing[item] != item
            }
            catalog.update(GLOSSARY.get(locale, {}))
        else:
            catalog = translate_all(strings, locale)
        validate_catalog(
            strings,
            catalog,
            locale,
            require_complete=not glossary_only,
        )
        payload = {
            "locale": locale,
            "source_locale": "zh-CN",
            "catalog_version": 1,
            "strings": catalog,
            "patterns": [],
            "translation_stage": "reviewed_subset",
            "reviewed_count": sum(
                item in GLOSSARY.get(locale, {}) for item in strings
            ),
        }
        translated_count = sum(
            bool(catalog.get(item, "").strip()) for item in strings
        )
        payload["translated_count"] = translated_count
        payload["total_count"] = len(strings) + len(patterns)
        payload["status"] = (
            "complete" if translated_count == len(strings) else "preview"
        )
        (OUTPUT_ROOT / f"{locale}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
