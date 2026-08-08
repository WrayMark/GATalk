from __future__ import annotations


def asset_workspace_stylesheet() -> str:
    """Small workspace-specific layer on top of the global GATalk theme."""

    return """
QFrame#workflowContextBar {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 9px;
}
QFrame#workflowContextBar QLabel,
QFrame#workflowContextBar QComboBox,
QFrame#workflowContextBar QPushButton {
    background-color: transparent;
}
QFrame#workflowContextBar QComboBox,
QFrame#workflowContextBar QPushButton {
    background-color: palette(button);
}
QScrollArea#assetProjectScroll,
QScrollArea#promptWorkshopScroll,
QScrollArea#generationPageScroll,
QScrollArea#automaticPageScroll,
QScrollArea#assetBoardPreviewScroll {
    background: palette(window);
    border: none;
}
QWidget#promptWorkshopBody {
    background: palette(window);
}
QGroupBox#workflowSection {
    margin-top: 16px;
    padding-top: 14px;
    padding-left: 12px;
    padding-right: 12px;
    padding-bottom: 12px;
}
QLabel#workflowBasis {
    background: palette(alternate-base);
    border-left: 3px solid palette(highlight);
    border-radius: 6px;
    padding: 10px 12px;
}
QTabWidget#assetWorkflowTabs::pane {
    border-top: 1px solid palette(mid);
    border-radius: 0px;
}
QTabWidget#assetWorkflowTabs > QTabBar::tab {
    min-width: 112px;
    padding-left: 16px;
    padding-right: 16px;
}
QTabWidget#manualWorkflowTabs::pane {
    border-top: 1px solid palette(mid);
    border-radius: 0px;
}
QTabWidget#manualWorkflowTabs QTabBar::tab {
    min-width: 82px;
    padding-left: 12px;
    padding-right: 12px;
}
QDockWidget#assetBreakdownProjectDock QWidget {
    background: palette(window);
}
"""
