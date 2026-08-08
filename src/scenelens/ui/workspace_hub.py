from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class WorkspaceCard(QFrame):
    selected = Signal(str)

    def __init__(
        self,
        index: str,
        workspace_id: str,
        category: str,
        title: str,
        description: str,
        features: tuple[str, ...],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.workspace_id = workspace_id
        self.setObjectName("workspaceCard")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(11)
        meta = QHBoxLayout()
        number = QLabel(index)
        number.setObjectName("cardIndex")
        meta.addWidget(number)
        meta.addStretch(1)
        category_label = QLabel(category)
        category_label.setProperty("role", "muted")
        meta.addWidget(category_label)
        layout.addLayout(meta)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        layout.addWidget(heading)
        intro = QLabel(description)
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        layout.addWidget(intro)
        for feature in features:
            label = QLabel(f"—  {feature}")
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch(1)
        button = QPushButton(f"进入{title}")
        button.setProperty("primary", True)
        button.clicked.connect(lambda: self.selected.emit(self.workspace_id))
        layout.addWidget(button)


class WorkspaceHubWindow(QMainWindow):
    workspace_selected = Signal(str)
    settings_requested = Signal()
    task_center_requested = Signal()
    diagnostics_requested = Signal()
    global_search_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GATalk — 游戏美术与创作知识工作台")
        self.resize(1480, 900)
        self.setMinimumSize(1080, 700)
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._search_shortcut.activated.connect(self.global_search_requested)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(44, 28, 44, 36)
        root_layout.setSpacing(22)
        root_layout.addLayout(self._build_header())
        root_layout.addLayout(self._build_platform_entries())

        section = QHBoxLayout()
        title = QLabel("专业工作台")
        title.setObjectName("sectionTitle")
        section.addWidget(title)
        subtitle = QLabel("针对明确任务的项目、分析与生产流程")
        subtitle.setProperty("role", "muted")
        section.addWidget(subtitle)
        section.addStretch(1)
        root_layout.addLayout(section)

        cards = QGridLayout()
        cards.setHorizontalSpacing(18)
        cards.setVerticalSpacing(18)
        definitions = (
            (
                "01", "scene_art_control", "REVIEW", "场景美术控制",
                "围绕制作目标、参考图与 UE 截图，完成证据化审阅、任务和版本复查。",
                ("双图与成对区域对照", "主美、灯光专项审阅", "优化预演与版本闭环"),
            ),
            (
                "02", "artwork_study", "STUDY", "作品研究",
                "逐层研究一张原画、概念图或成品，理解视觉选择为何有效。",
                ("单图形式证据", "主美十二维拆解", "学习笔记与综合报告"),
            ),
            (
                "03", "asset_breakdown", "ASSETS", "资产拆分工作台",
                "把复杂场景原画转成可校正、可追溯的结构化生产资产规划。",
                ("分层拆分与自动资产板", "区域、复用与优先级", "提示语协商与结构化导出"),
            ),
            (
                "04", "comparative_study", "COMPARE", "作品研究集合与对照研究",
                "把多件作品放在同一研究问题下并置，找出策略差异、共同规律与适用边界。",
                ("2–6 件作品同轴对照", "本地测量与专家研究", "资料库来源与研究结论"),
            ),
        )
        for index, definition in enumerate(definitions):
            card = WorkspaceCard(*definition)
            card.selected.connect(self.workspace_selected)
            cards.addWidget(card, index // 2, index % 2)
        root_layout.addLayout(cards)
        footer = QLabel(
            "原始图片只读  ·  无 API Key 仍可使用本地功能  ·  "
            "所有网络发送均需主动确认"
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        footer.setProperty("role", "muted")
        root_layout.addWidget(footer)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        mark = QLabel("GA")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(52, 52)
        header.addWidget(mark)
        brand_stack = QVBoxLayout()
        brand_stack.setSpacing(0)
        title = QLabel("GATalk")
        title.setObjectName("brandTitle")
        brand_stack.addWidget(title)
        product_line = QLabel("GAME ART & CREATIVE KNOWLEDGE WORKBENCH")
        product_line.setProperty("role", "muted")
        brand_stack.addWidget(product_line)
        header.addLayout(brand_stack)
        header.addStretch(1)
        search = QPushButton("全局检索  Ctrl+K")
        search.setToolTip("跨项目搜索资料、研究结论、资产、任务和质量门禁")
        search.clicked.connect(self.global_search_requested)
        header.addWidget(search)
        tasks = QPushButton("任务中心")
        tasks.setToolTip("查看 AI、分析、导出和打包任务的状态与失败原因")
        tasks.clicked.connect(self.task_center_requested)
        header.addWidget(tasks)
        diagnostics = QPushButton("项目诊断")
        diagnostics.clicked.connect(self.diagnostics_requested)
        header.addWidget(diagnostics)
        settings = QPushButton("全局设置")
        settings.clicked.connect(self.settings_requested)
        header.addWidget(settings)
        return header

    def _build_platform_entries(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addWidget(self._build_knowledge_entry(), 1)
        row.addWidget(self._build_review_control_entry(), 1)
        return row

    def _build_knowledge_entry(self) -> QFrame:
        platform = QFrame()
        platform.setObjectName("heroPanel")
        layout = QHBoxLayout(platform)
        layout.setContentsMargins(28, 24, 28, 24)
        copy = QVBoxLayout()
        eyebrow = QLabel("平台层  ·  跨工作台资料基础设施")
        eyebrow.setProperty("role", "muted")
        copy.addWidget(eyebrow)
        title = QLabel("参考资料与知识库")
        title.setObjectName("heroTitle")
        copy.addWidget(title)
        description = QLabel(
            "统一管理图片、文档、网页来源、集合、标签与研究笔记。"
            "它位于专业工作台之上：美术资料域现已启用，未来的关卡设计、"
            "策划与其他资料域可独立注册，不改变现有业务数据。"
        )
        description.setWordWrap(True)
        description.setProperty("role", "muted")
        copy.addWidget(description)
        domains = QLabel("已启用：美术参考资料    已预留：关卡设计资料 · 策划与系统资料")
        domains.setWordWrap(True)
        copy.addWidget(domains)
        layout.addLayout(copy, 1)
        action = QPushButton("进入参考资料与知识库")
        action.setProperty("primary", True)
        action.setMinimumWidth(220)
        action.clicked.connect(
            lambda: self.workspace_selected.emit("reference_knowledge")
        )
        layout.addWidget(action)
        return platform

    def _build_review_control_entry(self) -> QFrame:
        platform = QFrame()
        platform.setObjectName("heroPanel")
        layout = QVBoxLayout(platform)
        layout.setContentsMargins(28, 24, 28, 24)
        eyebrow = QLabel("平台层  ·  跨项目审阅闭环")
        eyebrow.setProperty("role", "muted")
        layout.addWidget(eyebrow)
        title = QLabel("审阅任务与质量门禁中心")
        title.setObjectName("heroTitle")
        layout.addWidget(title)
        description = QLabel(
            "统一接收场景审阅、作品研究和资产拆分中由用户确认的任务，"
            "记录验收条件，并按新版本复查是否改善或解决。"
        )
        description.setWordWrap(True)
        description.setProperty("role", "muted")
        layout.addWidget(description)
        layout.addStretch(1)
        action = QPushButton("进入审阅任务与质量门禁中心")
        action.setProperty("primary", True)
        action.clicked.connect(
            lambda: self.workspace_selected.emit("review_control")
        )
        layout.addWidget(action)
        return platform
