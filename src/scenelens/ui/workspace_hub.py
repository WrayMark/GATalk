from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
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
        self.setMinimumSize(310, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(13)

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

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        for feature in features:
            label = QLabel(f"—  {feature}")
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch(1)

        button = QPushButton(f"进入{title}")
        button.setProperty("primary", True)
        button.setMinimumHeight(42)
        button.clicked.connect(lambda: self.selected.emit(self.workspace_id))
        layout.addWidget(button)


class WorkspaceHubWindow(QMainWindow):
    workspace_selected = Signal(str)
    settings_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GATalk — 游戏美术工作台")
        self.resize(1460, 860)
        self.setMinimumSize(1100, 700)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(44, 28, 44, 32)
        root_layout.setSpacing(22)

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
        product_line = QLabel("GAME ART WORKBENCH")
        product_line.setProperty("role", "muted")
        brand_stack.addWidget(product_line)
        header.addLayout(brand_stack)
        header.addStretch(1)
        settings_button = QPushButton("全局设置")
        settings_button.setToolTip("主题、强调色、字号、密度和窗口布局")
        settings_button.clicked.connect(self.settings_requested)
        header.addWidget(settings_button)
        root_layout.addLayout(header)

        hero = QFrame()
        hero.setObjectName("heroPanel")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(7)
        hero_title = QLabel("让美术判断有证据，让制作过程可复查")
        hero_title.setObjectName("heroTitle")
        hero_copy.addWidget(hero_title)
        subtitle = QLabel(
            "从作品学习、资产规划到场景版本审阅，选择当前任务进入对应工作台。"
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "muted")
        hero_copy.addWidget(subtitle)
        hero_layout.addLayout(hero_copy, 1)
        privacy = QLabel(
            "本地优先\n联网前明确确认"
        )
        privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        privacy.setProperty("role", "muted")
        hero_layout.addWidget(privacy)
        root_layout.addWidget(hero)

        cards = QGridLayout()
        cards.setHorizontalSpacing(18)
        cards.setVerticalSpacing(18)
        visual = WorkspaceCard(
            "01",
            "scene_art_control",
            "REVIEW",
            "场景美术控制",
            "围绕制作目标、参考图与 UE 截图，完成证据化审阅、任务和版本复查。",
            (
                "双图对比、共享色板与成对区域",
                "AI 主美与灯光专项审阅",
                "优化预演、任务与版本闭环",
            ),
        )
        artwork = WorkspaceCard(
            "02",
            "artwork_study",
            "STUDY",
            "作品研究",
            "研究一张原画、概念图或优秀作品，逐层理解它为何有效以及如何组织观看。",
            (
                "单图明度、色彩、细节与空间证据",
                "CG 主美十二维深度拆解",
                "学习笔记、标注与综合研究报告",
            ),
        )
        asset_breakdown = WorkspaceCard(
            "03",
            "asset_breakdown",
            "ASSETS",
            "资产拆分工作台",
            "把复杂场景原画转换为可校正、可追溯的结构化生产资产计划。",
            (
                "人工校正拆分与全自动资产板",
                "区域、层级、复用与制作优先级",
                "提示语协商、概念图与结构化导出",
            ),
        )
        for index, card in enumerate((visual, artwork, asset_breakdown)):
            card.selected.connect(self.workspace_selected)
            cards.addWidget(card, 0, index)
        root_layout.addLayout(cards, 1)

        footer = QLabel(
            "原始图片只读 · 无 API Key 仍可使用本地功能 · "
            "主题与窗口布局仅保存在本机"
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        footer.setProperty("role", "muted")
        root_layout.addWidget(footer)
        self.setCentralWidget(root)
