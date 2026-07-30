from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
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
        workspace_id: str,
        title: str,
        description: str,
        features: tuple[str, ...],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.workspace_id = workspace_id
        self.setObjectName("workspaceCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "#workspaceCard {background:#292A2D;border:1px solid #4A4D52;"
            "border-radius:10px;} #workspaceCard:hover {border-color:#8AB4F8;}"
        )
        self.setMinimumSize(320, 350)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:18pt;font-weight:700;color:#F1F3F4;")
        layout.addWidget(heading)
        intro = QLabel(description)
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size:11pt;color:#BDC1C6;")
        layout.addWidget(intro)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        for feature in features:
            label = QLabel(f"• {feature}")
            label.setWordWrap(True)
            label.setStyleSheet("color:#DADCE0;")
            layout.addWidget(label)
        layout.addStretch(1)
        button = QPushButton(f"进入{title}")
        button.setMinimumHeight(42)
        button.setStyleSheet(
            "QPushButton {background:#3C5F8A;border-color:#8AB4F8;"
            "font-weight:600;} QPushButton:hover {background:#466F9F;}"
        )
        button.clicked.connect(lambda: self.selected.emit(self.workspace_id))
        layout.addWidget(button)


class WorkspaceHubWindow(QMainWindow):
    workspace_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SceneLens — 游戏美术工作台")
        self.resize(1420, 760)
        self.setMinimumSize(1040, 650)
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(48, 36, 48, 42)
        root_layout.setSpacing(20)
        title = QLabel("SceneLens")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet("font-size:28pt;font-weight:800;color:#F1F3F4;")
        root_layout.addWidget(title)
        subtitle = QLabel(
            "游戏美术控制、作品学习与资产规划工作台\n选择本次要完成的工作。"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        subtitle.setStyleSheet("font-size:12pt;color:#BDC1C6;")
        root_layout.addWidget(subtitle)
        cards = QGridLayout()
        cards.setSpacing(24)
        visual = WorkspaceCard(
            "scene_art_control",
            "场景美术控制",
            "围绕制作目标、参考图与 UE 截图，完成证据化审阅、任务和版本复查。",
            (
                "双图对比、共享色板、明度与成对区域",
                "制作意图、参考图视觉简报",
                "AI 主美与灯光专项审阅",
                "优化预演、任务与版本闭环",
            ),
        )
        artwork = WorkspaceCard(
            "artwork_study",
            "作品研究",
            "研究一张原画、概念图或优秀场景作品，逐层理解它为何有效以及如何组织观看。",
            (
                "单图本地明度、色彩、细节与空间证据",
                "灰度、明度归纳、剪影、伪色与构图辅助",
                "CG 主美十二维深度拆解与跨维度因果链",
                "个人学习笔记、画面标注与综合研究报告",
            ),
        )
        asset_breakdown = WorkspaceCard(
            "asset_breakdown",
            "资产拆分工作台",
            "把复杂游戏场景原画转换为可校正、可追溯的结构化生产资产清单。",
            (
                "建筑模块、道具、植被、地形、材质、贴花与远景分类",
                "原画区域、可见像素遮罩、层级、复用关系与制作优先级",
                "用户拆分、合并、重命名、补充和持久保存",
                "按需生成独立概念图、遮挡补全图和资产展示板",
            ),
        )
        for index, card in enumerate((visual, artwork, asset_breakdown)):
            card.selected.connect(self.workspace_selected)
            cards.addWidget(card, 0, index)
        root_layout.addLayout(cards, 1)
        footer = QLabel(
            "所有本地功能均可在无 API Key 时使用；网络发送只在你确认后发生。"
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        footer.setStyleSheet("color:#9AA0A6;")
        root_layout.addWidget(footer)
        self.setCentralWidget(root)
